"""
RocketMQ消息处理器
定义各种消息类型的具体处理逻辑
"""

import time
import logging
import json
import numpy as np
from typing import Dict, Any, List
from rocketmq_integration import SegmentMessage, MessageType

logger = logging.getLogger(__name__)

class MessageHandlers:
    """消息处理器集合"""
    
    def __init__(self, sam_predictor=None, yolo_model=None, redis_cache=None):
        """初始化消息处理器"""
        self.sam_predictor = sam_predictor
        self.yolo_model = yolo_model
        self.redis_cache = redis_cache
        
        # 处理统计
        self.processing_stats = {
            'yolo_processed': 0,
            'sam_processed': 0,
            'batch_processed': 0,
            'total_processing_time': 0
        }
    
    def handle_yolo_detect_message(self, message: SegmentMessage) -> Dict[str, Any]:
        """处理YOLO检测消息"""
        start_time = time.time()
        
        try:
            payload = message.payload
            image_path = payload['image_path']
            page_id = payload['page_id']
            filename = payload['filename']
            user_id = message.user_id
            
            logger.info(f"Processing YOLO detection for {image_path}, page {page_id}")
            
            # 检查Redis缓存
            cache_key = f"yolo:{filename}:page_{page_id}"
            cached_result = None
            
            if self.redis_cache:
                try:
                    cached_data = self.redis_cache.get(cache_key)
                    if cached_data:
                        cached_result = json.loads(cached_data)
                        logger.info(f"YOLO result found in cache for page {page_id}")
                except Exception as e:
                    logger.warning(f"Cache retrieval failed: {e}")
            
            # 如果缓存中没有，则进行检测
            if not cached_result:
                # 调用YOLO模型进行检测
                detection_result = self._run_yolo_detection(image_path, page_id, filename)
                
                # 缓存结果
                if self.redis_cache:
                    try:
                        self.redis_cache.setex(
                            cache_key, 
                            3600,  # 1小时缓存
                            json.dumps(detection_result)
                        )
                        logger.info(f"YOLO result cached for page {page_id}")
                    except Exception as e:
                        logger.warning(f"Failed to cache YOLO result: {e}")
                
                result = detection_result
            else:
                result = cached_result
                result['from_cache'] = True
            
            processing_time = time.time() - start_time
            self.processing_stats['yolo_processed'] += 1
            self.processing_stats['total_processing_time'] += processing_time
            
            logger.info(f"YOLO detection completed for page {page_id} in {processing_time:.2f}s")
            
            return {
                'success': True,
                'message_id': message.message_id,
                'page_id': page_id,
                'detection_result': result,
                'processing_time': processing_time,
                'cache_hit': 'from_cache' in result
            }
            
        except Exception as e:
            logger.error(f"YOLO detection failed for message {message.message_id}: {e}")
            raise
    
    def handle_sam_segment_message(self, message: SegmentMessage) -> Dict[str, Any]:
        """处理SAM分割消息"""
        start_time = time.time()
        
        try:
            payload = message.payload
            image_path = payload['image_path']
            clicks = payload['clicks']
            user_id = message.user_id
            
            logger.info(f"Processing SAM segmentation for {image_path}")
            
            # 生成点击签名用于缓存
            click_signature = self._generate_click_signature(clicks)
            
            # 检查embedding缓存
            embedding_cache_key = f"sam_embedding:{image_path}"
            cached_embedding = None
            
            if self.redis_cache:
                try:
                    cached_embedding = self.redis_cache.get_sam_embedding(image_path)
                    if cached_embedding is not None:
                        logger.info("SAM embedding found in cache")
                except Exception as e:
                    logger.warning(f"Embedding cache retrieval failed: {e}")
            
            # 检查logit缓存
            logit_cache_key = f"sam_logit:{image_path}:{click_signature}"
            cached_logit = None
            
            if self.redis_cache and len(clicks) > 1:  # 非首次分割才检查logit缓存
                try:
                    cached_logit = self.redis_cache.get_sam_logit(image_path, click_signature)
                    if cached_logit is not None:
                        logger.info("SAM logit found in cache")
                except Exception as e:
                    logger.warning(f"Logit cache retrieval failed: {e}")
            
            # 执行SAM分割
            result = self._run_sam_segmentation(
                image_path, clicks, cached_embedding, cached_logit
            )
            
            # 缓存embedding（如果是新的）
            if self.redis_cache and cached_embedding is None and 'embedding' in result:
                try:
                    self.redis_cache.set_sam_embedding(
                        image_path, result['embedding'], ttl=3600
                    )
                    logger.info("SAM embedding cached")
                except Exception as e:
                    logger.warning(f"Failed to cache embedding: {e}")
            
            # 缓存logit
            if self.redis_cache and 'logit' in result:
                try:
                    self.redis_cache.set_sam_logit(
                        image_path, click_signature, result['logit'], ttl=1800
                    )
                    logger.info("SAM logit cached")
                except Exception as e:
                    logger.warning(f"Failed to cache logit: {e}")
            
            processing_time = time.time() - start_time
            self.processing_stats['sam_processed'] += 1
            self.processing_stats['total_processing_time'] += processing_time
            
            logger.info(f"SAM segmentation completed in {processing_time:.2f}s")
            
            return {
                'success': True,
                'message_id': message.message_id,
                'mask': result['mask'],
                'shape': result['shape'],
                'processing_time': processing_time,
                'embedding_cache_hit': cached_embedding is not None,
                'logit_cache_hit': cached_logit is not None
            }
            
        except Exception as e:
            logger.error(f"SAM segmentation failed for message {message.message_id}: {e}")
            raise
    
    def handle_batch_process_message(self, message: SegmentMessage) -> Dict[str, Any]:
        """处理批量处理消息"""
        start_time = time.time()
        
        try:
            payload = message.payload
            pdf_filename = payload['pdf_filename']
            start_page = payload['start_page']
            end_page = payload['end_page']
            user_id = message.user_id
            
            logger.info(f"Processing batch job for {pdf_filename}, pages {start_page}-{end_page}")
            
            # 分页处理
            processed_pages = []
            failed_pages = []
            
            for page_num in range(start_page, end_page + 1):
                try:
                    # 处理单页
                    page_result = self._process_single_page(pdf_filename, page_num, user_id)
                    processed_pages.append({
                        'page_num': page_num,
                        'result': page_result,
                        'status': 'success'
                    })
                    logger.info(f"Page {page_num} processed successfully")
                    
                except Exception as e:
                    failed_pages.append({
                        'page_num': page_num,
                        'error': str(e),
                        'status': 'failed'
                    })
                    logger.error(f"Page {page_num} processing failed: {e}")
                
                # 添加小延迟避免过载
                time.sleep(0.1)
            
            processing_time = time.time() - start_time
            self.processing_stats['batch_processed'] += 1
            self.processing_stats['total_processing_time'] += processing_time
            
            logger.info(f"Batch processing completed in {processing_time:.2f}s")
            
            return {
                'success': True,
                'message_id': message.message_id,
                'pdf_filename': pdf_filename,
                'processed_pages': len(processed_pages),
                'failed_pages': len(failed_pages),
                'page_results': processed_pages,
                'failures': failed_pages,
                'processing_time': processing_time
            }
            
        except Exception as e:
            logger.error(f"Batch processing failed for message {message.message_id}: {e}")
            raise
    
    def _run_yolo_detection(self, image_path: str, page_id: int, filename: str) -> Dict[str, Any]:
        """执行YOLO检测（模拟实现）"""
        # 这里应该调用实际的YOLO检测逻辑
        # 暂时返回模拟结果
        time.sleep(2)  # 模拟检测时间
        
        return {
            'detections': [
                {
                    'bbox': [100, 100, 200, 200],
                    'confidence': 0.95,
                    'class': 'artifact',
                    'class_id': 0
                },
                {
                    'bbox': [300, 150, 400, 250],
                    'confidence': 0.88,
                    'class': 'artifact',
                    'class_id': 0
                }
            ],
            'image_path': image_path,
            'page_id': page_id,
            'filename': filename,
            'detection_time': time.time()
        }
    
    def _run_sam_segmentation(self, image_path: str, clicks: List[Dict], 
                            cached_embedding=None, cached_logit=None) -> Dict[str, Any]:
        """执行SAM分割（模拟实现）"""
        # 这里应该调用实际的SAM分割逻辑
        
        # 模拟embedding计算（如果没有缓存）
        if cached_embedding is None:
            time.sleep(2)  # 模拟embedding计算时间
            embedding = np.random.rand(256, 64, 64).astype(np.float32)
        else:
            embedding = cached_embedding
        
        # 模拟分割计算
        if cached_logit is None:
            time.sleep(1)  # 模拟分割时间
        else:
            time.sleep(0.2)  # 缓存命中时更快
        
        # 生成模拟mask
        mask = np.random.randint(0, 2, (512, 512), dtype=np.uint8)
        logit = np.random.rand(512, 512).astype(np.float32)
        
        return {
            'mask': mask.tolist(),
            'shape': [512, 512],
            'embedding': embedding if cached_embedding is None else None,
            'logit': logit,
            'clicks': clicks,
            'segmentation_time': time.time()
        }
    
    def _process_single_page(self, pdf_filename: str, page_num: int, user_id: str) -> Dict[str, Any]:
        """处理单个PDF页面"""
        # 模拟页面处理
        time.sleep(1)
        
        return {
            'page_num': page_num,
            'artifacts_found': np.random.randint(1, 5),
            'processing_time': 1.0,
            'status': 'completed'
        }
    
    def _generate_click_signature(self, clicks: List[Dict]) -> str:
        """生成点击签名用于缓存"""
        # 将点击坐标和类型转换为字符串签名
        click_str = ""
        for click in sorted(clicks, key=lambda x: (x['x'], x['y'])):
            click_str += f"{click['x']},{click['y']},{click['clickType']};"
        
        import hashlib
        return hashlib.md5(click_str.encode()).hexdigest()
    
    def get_processing_stats(self) -> Dict[str, Any]:
        """获取处理统计信息"""
        return {
            **self.processing_stats,
            'avg_processing_time': (
                self.processing_stats['total_processing_time'] / 
                max(1, sum([
                    self.processing_stats['yolo_processed'],
                    self.processing_stats['sam_processed'],
                    self.processing_stats['batch_processed']
                ]))
            )
        }

# 全局消息处理器实例
message_handlers = None

def init_message_handlers(sam_predictor=None, yolo_model=None, redis_cache=None):
    """初始化全局消息处理器"""
    global message_handlers
    message_handlers = MessageHandlers(sam_predictor, yolo_model, redis_cache)
    return message_handlers

def get_message_handlers() -> MessageHandlers:
    """获取全局消息处理器"""
    if message_handlers is None:
        raise RuntimeError("Message handlers not initialized. Call init_message_handlers() first.")
    return message_handlers 