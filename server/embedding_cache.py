"""
SAM Embedding缓存管理器
支持在内存中缓存多个图片的embedding，解决单实例限制问题
"""

import time
import logging
import threading
from typing import Dict, Optional, Tuple
import numpy as np
import torch
from collections import OrderedDict

logger = logging.getLogger(__name__)

class EmbeddingCache:
    """多Embedding缓存管理器"""
    
    def __init__(self, max_cache_size: int = 10, max_memory_mb: int = 1024):
        """
        初始化embedding缓存
        
        Args:
            max_cache_size: 最大缓存数量
            max_memory_mb: 最大内存使用量(MB)
        """
        self.max_cache_size = max_cache_size
        self.max_memory_bytes = max_memory_mb * 1024 * 1024
        self.cache: OrderedDict[str, Dict] = OrderedDict()
        self.lock = threading.RLock()
        self.current_memory_bytes = 0
        
        # 统计信息
        self.stats = {
            'hits': 0,
            'misses': 0,
            'evictions': 0,
            'total_requests': 0
        }
    
    def _estimate_embedding_size(self, embedding: torch.Tensor) -> int:
        """估算embedding的内存大小"""
        if embedding is None:
            return 0
        # 假设float32，每个元素4字节
        return embedding.numel() * 4
    
    def _evict_if_needed(self, new_embedding_size: int):
        """如果需要，执行淘汰策略"""
        while (len(self.cache) >= self.max_cache_size or 
               self.current_memory_bytes + new_embedding_size > self.max_memory_bytes):
            
            if not self.cache:
                logger.warning("Cache is empty but still needs eviction")
                break
            
            # LRU淘汰：移除最久未使用的
            oldest_key = next(iter(self.cache))
            oldest_entry = self.cache.pop(oldest_key)
            
            # 释放内存
            old_size = self._estimate_embedding_size(oldest_entry.get('embedding'))
            self.current_memory_bytes -= old_size
            
            self.stats['evictions'] += 1
            logger.info(f"Evicted embedding for {oldest_key}, freed {old_size} bytes")
    
    def put(self, image_path: str, embedding: torch.Tensor, metadata: Dict = None):
        """
        存储embedding
        
        Args:
            image_path: 图片路径
            embedding: SAM embedding tensor
            metadata: 额外的元数据
        """
        with self.lock:
            embedding_size = self._estimate_embedding_size(embedding)
            
            # 检查是否需要淘汰
            self._evict_if_needed(embedding_size)
            
            # 存储embedding
            cache_entry = {
                'embedding': embedding,
                'size': embedding_size,
                'created_at': time.time(),
                'last_accessed': time.time(),
                'access_count': 0,
                'metadata': metadata or {}
            }
            
            self.cache[image_path] = cache_entry
            self.current_memory_bytes += embedding_size
            
            logger.info(f"Cached embedding for {image_path}, size: {embedding_size} bytes")
    
    def get(self, image_path: str) -> Optional[torch.Tensor]:
        """
        获取embedding
        
        Args:
            image_path: 图片路径
            
        Returns:
            embedding tensor or None
        """
        with self.lock:
            self.stats['total_requests'] += 1
            
            if image_path in self.cache:
                # 缓存命中
                entry = self.cache[image_path]
                entry['last_accessed'] = time.time()
                entry['access_count'] += 1
                
                # 移动到末尾（LRU）
                self.cache.move_to_end(image_path)
                
                self.stats['hits'] += 1
                logger.info(f"Embedding cache hit for {image_path}")
                return entry['embedding']
            else:
                # 缓存未命中
                self.stats['misses'] += 1
                logger.info(f"Embedding cache miss for {image_path}")
                return None
    
    def remove(self, image_path: str) -> bool:
        """移除指定的embedding"""
        with self.lock:
            if image_path in self.cache:
                entry = self.cache.pop(image_path)
                self.current_memory_bytes -= entry['size']
                logger.info(f"Removed embedding for {image_path}")
                return True
            return False
    
    def clear(self):
        """清空所有缓存"""
        with self.lock:
            self.cache.clear()
            self.current_memory_bytes = 0
            logger.info("Cleared all embeddings from cache")
    
    def get_stats(self) -> Dict:
        """获取缓存统计信息"""
        with self.lock:
            hit_rate = (self.stats['hits'] / max(1, self.stats['total_requests'])) * 100
            
            return {
                'cache_size': len(self.cache),
                'memory_usage_mb': self.current_memory_bytes / (1024 * 1024),
                'max_memory_mb': self.max_memory_bytes / (1024 * 1024),
                'hit_rate': hit_rate,
                'hits': self.stats['hits'],
                'misses': self.stats['misses'],
                'evictions': self.stats['evictions'],
                'total_requests': self.stats['total_requests']
            }
    
    def get_cache_info(self) -> Dict:
        """获取详细的缓存信息"""
        with self.lock:
            cache_info = []
            for image_path, entry in self.cache.items():
                cache_info.append({
                    'image_path': image_path,
                    'size_mb': entry['size'] / (1024 * 1024),
                    'created_at': entry['created_at'],
                    'last_accessed': entry['last_accessed'],
                    'access_count': entry['access_count']
                })
            
            return {
                'cache_entries': cache_info,
                'stats': self.get_stats()
            }


# 全局embedding缓存实例
_embedding_cache = None

def get_embedding_cache() -> EmbeddingCache:
    """获取全局embedding缓存实例"""
    global _embedding_cache
    if _embedding_cache is None:
        _embedding_cache = EmbeddingCache(
            max_cache_size=10,  # 最多缓存10个embedding
            max_memory_mb=1024  # 最多使用1GB内存
        )
    return _embedding_cache

def init_embedding_cache(max_cache_size: int = 10, max_memory_mb: int = 1024):
    """初始化embedding缓存"""
    global _embedding_cache
    _embedding_cache = EmbeddingCache(max_cache_size, max_memory_mb)
    return _embedding_cache 