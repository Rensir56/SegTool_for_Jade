import redis
import pickle
import hashlib
import json
from typing import Optional, Dict, Any
import numpy as np
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

class RedisCache:
    """Redis缓存管理器，用于SAM embedding缓存和用户会话管理"""
    
    def __init__(self, host='localhost', port=6379, db=0, password=None):
        """初始化Redis连接"""
        try:
            self.redis_client = redis.Redis(
                host=host, 
                port=port, 
                db=db, 
                password=password,
                decode_responses=False  # 保持二进制数据
            )
            self.redis_client.ping()  # 测试连接
            logger.info("Redis connection established successfully")
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            raise
    
    def _get_image_hash(self, image_path: str) -> str:
        """生成图片的唯一哈希值"""
        import os
        # 结合文件路径和修改时间生成hash
        file_stat = os.stat(image_path)
        content = f"{image_path}_{file_stat.st_mtime}_{file_stat.st_size}"
        return hashlib.md5(content.encode()).hexdigest()
    
    # ==================== SAM Embedding 缓存 ====================
    
    def get_sam_embedding(self, image_path: str) -> Optional[Dict[str, Any]]:
        """获取SAM embedding缓存"""
        try:
            image_hash = self._get_image_hash(image_path)
            cache_key = f"sam:embedding:{image_hash}"
            
            cached_data = self.redis_client.get(cache_key)
            if cached_data:
                embedding_data = pickle.loads(cached_data)
                logger.info(f"SAM embedding cache hit for {image_path}")
                return embedding_data
            
            logger.info(f"SAM embedding cache miss for {image_path}")
            return None
        except Exception as e:
            logger.error(f"Error retrieving SAM embedding cache: {e}")
            return None
    
    def set_sam_embedding(self, image_path: str, embedding_data: Dict[str, Any], ttl: int = 3600):
        """设置SAM embedding缓存"""
        try:
            image_hash = self._get_image_hash(image_path)
            cache_key = f"sam:embedding:{image_hash}"
            
            serialized_data = pickle.dumps(embedding_data)
            self.redis_client.setex(cache_key, ttl, serialized_data)
            logger.info(f"SAM embedding cached for {image_path}, TTL: {ttl}s")
        except Exception as e:
            logger.error(f"Error setting SAM embedding cache: {e}")
    
    def get_sam_logit(self, image_path: str, click_signature: str) -> Optional[np.ndarray]:
        """获取SAM logit缓存（基于点击历史）"""
        try:
            image_hash = self._get_image_hash(image_path)
            cache_key = f"sam:logit:{image_hash}:{click_signature}"
            
            cached_logit = self.redis_client.get(cache_key)
            if cached_logit:
                logit_data = pickle.loads(cached_logit)
                logger.info(f"SAM logit cache hit for {image_path}")
                return logit_data
            return None
        except Exception as e:
            logger.error(f"Error retrieving SAM logit cache: {e}")
            return None
    
    def set_sam_logit(self, image_path: str, click_signature: str, logit: np.ndarray, ttl: int = 1800):
        """设置SAM logit缓存"""
        try:
            image_hash = self._get_image_hash(image_path)
            cache_key = f"sam:logit:{image_hash}:{click_signature}"
            
            serialized_logit = pickle.dumps(logit)
            self.redis_client.setex(cache_key, ttl, serialized_logit)
            logger.info(f"SAM logit cached for {image_path}")
        except Exception as e:
            logger.error(f"Error setting SAM logit cache: {e}")
    
    # ==================== 用户会话管理 ====================
    
    def get_user_session(self, user_id: str) -> Optional[Dict[str, Any]]:
        """获取用户会话数据"""
        try:
            session_key = f"user:session:{user_id}"
            session_data = self.redis_client.hgetall(session_key)
            
            if session_data:
                # 将bytes转换为字符串
                decoded_session = {}
                for key, value in session_data.items():
                    key_str = key.decode('utf-8') if isinstance(key, bytes) else key
                    value_str = value.decode('utf-8') if isinstance(value, bytes) else value
                    # 尝试解析JSON
                    try:
                        decoded_session[key_str] = json.loads(value_str)
                    except:
                        decoded_session[key_str] = value_str
                
                logger.info(f"User session retrieved for {user_id}")
                return decoded_session
            return None
        except Exception as e:
            logger.error(f"Error retrieving user session: {e}")
            return None
    
    def set_user_session(self, user_id: str, session_data: Dict[str, Any], ttl: int = 86400):
        """设置用户会话数据"""
        try:
            session_key = f"user:session:{user_id}"
            
            # 序列化复杂数据类型
            serialized_data = {}
            for key, value in session_data.items():
                if isinstance(value, (dict, list)):
                    serialized_data[key] = json.dumps(value)
                else:
                    serialized_data[key] = str(value)
            
            self.redis_client.hset(session_key, mapping=serialized_data)
            self.redis_client.expire(session_key, ttl)
            logger.info(f"User session set for {user_id}, TTL: {ttl}s")
        except Exception as e:
            logger.error(f"Error setting user session: {e}")
    
    def update_user_session_field(self, user_id: str, field: str, value: Any):
        """更新用户会话中的特定字段"""
        try:
            session_key = f"user:session:{user_id}"
            
            if isinstance(value, (dict, list)):
                serialized_value = json.dumps(value)
            else:
                serialized_value = str(value)
            
            self.redis_client.hset(session_key, field, serialized_value)
            logger.info(f"User session field '{field}' updated for {user_id}")
        except Exception as e:
            logger.error(f"Error updating user session field: {e}")
    
    # ==================== 通用缓存方法 ====================
    
    def get_cache(self, key: str) -> Optional[Any]:
        """通用缓存获取"""
        try:
            cached_data = self.redis_client.get(key)
            if cached_data:
                return pickle.loads(cached_data)
            return None
        except Exception as e:
            logger.error(f"Error retrieving cache for key {key}: {e}")
            return None
    
    def set_cache(self, key: str, value: Any, ttl: int = 3600):
        """通用缓存设置"""
        try:
            serialized_data = pickle.dumps(value)
            self.redis_client.setex(key, ttl, serialized_data)
            logger.info(f"Cache set for key {key}, TTL: {ttl}s")
        except Exception as e:
            logger.error(f"Error setting cache for key {key}: {e}")
    
    def delete_cache(self, key: str):
        """删除缓存"""
        try:
            self.redis_client.delete(key)
            logger.info(f"Cache deleted for key {key}")
        except Exception as e:
            logger.error(f"Error deleting cache for key {key}: {e}")
    
    def clear_user_cache(self, user_id: str):
        """清除用户相关的所有缓存"""
        try:
            pattern = f"*{user_id}*"
            keys = self.redis_client.keys(pattern)
            if keys:
                self.redis_client.delete(*keys)
                logger.info(f"Cleared {len(keys)} cache entries for user {user_id}")
        except Exception as e:
            logger.error(f"Error clearing user cache: {e}")

# 全局Redis缓存实例
redis_cache = None

def init_redis_cache(host='localhost', port=6379, db=0, password=None):
    """初始化全局Redis缓存实例"""
    global redis_cache
    redis_cache = RedisCache(host=host, port=port, db=db, password=password)
    return redis_cache

def get_redis_cache() -> RedisCache:
    """获取全局Redis缓存实例"""
    global redis_cache
    if redis_cache is None:
        redis_cache = init_redis_cache()
    return redis_cache 