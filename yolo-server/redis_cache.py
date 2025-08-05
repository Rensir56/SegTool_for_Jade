# YOLO服务器Redis缓存模块
import redis
import json
import hashlib
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime

logger = logging.getLogger(__name__)

class YOLORedisCache:
    """YOLO服务器Redis缓存管理器"""
    
    def __init__(self, host='localhost', port=6379, db=1, password=None):
        """初始化Redis连接"""
        try:
            self.redis_client = redis.Redis(
                host=host, 
                port=port, 
                db=db,  # 使用不同的数据库
                password=password,
                decode_responses=True  # YOLO主要存储JSON数据
            )
            self.redis_client.ping()
            logger.info("YOLO Redis cache initialized successfully")
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            raise
    
    def _get_file_hash(self, file_path: str, page_id: int) -> str:
        """生成文件+页面的唯一哈希"""
        import os
        try:
            file_stat = os.stat(file_path)
            content = f"{file_path}_{page_id}_{file_stat.st_mtime}_{file_stat.st_size}"
            return hashlib.md5(content.encode()).hexdigest()
        except OSError:
            # 文件不存在时使用路径和页面ID
            content = f"{file_path}_{page_id}"
            return hashlib.md5(content.encode()).hexdigest()
    
    # ==================== YOLO检测结果缓存 ====================
    
    def get_yolo_result(self, image_path: str, page_id: int, filename: str) -> Optional[Dict[str, Any]]:
        """获取YOLO检测结果缓存"""
        try:
            file_hash = self._get_file_hash(image_path, page_id)
            cache_key = f"yolo:result:{file_hash}:{filename}"
            
            cached_result = self.redis_client.get(cache_key)
            if cached_result:
                result_data = json.loads(cached_result)
                logger.info(f"YOLO result cache hit for {image_path} page {page_id}")
                return result_data
            
            logger.info(f"YOLO result cache miss for {image_path} page {page_id}")
            return None
        except Exception as e:
            logger.error(f"Error retrieving YOLO result cache: {e}")
            return None
    
    def set_yolo_result(self, image_path: str, page_id: int, filename: str, result_data: Dict[str, Any], ttl: int = 7200):
        """设置YOLO检测结果缓存"""
        try:
            file_hash = self._get_file_hash(image_path, page_id)
            cache_key = f"yolo:result:{file_hash}:{filename}"
            
            # 添加时间戳
            result_data['cached_at'] = datetime.now().isoformat()
            result_data['cache_key'] = cache_key
            
            serialized_data = json.dumps(result_data)
            self.redis_client.setex(cache_key, ttl, serialized_data)
            logger.info(f"YOLO result cached for {image_path} page {page_id}, TTL: {ttl}s")
        except Exception as e:
            logger.error(f"Error setting YOLO result cache: {e}")
    
    # ==================== 批量处理状态管理 ====================
    
    def get_batch_processing_status(self, user_id: str, filename: str) -> Optional[Dict[str, Any]]:
        """获取批量处理状态"""
        try:
            status_key = f"yolo:batch:{user_id}:{filename}"
            status_data = self.redis_client.hgetall(status_key)
            
            if status_data:
                # 解析数据类型
                parsed_status = {}
                for key, value in status_data.items():
                    try:
                        parsed_status[key] = json.loads(value)
                    except:
                        parsed_status[key] = value
                
                logger.info(f"Batch processing status retrieved for {user_id}/{filename}")
                return parsed_status
            return None
        except Exception as e:
            logger.error(f"Error retrieving batch processing status: {e}")
            return None
    
    def update_batch_processing_status(self, user_id: str, filename: str, status_update: Dict[str, Any]):
        """更新批量处理状态"""
        try:
            status_key = f"yolo:batch:{user_id}:{filename}"
            
            # 序列化复杂数据
            serialized_update = {}
            for key, value in status_update.items():
                if isinstance(value, (dict, list)):
                    serialized_update[key] = json.dumps(value)
                else:
                    serialized_update[key] = str(value)
            
            self.redis_client.hset(status_key, mapping=serialized_update)
            self.redis_client.expire(status_key, 86400)  # 24小时过期
            logger.info(f"Batch processing status updated for {user_id}/{filename}")
        except Exception as e:
            logger.error(f"Error updating batch processing status: {e}")
    
    def set_page_processing_lock(self, user_id: str, filename: str, page_id: int, ttl: int = 300):
        """设置页面处理锁，防止重复处理"""
        try:
            lock_key = f"yolo:lock:{user_id}:{filename}:page_{page_id}"
            
            # 使用SET NX（不存在时设置）实现分布式锁
            lock_acquired = self.redis_client.set(lock_key, "locked", nx=True, ex=ttl)
            
            if lock_acquired:
                logger.info(f"Processing lock acquired for page {page_id}")
                return True
            else:
                logger.warning(f"Processing lock already exists for page {page_id}")
                return False
        except Exception as e:
            logger.error(f"Error setting processing lock: {e}")
            return False
    
    def release_page_processing_lock(self, user_id: str, filename: str, page_id: int):
        """释放页面处理锁"""
        try:
            lock_key = f"yolo:lock:{user_id}:{filename}:page_{page_id}"
            self.redis_client.delete(lock_key)
            logger.info(f"Processing lock released for page {page_id}")
        except Exception as e:
            logger.error(f"Error releasing processing lock: {e}")
    
    # ==================== 用户会话管理 ====================
    
    def get_user_session(self, user_id: str) -> Optional[Dict[str, Any]]:
        """获取用户会话"""
        try:
            session_key = f"yolo:session:{user_id}"
            session_data = self.redis_client.hgetall(session_key)
            
            if session_data:
                parsed_session = {}
                for key, value in session_data.items():
                    try:
                        parsed_session[key] = json.loads(value)
                    except:
                        parsed_session[key] = value
                return parsed_session
            return None
        except Exception as e:
            logger.error(f"Error retrieving user session: {e}")
            return None
    
    def update_user_session(self, user_id: str, session_data: Dict[str, Any]):
        """更新用户会话"""
        try:
            session_key = f"yolo:session:{user_id}"
            
            serialized_data = {}
            for key, value in session_data.items():
                if isinstance(value, (dict, list)):
                    serialized_data[key] = json.dumps(value)
                else:
                    serialized_data[key] = str(value)
            
            self.redis_client.hset(session_key, mapping=serialized_data)
            self.redis_client.expire(session_key, 86400)  # 24小时
            logger.info(f"User session updated for {user_id}")
        except Exception as e:
            logger.error(f"Error updating user session: {e}")

# 全局实例
yolo_redis_cache = None

def init_yolo_redis_cache(host='localhost', port=6379, db=1, password=None):
    """初始化YOLO Redis缓存"""
    global yolo_redis_cache
    yolo_redis_cache = YOLORedisCache(host=host, port=port, db=db, password=password)
    return yolo_redis_cache

def get_yolo_redis_cache() -> YOLORedisCache:
    """获取YOLO Redis缓存实例"""
    global yolo_redis_cache
    if yolo_redis_cache is None:
        yolo_redis_cache = init_yolo_redis_cache()
    return yolo_redis_cache 