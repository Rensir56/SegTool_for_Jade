"""
YOLO服务器 - 集成RocketMQ版本  
实现异步消息处理和GPU资源调度
"""

import os
import time
import logging
import subprocess
import shutil
import atexit
from natsort import natsorted
from contextlib import asynccontextmanager
from flask import Flask, request, jsonify, send_from_directory, url_for
from flask_cors import CORS
import threading

# RocketMQ和Redis集成
from rocketmq_integration import (
    init_rocketmq_manager, get_rocketmq_manager,
    MessageType, MessagePriority
)
from rocketmq_message_handlers import init_message_handlers, get_message_handlers
from redis_cache import init_redis_cache, get_redis_cache

# 数据库集成
from database_manager import init_database_manager, get_database_manager

# YOLO处理逻辑
from Newcut import process_image

# 配置日志
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 全局变量
rocketmq_manager = None
message_handlers = None
redis_cache = None
database_manager = None

# Flask应用配置
app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

# 基础路径配置
base_detect_path = os.path.abspath('./runs/detect')
model_path = "best.pt"
flag_clean = True

def init_yolo_services():
    """初始化YOLO服务的各种组件"""
    global rocketmq_manager, message_handlers, redis_cache, database_manager
    
    try:
        logger.info("Initializing YOLO server with RocketMQ...")
        
        # 1. 初始化Redis缓存
        logger.info("Initializing Redis cache...")
        redis_cache = init_redis_cache()
        
        # 2. 初始化数据库
        logger.info("Initializing database...")
        database_manager = init_database_manager()
        
        # 3. 初始化RocketMQ
        logger.info("Initializing RocketMQ...")
        rocketmq_manager = init_rocketmq_manager(
            nameserver_address=os.getenv('ROCKETMQ_NAMESERVER', 'localhost:9876'),
            group_id='segtool_yolo_group'
        )
        
        # 4. 初始化消息处理器
        logger.info("Initializing message handlers...")
        message_handlers = init_message_handlers(
            yolo_model=model_path,
            redis_cache=redis_cache
        )
        
        # 5. 注册消息处理器
        rocketmq_manager.register_message_handler(
            MessageType.YOLO_DETECT, 
            message_handlers.handle_yolo_detect_message
        )
        rocketmq_manager.register_message_handler(
            MessageType.BATCH_PROCESS,
            message_handlers.handle_batch_process_message
        )
        
        # 6. 启动消息消费者
        rocketmq_manager.start_consumer(MessageType.YOLO_DETECT)
        rocketmq_manager.start_consumer(MessageType.BATCH_PROCESS)
        
        logger.info("YOLO server with RocketMQ initialized successfully")
        
    except Exception as e:
        logger.error(f"Failed to initialize YOLO server: {e}")
        raise

def get_user_id_from_request(user_agent: str = None) -> str:
    """从请求中提取用户ID"""
    if user_agent:
        import hashlib
        return hashlib.md5(user_agent.encode()).hexdigest()[:16]
    return "anonymous_user"

@app.route('/uploadimg_async', methods=['POST'])
def upload_image_async():
    """异步上传和处理接口 - 通过RocketMQ处理"""
    try:
        if not request.json:
            return jsonify({'error': 'No JSON payload provided'}), 400

        image_path = request.json.get('path')
        page_id = request.json.get('page')
        file_name = request.json.get('filename')
        user_agent = request.headers.get('User-Agent', '')
        user_id = get_user_id_from_request(user_agent)

        if not image_path or not os.path.exists(image_path):
            return jsonify({'error': 'Invalid path'}), 400

        # 发送消息到RocketMQ
        message_id = rocketmq_manager.send_yolo_detect_message(
            user_id=user_id,
            project_id=file_name,
            image_path=image_path,
            page_id=page_id,
            filename=file_name,
            priority=MessagePriority.NORMAL
        )
        
        # 记录到数据库
        if database_manager:
            try:
                database_manager.log_processing_request(
                    user_id=user_id,
                    project_id=file_name,
                    request_type='yolo_detect',
                    request_data={'page_id': page_id, 'image_path': image_path},
                    message_id=message_id
                )
            except Exception as e:
                logger.warning(f"Failed to log request to database: {e}")

        return jsonify({
            'message_id': message_id,
            'status': 'submitted',
            'page_id': page_id,
            'estimated_time': 10  # 预估处理时间（秒）
        })

    except Exception as e:
        logger.error(f"Failed to submit YOLO task: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/uploadimg', methods=['POST'])
def upload_image():
    """同步上传接口 - 兼容性保持"""
    try:
        if not request.json:
            return jsonify({'error': 'No JSON payload provided'}), 400

        image_path = request.json.get('path')
        page_id = request.json.get('page')
        file_name = request.json.get('filename')

        if not image_path or not os.path.exists(image_path):
            return jsonify({'error': 'Invalid path'}), 400

        # 检查Redis缓存
        cache_key = f"yolo:{file_name}:page_{page_id}"
        if redis_cache:
            cached_result = redis_cache.get_json(cache_key)
            if cached_result:
                logger.info(f"YOLO result found in cache for page {page_id}")
                return jsonify({'message': 'Image processed successfully (cached)'})

        # 执行YOLO检测
        result = _execute_yolo_detection(image_path, page_id, file_name)
        
        # 缓存结果
        if redis_cache:
            redis_cache.set_json(cache_key, result, ttl=3600)

        return jsonify({'message': 'Image processed successfully'})

    except Exception as e:
        logger.error(f"Sync YOLO processing failed: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/segmentimg_async', methods=['POST'])
def segment_image_async():
    """异步分割接口"""
    try:
        if not request.json:
            return jsonify({'error': 'No JSON payload provided'}), 400

        page_id = request.json.get('pageId')
        file_name = request.json.get('filename')
        user_agent = request.headers.get('User-Agent', '')
        user_id = get_user_id_from_request(user_agent)

        if not page_id:
            return jsonify({'error': 'Missing pageId parameter'}), 400

        # 发送批处理消息到RocketMQ
        message_id = rocketmq_manager.send_batch_process_message(
            user_id=user_id,
            project_id=file_name,
            pdf_filename=file_name,
            start_page=page_id,
            end_page=page_id,
            priority=MessagePriority.HIGH
        )

        return jsonify({
            'message_id': message_id,
            'status': 'submitted',
            'page_id': page_id,
            'estimated_time': 5
        })

    except Exception as e:
        logger.error(f"Failed to submit segment task: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/segmentimg', methods=['POST'])
def segment_image():
    """同步分割接口 - 兼容性保持"""
    try:
        if not request.json:
            return jsonify({'error': 'No JSON payload provided'}), 400

        page_id = request.json.get('pageId')
        file_name = request.json.get('filename')
        
        if not page_id:
            return jsonify({'error': 'Missing pageId parameter'}), 400

        # 检查缓存
        cache_key = f"yolo_segment:{file_name}:page_{page_id}"
        if redis_cache:
            cached_result = redis_cache.get_json(cache_key)
            if cached_result:
                logger.info(f"Segment result found in cache for page {page_id}")
                return jsonify(cached_result)

        # 执行分割
        result = _execute_yolo_segmentation(page_id, file_name)
        
        # 缓存结果
        if redis_cache:
            redis_cache.set_json(cache_key, result, ttl=1800)

        return jsonify(result)

    except Exception as e:
        logger.error(f"Sync segment processing failed: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/task_status/<message_id>')
def get_task_status(message_id):
    """查询任务状态"""
    try:
        # 从Redis查询结果
        result_key = f"yolo_result:{message_id}"
        result = redis_cache.get_json(result_key) if redis_cache else None
        
        if result:
            return jsonify({
                'message_id': message_id,
                'status': 'completed',
                'result': result
            })
        else:
            return jsonify({
                'message_id': message_id,
                'status': 'processing',
                'progress': 'in_queue'
            })
            
    except Exception as e:
        logger.error(f"Failed to get task status: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/queue_stats')
def get_queue_stats():
    """获取队列统计信息"""
    try:
        mq_stats = rocketmq_manager.get_stats()
        handler_stats = message_handlers.get_processing_stats()
        
        return jsonify({
            'rocketmq_stats': mq_stats,
            'processing_stats': handler_stats,
            'server_status': 'healthy'
        })
        
    except Exception as e:
        logger.error(f"Failed to get queue stats: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/health')
def health_check():
    """健康检查"""
    try:
        redis_status = "ok" if redis_cache and redis_cache.ping() else "error"
        mq_status = "ok" if rocketmq_manager else "error"
        
        return jsonify({
            'status': 'healthy' if all([
                redis_status == "ok",
                mq_status == "ok"
            ]) else 'unhealthy',
            'components': {
                'redis': redis_status,
                'rocketmq': mq_status,
                'yolo_model': "ok"
            },
            'timestamp': time.time()
        })
        
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return jsonify({
            'status': 'unhealthy',
            'error': str(e),
            'timestamp': time.time()
        })

@app.route('/image/<path:file_name>/<path:folder>/<filename>')
def serve_image(file_name, folder, filename):
    """提供图片文件服务"""
    folder_path = os.path.join(base_detect_path, file_name, folder)
    logger.info(f"Requested folder_path: {folder_path}")
    logger.info(f"Requested filename: {filename}")

    if not os.path.exists(os.path.join(folder_path, filename)):
        return jsonify({'error': 'File not found'}), 404

    return send_from_directory(folder_path, filename)

def _execute_yolo_detection(image_path: str, page_id: int, file_name: str):
    """执行YOLO检测"""
    try:
        # 确定运行次数目录名称
        i = 1
        while os.path.exists(os.path.join(base_detect_path, f'predict{i}')):
            i += 1

        # 构建并执行命令
        command = [
            "yolo", "predict",
            f"model={model_path}",
            f"source={image_path}",
            "save_txt=True",
            "hide_labels=False",
            "hide_conf=False",
            "show_boxes=False",
            f"name=predict{page_id}",
            f"project={os.path.join(base_detect_path, file_name)}"
        ]

        logger.info(f"Executing command: {command}")

        result = subprocess.run(
            command, 
            capture_output=True, 
            text=True, 
            encoding='utf-8', 
            check=True
        )
        
        logger.info(f"Command executed successfully: {result.stdout}")
        
        return {
            'success': True,
            'output': result.stdout,
            'command': ' '.join(command)
        }
        
    except subprocess.CalledProcessError as e:
        logger.error(f"Error executing command: {e.stderr}")
        raise Exception(f"Command failed: {e.stderr}")

def _execute_yolo_segmentation(page_id: int, file_name: str):
    """执行YOLO分割"""
    try:
        img_folder = os.path.join(os.path.join(base_detect_path, file_name), f'predict{page_id}')
        txt_folder = os.path.join(img_folder, 'labels')
        save_folder = os.path.join(img_folder, 'Result_single')

        if not os.path.exists(txt_folder):
            raise Exception('Label folder not found')

        process_image(txt_folder, img_folder, save_folder)

        images = []
        for filename in natsorted(os.listdir(save_folder)):
            if filename.endswith('.jpg') or filename.endswith('.png'):
                image_url = url_for('serve_image', 
                                  file_name=file_name, 
                                  folder=f'predict{page_id}/Result_single', 
                                  filename=filename, 
                                  _external=True)
                images.append({
                    'name': filename,
                    'image': image_url
                })

        logger.info(f"save_folder: {save_folder}")
        logger.info(f"images: {images}")

        return {"images": images}
        
    except Exception as e:
        logger.error(f"Error during image processing: {str(e)}")
        raise Exception(f'Processing error: {str(e)}')

@atexit.register
def clean_up():
    """清理资源"""
    if flag_clean:
        for item_name in os.listdir(base_detect_path):
            item_path = os.path.join(base_detect_path, item_name)
            if os.path.isdir(item_path):
                shutil.rmtree(item_path, ignore_errors=True)
            else:
                os.remove(item_path)
        logger.info("Cleanup completed")
    
    # 关闭RocketMQ连接
    if rocketmq_manager:
        rocketmq_manager.shutdown()

if __name__ == '__main__':
    import sys
    sys.stdout.reconfigure(encoding='utf-8')
    
    # 初始化服务
    init_yolo_services()
    
    # 启动Flask应用
    app.run(host='0.0.0.0', port=8005, debug=False) 