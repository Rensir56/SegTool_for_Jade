"""
SAM服务器 - 集成RocketMQ版本
实现异步消息处理和GPU资源调度
"""

import os
import time
import logging
import numpy as np
from contextlib import asynccontextmanager
from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

# SAM相关导入
from segment_anything import SamPredictor, sam_model_registry
from segment_anything.utils import amg
import cv2
import lzstring
from pycocotools import mask as mask_utils

# RocketMQ和Redis集成
from rocketmq_integration import (
    init_rocketmq_manager, get_rocketmq_manager,
    MessageType, MessagePriority
)
from rocketmq_message_handlers import init_message_handlers, get_message_handlers
from redis_cache import init_redis_cache, get_redis_cache
from utils.click_signature import generate_click_signature_full

# 数据库集成
from database_manager import init_database_manager, get_database_manager

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 全局变量
sam_predictor = None
rocketmq_manager = None
message_handlers = None
redis_cache = None
database_manager = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    global sam_predictor, rocketmq_manager, message_handlers, redis_cache, database_manager
    
    try:
        logger.info("Initializing SAM server with RocketMQ...")
        
        # 1. 初始化Redis缓存
        logger.info("Initializing Redis cache...")
        redis_cache = init_redis_cache()
        
        # 2. 初始化数据库
        logger.info("Initializing database...")
        database_manager = init_database_manager()
        
        # 3. 初始化SAM模型
        logger.info("Loading SAM model...")
        sam_checkpoint = os.path.join(os.path.dirname(__file__), "sam_vit_h_4b8939.pth")
        device = "cuda" if os.path.exists("/proc/driver/nvidia/version") else "cpu"
        
        sam = sam_model_registry["vit_h"](checkpoint=sam_checkpoint)
        sam.to(device=device)
        sam_predictor = SamPredictor(sam)
        logger.info(f"SAM model loaded on {device}")
        
        # 4. 初始化RocketMQ
        logger.info("Initializing RocketMQ...")
        rocketmq_manager = init_rocketmq_manager(
            nameserver_address=os.getenv('ROCKETMQ_NAMESERVER', 'localhost:9876'),
            group_id='segtool_sam_group'
        )
        
        # 5. 初始化消息处理器
        logger.info("Initializing message handlers...")
        message_handlers = init_message_handlers(
            sam_predictor=sam_predictor,
            redis_cache=redis_cache
        )
        
        # 6. 注册消息处理器
        rocketmq_manager.register_message_handler(
            MessageType.SAM_SEGMENT, 
            message_handlers.handle_sam_segment_message
        )
        
        # 7. 启动消息消费者
        rocketmq_manager.start_consumer(MessageType.SAM_SEGMENT)
        
        logger.info("SAM server with RocketMQ initialized successfully")
        
        yield  # 运行应用
        
    except Exception as e:
        logger.error(f"Failed to initialize SAM server: {e}")
        raise
    finally:
        # 清理资源
        logger.info("Shutting down SAM server...")
        if rocketmq_manager:
            rocketmq_manager.shutdown()
        logger.info("SAM server shutdown complete")

# 创建FastAPI应用
app = FastAPI(
    title="SAM Segmentation Service with RocketMQ",
    description="Segment Anything Model service with RocketMQ message queue",
    version="2.0.0",
    lifespan=lifespan
)

# CORS配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def get_user_id_from_request(user_agent: str = None) -> str:
    """从请求中提取用户ID"""
    # 简单的用户识别逻辑
    if user_agent:
        import hashlib
        return hashlib.md5(user_agent.encode()).hexdigest()[:16]
    return "anonymous_user"

@app.post("/segment_async")
async def segment_async(body: dict, user_agent: str = Header(None)):
    """异步分割接口 - 通过RocketMQ处理"""
    try:
        user_id = get_user_id_from_request(user_agent)
        image_path = body.get('path')
        clicks = body.get('clicks', [])
        
        if not image_path or not clicks:
            raise HTTPException(status_code=400, detail="Missing path or clicks")
        
        # 发送消息到RocketMQ
        message_id = rocketmq_manager.send_sam_segment_message(
            user_id=user_id,
            project_id=body.get('project_id', 'default'),
            image_path=image_path,
            clicks=clicks,
            priority=MessagePriority.HIGH  # 用户交互任务高优先级
        )
        
        # 记录到数据库
        if database_manager:
            try:
                database_manager.log_processing_request(
                    user_id=user_id,
                    project_id=body.get('project_id', 'default'),
                    request_type='sam_segment',
                    request_data={'clicks_count': len(clicks)},
                    message_id=message_id
                )
            except Exception as e:
                logger.warning(f"Failed to log request to database: {e}")
        
        return {
            'message_id': message_id,
            'status': 'submitted',
            'estimated_time': 5,  # 预估处理时间（秒）
            'queue_position': 'calculating...'
        }
        
    except Exception as e:
        logger.error(f"Failed to submit segment task: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/task_status/{message_id}")
async def get_task_status(message_id: str, user_agent: str = Header(None)):
    """查询任务状态"""
    try:
        # 这里需要实现任务状态查询逻辑
        # 可以通过Redis查询结果或者数据库查询状态
        
        # 简单实现：从Redis查询结果
        result_key = f"sam_result:{message_id}"
        result = redis_cache.get_json(result_key)
        
        if result:
            return {
                'message_id': message_id,
                'status': 'completed',
                'result': result
            }
        else:
            return {
                'message_id': message_id,
                'status': 'processing',
                'progress': 'in_queue'
            }
            
    except Exception as e:
        logger.error(f"Failed to get task status: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/segment")
def segment_sync(body: dict, user_agent: str = Header(None)):
    """同步分割接口 - 兼容性保持"""
    try:
        user_id = get_user_id_from_request(user_agent)
        image_path = body.get('path')
        clicks = body.get('clicks', [])
        
        if not image_path or not clicks:
            raise HTTPException(status_code=400, detail="Missing path or clicks")
        
        # 直接处理（不通过队列）用于快速响应
        start_time = time.time()
        
        # 检查Redis缓存
        click_signature = _generate_click_signature(clicks)
        cached_result = redis_cache.get_sam_result(image_path, click_signature)
        
        if cached_result:
            logger.info("SAM result found in cache")
            return cached_result
        
        # 执行分割
        result = _execute_sam_segmentation(image_path, clicks)
        
        # 缓存结果
        redis_cache.set_sam_result(image_path, click_signature, result, ttl=1800)
        
        processing_time = time.time() - start_time
        logger.info(f"Sync segmentation completed in {processing_time:.2f}s")
        
        return result
        
    except Exception as e:
        logger.error(f"Sync segmentation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/queue_stats")
async def get_queue_stats():
    """获取队列统计信息"""
    try:
        mq_stats = rocketmq_manager.get_stats()
        handler_stats = message_handlers.get_processing_stats()
        
        return {
            'rocketmq_stats': mq_stats,
            'processing_stats': handler_stats,
            'server_status': 'healthy'
        }
        
    except Exception as e:
        logger.error(f"Failed to get queue stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
async def health_check():
    """健康检查"""
    try:
        # 检查各组件状态
        redis_status = "ok" if redis_cache and redis_cache.ping() else "error"
        sam_status = "ok" if sam_predictor else "error"
        mq_status = "ok" if rocketmq_manager else "error"
        
        return {
            'status': 'healthy' if all([
                redis_status == "ok",
                sam_status == "ok", 
                mq_status == "ok"
            ]) else 'unhealthy',
            'components': {
                'redis': redis_status,
                'sam_model': sam_status,
                'rocketmq': mq_status
            },
            'timestamp': time.time()
        }
        
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {
            'status': 'unhealthy',
            'error': str(e),
            'timestamp': time.time()
        }

def _generate_click_signature(clicks, grid_size: int = 20):
    """生成点击签名，支持坐标平滑化（使用共享工具函数）"""
    return generate_click_signature_full(clicks, grid_size)

def _execute_sam_segmentation(image_path: str, clicks: list):
    """执行SAM分割"""
    try:
        # 加载和设置图像
        image = cv2.imread(image_path)
        if image is None:
            raise ValueError(f"Cannot read image: {image_path}")
        
        image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        sam_predictor.set_image(image_rgb)
        
        # 准备输入点
        input_points = []
        input_labels = []
        for click in clicks:
            input_points.append([click["x"], click["y"]])
            input_labels.append(click["clickType"])
        
        input_points = np.array(input_points)
        input_labels = np.array(input_labels)
        
        # 执行预测
        masks, scores, logits = sam_predictor.predict(
            point_coords=input_points,
            point_labels=input_labels,
            multimask_output=len(clicks) == 1
        )
        
        # 选择最佳结果
        best = np.argmax(scores)
        best_mask = masks[best, :, :]
        
        # 编码mask
        source_mask = mask_utils.encode(np.asfortranarray(best_mask))["counts"]
        if isinstance(source_mask, bytes):
            source_mask = source_mask.decode("utf-8")
        
        lzs = lzstring.LZString()
        encoded = lzs.compressToEncodedURIComponent(source_mask)
        
        return {
            'mask': encoded,
            'shape': list(best_mask.shape),
            'score': float(scores[best])
        }
        
    except Exception as e:
        logger.error(f"SAM segmentation execution failed: {e}")
        raise

if __name__ == "__main__":
    uvicorn.run(
        "main_rocketmq:app",
        host="0.0.0.0",
        port=8080,
        reload=False,
        workers=1  # RocketMQ消费者不能多进程
    ) 