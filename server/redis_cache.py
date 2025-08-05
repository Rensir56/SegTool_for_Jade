import redis
import pickle
import hashlib
import json
import gzip
import numpy as np
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
import logging
import os
import time

logger = logging.getLogger(__name__)

class RedisCache:
    """Redis缓存管理器，用于SAM embedding缓存和用户会话管理
    优化版本：解决大value问题，支持数据压缩和分片存储
    """
    
    # 配置常量
    MAX_VALUE_SIZE = 512 * 1024  # 512KB，超过此大小将分片存储
    COMPRESSION_THRESHOLD = 100 * 1024  # 100KB，超过此大小将压缩
    LOGIT_CHUNK_SIZE = 64 * 1024  # 64KB，logit分片大小
    
    def __init__(self, host='localhost', port=6379, db=0, password=None):
        """初始化Redis连接"""
        try:
            self.redis_client = redis.Redis(
                host=host, 
                port=port, 
                db=db, 
                password=password,
                decode_responses=False,  # 保持二进制数据
                socket_timeout=30,  # 增加超时时间
                socket_connect_timeout=10
            )
            self.redis_client.ping()  # 测试连接
            logger.info("Redis connection established successfully")
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            raise
    
    def _get_image_hash(self, image_path: str) -> str:
        """生成图片的唯一哈希值"""
        # 结合文件路径和修改时间生成hash
        file_stat = os.stat(image_path)
        content = f"{image_path}_{file_stat.st_mtime}_{file_stat.st_size}"
        return hashlib.md5(content.encode()).hexdigest()
    
    def _compress_data(self, data: bytes) -> bytes:
        """压缩数据"""
        return gzip.compress(data, compresslevel=6)
    
    def _decompress_data(self, compressed_data: bytes) -> bytes:
        """解压数据"""
        return gzip.decompress(compressed_data)
    
    def _serialize_with_compression(self, obj: Any) -> bytes:
        """序列化并压缩数据"""
        serialized = pickle.dumps(obj, protocol=pickle.HIGHEST_PROTOCOL)
        
        # 如果数据大于阈值，进行压缩
        if len(serialized) > self.COMPRESSION_THRESHOLD:
            compressed = self._compress_data(serialized)
            # 只有在压缩有效时才使用压缩数据
            if len(compressed) < len(serialized):
                return b'GZIP:' + compressed
            else:
                return b'PICKLE:' + serialized
        else:
            return b'PICKLE:' + serialized
    
    def _deserialize_with_compression(self, data: bytes) -> Any:
        """解压并反序列化数据"""
        if data.startswith(b'GZIP:'):
            compressed_data = data[5:]  # 去掉'GZIP:'前缀
            decompressed = self._decompress_data(compressed_data)
            return pickle.loads(decompressed)
        elif data.startswith(b'PICKLE:'):
            serialized_data = data[7:]  # 去掉'PICKLE:'前缀
            return pickle.loads(serialized_data)
        else:
            # 兼容旧格式
            return pickle.loads(data)
    
    def _split_large_data(self, key: str, data: bytes, ttl: int) -> bool:
        """将大数据分片存储"""
        try:
            data_size = len(data)
            if data_size <= self.MAX_VALUE_SIZE:
                return False
            
            # 计算分片数量
            num_chunks = (data_size + self.LOGIT_CHUNK_SIZE - 1) // self.LOGIT_CHUNK_SIZE
            
            # 存储分片信息
            chunk_info = {
                'num_chunks': num_chunks,
                'total_size': data_size,
                'created_at': time.time()
            }
            
            # 存储分片信息
            info_key = f"{key}:info"
            self.redis_client.setex(
                info_key, 
                ttl, 
                json.dumps(chunk_info).encode()
            )
            
            # 分片存储数据
            for i in range(num_chunks):
                start = i * self.LOGIT_CHUNK_SIZE
                end = min(start + self.LOGIT_CHUNK_SIZE, data_size)
                chunk = data[start:end]
                
                chunk_key = f"{key}:chunk:{i}"
                self.redis_client.setex(chunk_key, ttl, chunk)
            
            logger.info(f"Large data split into {num_chunks} chunks for key {key}")
            return True
            
        except Exception as e:
            logger.error(f"Error splitting large data for key {key}: {e}")
            return False
    
    def _get_large_data(self, key: str) -> Optional[bytes]:
        """获取分片存储的大数据"""
        try:
            # 检查是否存在分片信息
            info_key = f"{key}:info"
            info_data = self.redis_client.get(info_key)
            
            if not info_data:
                return None
            
            chunk_info = json.loads(info_data.decode())
            num_chunks = chunk_info['num_chunks']
            
            # 收集所有分片
            chunks = []
            for i in range(num_chunks):
                chunk_key = f"{key}:chunk:{i}"
                chunk_data = self.redis_client.get(chunk_key)
                if not chunk_data:
                    logger.error(f"Missing chunk {i} for key {key}")
                    return None
                chunks.append(chunk_data)
            
            # 合并分片
            combined_data = b''.join(chunks)
            logger.info(f"Retrieved large data with {num_chunks} chunks for key {key}")
            return combined_data
            
        except Exception as e:
            logger.error(f"Error retrieving large data for key {key}: {e}")
            return None
    
    # ==================== SAM Embedding 缓存 ====================
    
    def get_sam_embedding(self, image_path: str) -> Optional[Dict[str, Any]]:
        """获取SAM embedding缓存"""
        try:
            image_hash = self._get_image_hash(image_path)
            cache_key = f"sam:embedding:{image_hash}"
            
            cached_data = self.redis_client.get(cache_key)
            if cached_data:
                embedding_data = self._deserialize_with_compression(cached_data)
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
            
            serialized_data = self._serialize_with_compression(embedding_data)
            self.redis_client.setex(cache_key, ttl, serialized_data)
            logger.info(f"SAM embedding cached for {image_path}, TTL: {ttl}s")
        except Exception as e:
            logger.error(f"Error setting SAM embedding cache: {e}")
    
    def get_sam_logit(self, image_path: str, click_signature: str) -> Optional[np.ndarray]:
        """获取SAM logit缓存（基于点击历史）"""
        try:
            image_hash = self._get_image_hash(image_path)
            cache_key = f"sam:logit:{image_hash}:{click_signature}"
            
            # 首先尝试获取分片数据
            cached_data = self._get_large_data(cache_key)
            if not cached_data:
                # 尝试获取普通数据
                cached_data = self.redis_client.get(cache_key)
            
            if cached_data:
                logit_data = self._deserialize_with_compression(cached_data)
                logger.info(f"SAM logit cache hit for {image_path}")
                return logit_data
            return None
        except Exception as e:
            logger.error(f"Error retrieving SAM logit cache: {e}")
            return None
    
    def get_logit_cache_size(self, image_path: str, click_signature: str) -> Optional[int]:
        """获取logit缓存的大小（用于监控）"""
        try:
            image_hash = self._get_image_hash(image_path)
            cache_key = f"sam:logit:{image_hash}:{click_signature}"
            
            # 检查是否存在分片数据
            info_key = f"{cache_key}:info"
            info_data = self.redis_client.get(info_key)
            
            if info_data:
                chunk_info = json.loads(info_data.decode())
                return chunk_info.get('total_size', 0)
            else:
                # 检查普通数据
                cached_data = self.redis_client.get(cache_key)
                return len(cached_data) if cached_data else 0
                
        except Exception as e:
            logger.error(f"Error getting logit cache size: {e}")
            return None
    
    def set_sam_logit(self, image_path: str, click_signature: str, logit: np.ndarray, ttl: int = 1800):
        """设置SAM logit缓存（支持分片存储）"""
        try:
            image_hash = self._get_image_hash(image_path)
            cache_key = f"sam:logit:{image_hash}:{click_signature}"
            
            serialized_data = self._serialize_with_compression(logit)
            
            # 检查是否需要分片存储
            if len(serialized_data) > self.MAX_VALUE_SIZE:
                success = self._split_large_data(cache_key, serialized_data, ttl)
                if success:
                    logger.info(f"SAM logit cached (chunked) for {image_path}")
                    return
                else:
                    logger.warning(f"Failed to chunk large logit, falling back to normal storage")
            
            # 普通存储
            self.redis_client.setex(cache_key, ttl, serialized_data)
            logger.info(f"SAM logit cached for {image_path}")
        except Exception as e:
            logger.error(f"Error setting SAM logit cache: {e}")
    
    # ==================== 缓存统计和监控 ====================
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """获取缓存统计信息"""
        try:
            stats = {
                'total_keys': 0,
                'memory_usage': 0,
                'chunked_keys': 0,
                'compressed_keys': 0
            }
            
            # 统计SAM相关缓存
            sam_keys = self.redis_client.keys("sam:*")
            stats['total_keys'] += len(sam_keys)
            
            # 统计分片数据
            chunk_info_keys = self.redis_client.keys("*:info")
            stats['chunked_keys'] = len(chunk_info_keys)
            
            # 获取内存使用情况
            info = self.redis_client.info('memory')
            stats['memory_usage'] = info.get('used_memory_human', 'N/A')
            
            return stats
        except Exception as e:
            logger.error(f"Error getting cache stats: {e}")
            return {}
    
    def cleanup_expired_chunks(self):
        """清理过期的分片数据"""
        try:
            # 查找所有分片信息键
            info_keys = self.redis_client.keys("*:info")
            cleaned_count = 0
            
            for info_key in info_keys:
                # 检查分片信息是否过期
                if not self.redis_client.exists(info_key):
                    # 获取分片数量
                    info_data = self.redis_client.get(info_key)
                    if info_data:
                        chunk_info = json.loads(info_data.decode())
                        num_chunks = chunk_info['num_chunks']
                        
                        # 删除所有分片
                        chunk_keys = [f"{info_key.decode()[:-5]}:chunk:{i}" for i in range(num_chunks)]
                        self.redis_client.delete(*chunk_keys)
                        cleaned_count += num_chunks
            
            if cleaned_count > 0:
                logger.info(f"Cleaned up {cleaned_count} expired chunks")
                
        except Exception as e:
            logger.error(f"Error cleaning up expired chunks: {e}")
    
    def get_cache_performance_stats(self) -> Dict[str, Any]:
        """获取缓存性能统计"""
        try:
            stats = {
                'total_keys': 0,
                'chunked_keys': 0,
                'compressed_keys': 0,
                'memory_usage_mb': 0,
                'largest_logit_size_kb': 0,
                'avg_logit_size_kb': 0
            }
            
            # 统计SAM相关缓存
            sam_keys = self.redis_client.keys("sam:*")
            stats['total_keys'] = len(sam_keys)
            
            # 统计分片数据
            chunk_info_keys = self.redis_client.keys("*:info")
            stats['chunked_keys'] = len(chunk_info_keys)
            
            # 获取内存使用情况
            info = self.redis_client.info('memory')
            stats['memory_usage_mb'] = info.get('used_memory', 0) / (1024 * 1024)
            
            # 分析logit大小分布
            logit_keys = self.redis_client.keys("sam:logit:*")
            logit_sizes = []
            
            for key in logit_keys[:100]:  # 采样前100个
                if not key.endswith(b':info') and not b':chunk:' in key:
                    data = self.redis_client.get(key)
                    if data:
                        logit_sizes.append(len(data) / 1024)  # KB
            
            if logit_sizes:
                stats['largest_logit_size_kb'] = max(logit_sizes)
                stats['avg_logit_size_kb'] = sum(logit_sizes) / len(logit_sizes)
            
            return stats
        except Exception as e:
            logger.error(f"Error getting cache performance stats: {e}")
            return {}
    
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