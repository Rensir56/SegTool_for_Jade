"""
RocketMQ消息处理器
定义各种消息类型的具体处理逻辑
集成多进程embedding缓存逻辑
"""

import time
import logging
import json
import numpy as np
import sys
import os
import hashlib
from typing import Dict, Any, List, Optional
from rocketmq_integration import SegmentMessage, MessageType

# 添加server目录到路径，以便导入SAM相关模块
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'server'))
from utils.click_signature import generate_click_signature_full
from segment_anything import SamPredictor, sam_model_registry
from PIL import Image
import torch

logger = logging.getLogger(__name__)

class MessageHandlers:
    """消息处理器集合 - 集成多进程embedding缓存逻辑"""
    
    def __init__(self, sam_predictor=None, yolo_model=None, redis_cache=None):
        """初始化消息处理器"""
        self.sam_predictor = sam_predictor
        self.yolo_model = yolo_model
        self.redis_cache = redis_cache
        
        # 进程内embedding缓存（类似多进程方案）
        self.embedding_cache = {}
        self.max_cache_size = 5  # 每个进程最多缓存5个embedding
        self.current_image_path = None
        self.current_embedding = None
        
        # 处理统计
        self.processing_stats = {
            'yolo_processed': 0,
            'sam_processed': 0,
            'batch_processed': 0,
            'total_processing_time': 0,
            'embedding_cache_hits': 0,
            'embedding_cache_misses': 0
        }
    
    def _get_image_hash(self, image_path: str) -> str:
        """生成图片哈希"""
        try:
            file_stat = os.stat(image_path)
            content = f"{image_path}_{file_stat.st_mtime}_{file_stat.st_size}"
            return hashlib.md5(content.encode()).hexdigest()
        except Exception as e:
            logger.warning(f"Failed to get image hash for {image_path}: {e}")
            return hashlib.md5(image_path.encode()).hexdigest()
    
    def _evict_oldest_embedding(self):
        """淘汰最旧的embedding"""
        if len(self.embedding_cache) >= self.max_cache_size:
            oldest_key = min(self.embedding_cache.keys(), 
                           key=lambda k: self.embedding_cache[k]['last_accessed'])
            del self.embedding_cache[oldest_key]
            logger.info(f"Evicted embedding for {oldest_key}")
    
    def _get_or_compute_embedding(self, image_path: str) -> Optional[np.ndarray]:
        """
        获取或计算embedding（集成多进程缓存逻辑）
        
        Args:
            image_path: 图片路径
            
        Returns:
            embedding数组或None
        """
        try:
            image_hash = self._get_image_hash(image_path)
            
            # 检查进程内缓存
            if image_hash in self.embedding_cache:
                # 缓存命中
                cache_entry = self.embedding_cache[image_hash]
                self.current_image_path = image_path
                self.current_embedding = cache_entry['embedding']
                
                # 更新访问时间
                cache_entry['last_accessed'] = time.time()
                cache_entry['access_count'] += 1
                
                self.processing_stats['embedding_cache_hits'] += 1
                logger.info(f"Embedding cache hit for {image_path}")
                return self.current_embedding
            
            # 缓存未命中，需要计算
            logger.info(f"Computing embedding for {image_path}")
            
            # 加载图片
            pil_image = Image.open(image_path)
            np_image = np.array(pil_image)
            
            # 计算embedding
            self.sam_predictor.set_image(np_image)
            embedding = self.sam_predictor.features.clone()  # 克隆embedding
            
            # 缓存embedding
            self._evict_oldest_embedding()
            self.embedding_cache[image_hash] = {
                'embedding': embedding,
                'image_path': image_path,
                'created_at': time.time(),
                'last_accessed': time.time(),
                'access_count': 1
            }
            
            self.current_image_path = image_path
            self.current_embedding = embedding
            
            self.processing_stats['embedding_cache_misses'] += 1
            logger.info(f"Embedding computed and cached for {image_path}")
            return self.current_embedding
            
        except Exception as e:
            logger.error(f"Error getting/computing embedding: {e}")
            return None
    
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
        """处理SAM分割消息 - 集成多进程embedding缓存逻辑"""
        start_time = time.time()
        
        try:
            payload = message.payload
            image_path = payload['image_path']
            clicks = payload['clicks']
            user_id = message.user_id
            
            logger.info(f"Processing SAM segmentation for {image_path}")
            
            # 生成点击签名用于缓存
            click_signature = self._generate_click_signature(clicks)
            
            # 获取或计算embedding（使用进程内缓存）
            embedding = self._get_or_compute_embedding(image_path)
            if embedding is None:
                raise Exception("Failed to get or compute embedding")
            
            # 检查Redis logit缓存
            cached_logit = None
            if self.redis_cache and len(clicks) > 1:  # 非首次分割才检查logit缓存
                try:
                    cached_logit = self.redis_cache.get_sam_logit(image_path, click_signature)
                    if cached_logit is not None:
                        logger.info("SAM logit found in Redis cache")
                except Exception as e:
                    logger.warning(f"Logit cache retrieval failed: {e}")
            
            # 执行SAM分割
            result = self._run_sam_segmentation(
                image_path, clicks, embedding, cached_logit
            )
            
            # 缓存logit到Redis
            if self.redis_cache and 'logit' in result:
                try:
                    self.redis_cache.set_sam_logit(
                        image_path, click_signature, result['logit'], ttl=1800
                    )
                    logger.info("SAM logit cached to Redis")
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
                'embedding_cache_hit': embedding is not None,
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
                            embedding=None, cached_logit=None) -> Dict[str, Any]:
        """执行SAM分割 - 使用真正的SAM模型"""
        try:
            # 准备输入点
            input_points = []
            input_labels = []
            for click in clicks:
                input_points.append([click["x"], click["y"]])
                input_labels.append(click["clickType"])
            
            input_points = np.array(input_points)
            input_labels = np.array(input_labels)
            
            # 设置embedding到predictor
            if embedding is not None:
                self.sam_predictor.features = embedding
                self.sam_predictor.is_image_set = True
            
            # 执行预测
            masks, scores, logits = self.sam_predictor.predict(
                point_coords=input_points,
                point_labels=input_labels,
                multimask_output=len(clicks) == 1
            )
            
            # 选择最佳结果
            best = np.argmax(scores)
            best_mask = masks[best, :, :]
            best_logit = logits[best, :, :]
            
            return {
                'mask': best_mask.tolist(),
                'shape': list(best_mask.shape),
                'logit': best_logit.tolist(),
                'clicks': clicks,
                'segmentation_time': time.time()
            }
            
        except Exception as e:
            logger.error(f"SAM segmentation execution failed: {e}")
            raise
    
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
    
    def _generate_click_signature(self, clicks: List[Dict], grid_size: int = 20) -> str:
        """生成点击签名用于缓存，支持坐标平滑化（使用共享工具函数）"""
        return generate_click_signature_full(clicks, grid_size)
    
    def get_processing_stats(self) -> Dict[str, Any]:
        """获取处理统计信息"""
        total_requests = sum([
            self.processing_stats['yolo_processed'],
            self.processing_stats['sam_processed'],
            self.processing_stats['batch_processed']
        ])
        
        embedding_cache_hit_rate = 0
        if (self.processing_stats['embedding_cache_hits'] + 
            self.processing_stats['embedding_cache_misses']) > 0:
            embedding_cache_hit_rate = (
                self.processing_stats['embedding_cache_hits'] / 
                (self.processing_stats['embedding_cache_hits'] + 
                 self.processing_stats['embedding_cache_misses'])
            )
        
        return {
            **self.processing_stats,
            'avg_processing_time': (
                self.processing_stats['total_processing_time'] / 
                max(1, total_requests)
            ),
            'embedding_cache_hit_rate': embedding_cache_hit_rate,
            'current_embedding_cache_size': len(self.embedding_cache),
            'max_embedding_cache_size': self.max_cache_size
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