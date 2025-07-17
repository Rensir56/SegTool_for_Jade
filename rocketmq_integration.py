"""
RocketMQ集成模块
实现GPU资源调度和流量削峰填谷
"""

import json
import time
import uuid
import logging
import threading
from typing import Dict, List, Optional, Callable, Any
from enum import Enum
from dataclasses import dataclass, asdict
import traceback
from concurrent.futures import ThreadPoolExecutor

# RocketMQ Python客户端
from rocketmq.client import Producer, PushConsumer, Message, ConsumeResult

logger = logging.getLogger(__name__)

class MessageType(Enum):
    """消息类型定义"""
    YOLO_DETECT = "YOLO_DETECT"
    SAM_SEGMENT = "SAM_SEGMENT"
    BATCH_PROCESS = "BATCH_PROCESS"
    PDF_EXTRACT = "PDF_EXTRACT"

class MessagePriority(Enum):
    """消息优先级"""
    LOW = 1
    NORMAL = 2
    HIGH = 3
    URGENT = 4

@dataclass
class SegmentMessage:
    """分割消息数据结构"""
    message_id: str
    message_type: MessageType
    user_id: str
    project_id: str
    payload: Dict[str, Any]
    priority: MessagePriority = MessagePriority.NORMAL
    max_retries: int = 3
    retry_count: int = 0
    created_at: float = None
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = time.time()
        if self.message_id is None:
            self.message_id = str(uuid.uuid4())

class RocketMQManager:
    """RocketMQ管理器"""
    
    def __init__(self, nameserver_address='localhost:9876', group_id='segtool_group'):
        """初始化RocketMQ管理器"""
        self.nameserver_address = nameserver_address
        self.group_id = group_id
        
        # Topic配置
        self.topics = {
            MessagePriority.URGENT: "segtool_urgent",
            MessagePriority.HIGH: "segtool_high", 
            MessagePriority.NORMAL: "segtool_normal",
            MessagePriority.LOW: "segtool_low"
        }
        
        # 死信队列Topic
        self.dlq_topic = "segtool_dlq"
        
        # 初始化生产者
        self.producer = None
        self.consumers = {}
        self.message_handlers: Dict[MessageType, Callable] = {}
        
        # 统计信息
        self.stats = {
            'messages_sent': 0,
            'messages_consumed': 0,
            'messages_failed': 0,
            'last_activity': time.time()
        }
        
        # 线程池
        self.executor = ThreadPoolExecutor(max_workers=10)
        
        self._init_producer()
        logger.info("RocketMQ Manager initialized")
    
    def _init_producer(self):
        """初始化生产者"""
        try:
            self.producer = Producer(group_id=f"{self.group_id}_producer")
            self.producer.set_name_server_address(self.nameserver_address)
            self.producer.start()
            logger.info("RocketMQ Producer started")
        except Exception as e:
            logger.error(f"Failed to initialize producer: {e}")
            raise
    
    def register_message_handler(self, message_type: MessageType, handler: Callable):
        """注册消息处理函数"""
        self.message_handlers[message_type] = handler
        logger.info(f"Registered handler for message type: {message_type.value}")
    
    def send_message(self, message: SegmentMessage) -> str:
        """发送消息到队列"""
        try:
            # 选择Topic
            topic = self.topics[message.priority]
            
            # 创建RocketMQ消息
            mq_message = Message(topic)
            mq_message.set_keys(message.message_id)
            mq_message.set_tags(message.message_type.value)
            mq_message.set_body(json.dumps(asdict(message)).encode('utf-8'))
            
            # 添加自定义属性
            mq_message.set_property("USER_ID", message.user_id)
            mq_message.set_property("PROJECT_ID", message.project_id)
            mq_message.set_property("CREATED_AT", str(message.created_at))
            mq_message.set_property("RETRY_COUNT", str(message.retry_count))
            
            # 发送消息
            result = self.producer.send_sync(mq_message)
            
            if result.status == 0:  # 发送成功
                self.stats['messages_sent'] += 1
                logger.info(f"Message {message.message_id} sent to {topic}")
                return message.message_id
            else:
                raise Exception(f"Send failed with status: {result.status}")
                
        except Exception as e:
            logger.error(f"Failed to send message: {e}")
            raise
    
    def send_yolo_detect_message(self, user_id: str, project_id: str, 
                                image_path: str, page_id: int, filename: str,
                                priority: MessagePriority = MessagePriority.NORMAL) -> str:
        """发送YOLO检测消息"""
        message = SegmentMessage(
            message_id=None,
            message_type=MessageType.YOLO_DETECT,
            user_id=user_id,
            project_id=project_id,
            payload={
                'image_path': image_path,
                'page_id': page_id,
                'filename': filename
            },
            priority=priority
        )
        return self.send_message(message)
    
    def send_sam_segment_message(self, user_id: str, project_id: str,
                               image_path: str, clicks: List[Dict],
                               priority: MessagePriority = MessagePriority.HIGH) -> str:
        """发送SAM分割消息"""
        message = SegmentMessage(
            message_id=None,
            message_type=MessageType.SAM_SEGMENT,
            user_id=user_id,
            project_id=project_id,
            payload={
                'image_path': image_path,
                'clicks': clicks
            },
            priority=priority
        )
        return self.send_message(message)
    
    def send_batch_process_message(self, user_id: str, project_id: str,
                                 pdf_filename: str, start_page: int, end_page: int,
                                 priority: MessagePriority = MessagePriority.NORMAL) -> str:
        """发送批量处理消息"""
        message = SegmentMessage(
            message_id=None,
            message_type=MessageType.BATCH_PROCESS,
            user_id=user_id,
            project_id=project_id,
            payload={
                'pdf_filename': pdf_filename,
                'start_page': start_page,
                'end_page': end_page
            },
            priority=priority
        )
        return self.send_message(message)
    
    def start_consumer(self, message_type: MessageType, consumer_group: str = None):
        """启动消息消费者"""
        if not consumer_group:
            consumer_group = f"{self.group_id}_{message_type.value.lower()}_consumer"
        
        try:
            consumer = PushConsumer(group_id=consumer_group)
            consumer.set_name_server_address(self.nameserver_address)
            
            # 订阅所有优先级的Topic，但只处理指定类型的消息
            for topic in self.topics.values():
                consumer.subscribe(topic, message_type.value)
            
            # 设置消息处理回调
            def message_listener(message):
                return self._handle_message(message, message_type)
            
            consumer.set_message_listener(message_listener)
            consumer.start()
            
            self.consumers[message_type] = consumer
            logger.info(f"Consumer started for {message_type.value}")
            
        except Exception as e:
            logger.error(f"Failed to start consumer for {message_type.value}: {e}")
            raise
    
    def _handle_message(self, mq_message, expected_type: MessageType) -> ConsumeResult:
        """处理接收到的消息"""
        try:
            # 解析消息
            message_data = json.loads(mq_message.body.decode('utf-8'))
            message_data['message_type'] = MessageType(message_data['message_type'])
            message_data['priority'] = MessagePriority(message_data['priority'])
            message = SegmentMessage(**message_data)
            
            # 检查消息类型
            if message.message_type != expected_type:
                logger.warning(f"Message type mismatch: expected {expected_type}, got {message.message_type}")
                return ConsumeResult.CONSUME_SUCCESS
            
            # 查找处理器
            handler = self.message_handlers.get(message.message_type)
            if not handler:
                logger.error(f"No handler registered for message type: {message.message_type}")
                self._send_to_dlq(mq_message, "No handler registered")
                return ConsumeResult.CONSUME_SUCCESS
            
            # 处理消息
            start_time = time.time()
            logger.info(f"Processing message {message.message_id} of type {message.message_type.value}")
            
            try:
                result = handler(message)
                processing_time = time.time() - start_time
                
                self.stats['messages_consumed'] += 1
                self.stats['last_activity'] = time.time()
                
                logger.info(f"Message {message.message_id} processed successfully in {processing_time:.2f}s")
                return ConsumeResult.CONSUME_SUCCESS
                
            except Exception as e:
                error_msg = f"Message processing failed: {str(e)}\n{traceback.format_exc()}"
                logger.error(f"Failed to process message {message.message_id}: {error_msg}")
                
                # 重试逻辑
                if message.retry_count < message.max_retries:
                    message.retry_count += 1
                    self._retry_message(message)
                    logger.info(f"Message {message.message_id} scheduled for retry ({message.retry_count}/{message.max_retries})")
                else:
                    self._send_to_dlq(mq_message, error_msg)
                    logger.error(f"Message {message.message_id} exceeded max retries, sent to DLQ")
                
                self.stats['messages_failed'] += 1
                return ConsumeResult.CONSUME_SUCCESS
                
        except Exception as e:
            logger.error(f"Failed to handle message: {e}")
            return ConsumeResult.RECONSUME_LATER
    
    def _retry_message(self, message: SegmentMessage):
        """重试消息"""
        try:
            # 延迟重试（指数退避）
            delay = min(300, 10 * (2 ** message.retry_count))  # 最大5分钟
            
            # 使用定时器延迟发送
            def delayed_send():
                time.sleep(delay)
                self.send_message(message)
            
            self.executor.submit(delayed_send)
            
        except Exception as e:
            logger.error(f"Failed to schedule retry for message {message.message_id}: {e}")
    
    def _send_to_dlq(self, original_message, error_reason: str):
        """发送消息到死信队列"""
        try:
            dlq_message = Message(self.dlq_topic)
            dlq_message.set_keys(original_message.keys)
            dlq_message.set_tags("FAILED")
            dlq_message.set_body(original_message.body)
            dlq_message.set_property("ERROR_REASON", error_reason)
            dlq_message.set_property("FAILED_AT", str(time.time()))
            
            self.producer.send_sync(dlq_message)
            logger.info(f"Message sent to DLQ: {original_message.keys}")
            
        except Exception as e:
            logger.error(f"Failed to send message to DLQ: {e}")
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            **self.stats,
            'topics': list(self.topics.values()),
            'registered_handlers': list(self.message_handlers.keys()),
            'active_consumers': list(self.consumers.keys())
        }
    
    def shutdown(self):
        """关闭RocketMQ连接"""
        try:
            # 关闭消费者
            for consumer in self.consumers.values():
                consumer.shutdown()
            
            # 关闭生产者
            if self.producer:
                self.producer.shutdown()
            
            # 关闭线程池
            self.executor.shutdown(wait=True)
            
            logger.info("RocketMQ Manager shutdown complete")
            
        except Exception as e:
            logger.error(f"Error during shutdown: {e}")

# 全局RocketMQ管理器实例
rocketmq_manager = None

def init_rocketmq_manager(nameserver_address='localhost:9876', group_id='segtool_group'):
    """初始化全局RocketMQ管理器"""
    global rocketmq_manager
    rocketmq_manager = RocketMQManager(nameserver_address, group_id)
    return rocketmq_manager

def get_rocketmq_manager() -> RocketMQManager:
    """获取全局RocketMQ管理器"""
    if rocketmq_manager is None:
        raise RuntimeError("RocketMQ manager not initialized. Call init_rocketmq_manager() first.")
    return rocketmq_manager 