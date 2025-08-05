"""
MySQL数据库管理模块
Phase 2: 业务数据持久化和分析
"""

import mysql.connector
from mysql.connector import pooling
import json
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
import uuid
from contextlib import contextmanager

logger = logging.getLogger(__name__)

class DatabaseManager:
    """数据库管理器"""
    
    def __init__(self, host='localhost', port=3306, database='segtool_db', 
                 user='root', password='password', pool_size=10):
        """初始化数据库连接池"""
        self.config = {
            'host': host,
            'port': port,
            'database': database,
            'user': user,
            'password': password,
            'charset': 'utf8mb4',
            'autocommit': True,
            'pool_name': 'segtool_pool',
            'pool_size': pool_size,
            'pool_reset_session': True
        }
        
        try:
            self.pool = pooling.MySQLConnectionPool(**self.config)
            logger.info("Database connection pool initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize database pool: {e}")
            raise
    
    @contextmanager
    def get_connection(self):
        """获取数据库连接（上下文管理器）"""
        connection = None
        try:
            connection = self.pool.get_connection()
            yield connection
        except Exception as e:
            if connection:
                connection.rollback()
            logger.error(f"Database operation failed: {e}")
            raise
        finally:
            if connection:
                connection.close()
    
    def execute_query(self, query: str, params: tuple = None) -> List[Dict]:
        """执行查询并返回结果"""
        with self.get_connection() as conn:
            cursor = conn.cursor(dictionary=True)
            cursor.execute(query, params or ())
            result = cursor.fetchall()
            cursor.close()
            return result
    
    def execute_update(self, query: str, params: tuple = None) -> int:
        """执行更新操作并返回影响的行数"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params or ())
            affected_rows = cursor.rowcount
            cursor.close()
            conn.commit()
            return affected_rows
    
    # ==================== 用户管理 ====================
    
    def create_or_update_user(self, user_id: str, username: str = None, 
                             institution: str = None, user_type: str = 'researcher') -> bool:
        """创建或更新用户信息"""
        try:
            query = """
                INSERT INTO users (user_id, username, institution, user_type, last_login_at)
                VALUES (%s, %s, %s, %s, NOW())
                ON DUPLICATE KEY UPDATE
                    username = COALESCE(VALUES(username), username),
                    institution = COALESCE(VALUES(institution), institution),
                    user_type = VALUES(user_type),
                    last_login_at = NOW()
            """
            self.execute_update(query, (user_id, username, institution, user_type))
            logger.info(f"User {user_id} created/updated successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to create/update user {user_id}: {e}")
            return False
    
    def get_user_info(self, user_id: str) -> Optional[Dict[str, Any]]:
        """获取用户信息"""
        try:
            query = "SELECT * FROM users WHERE user_id = %s"
            result = self.execute_query(query, (user_id,))
            return result[0] if result else None
        except Exception as e:
            logger.error(f"Failed to get user info for {user_id}: {e}")
            return None
    
    def update_user_statistics(self, user_id: str, total_projects_delta: int = 0, 
                              processing_time_delta: float = 0) -> bool:
        """更新用户统计信息"""
        try:
            query = """
                UPDATE users 
                SET total_projects = total_projects + %s,
                    total_processing_time = total_processing_time + %s,
                    updated_at = NOW()
                WHERE user_id = %s
            """
            self.execute_update(query, (total_projects_delta, processing_time_delta, user_id))
            return True
        except Exception as e:
            logger.error(f"Failed to update user statistics for {user_id}: {e}")
            return False
    
    # ==================== 项目管理 ====================
    
    def create_project(self, user_id: str, pdf_filename: str, pdf_file_path: str,
                      pdf_file_size: int, total_pages: int, metadata: Dict = None) -> str:
        """创建新项目"""
        try:
            project_id = str(uuid.uuid4())
            query = """
                INSERT INTO projects (
                    project_id, user_id, pdf_filename, pdf_file_path, 
                    pdf_file_size, total_pages, metadata, status
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, 'uploading')
            """
            self.execute_update(query, (
                project_id, user_id, pdf_filename, pdf_file_path,
                pdf_file_size, total_pages, json.dumps(metadata) if metadata else None
            ))
            
            # 更新用户项目计数
            self.update_user_statistics(user_id, total_projects_delta=1)
            
            logger.info(f"Project {project_id} created for user {user_id}")
            return project_id
        except Exception as e:
            logger.error(f"Failed to create project: {e}")
            raise
    
    def update_project_status(self, project_id: str, status: str, 
                             error_message: str = None) -> bool:
        """更新项目状态"""
        try:
            if status == 'processing':
                query = """
                    UPDATE projects 
                    SET status = %s, processing_start_time = NOW(), error_message = NULL
                    WHERE project_id = %s
                """
                params = (status, project_id)
            elif status in ['completed', 'failed']:
                query = """
                    UPDATE projects 
                    SET status = %s, processing_end_time = NOW(), error_message = %s
                    WHERE project_id = %s
                """
                params = (status, error_message, project_id)
            else:
                query = """
                    UPDATE projects 
                    SET status = %s, error_message = %s
                    WHERE project_id = %s
                """
                params = (status, error_message, project_id)
            
            self.execute_update(query, params)
            logger.info(f"Project {project_id} status updated to {status}")
            return True
        except Exception as e:
            logger.error(f"Failed to update project status: {e}")
            return False
    
    def get_project_info(self, project_id: str) -> Optional[Dict[str, Any]]:
        """获取项目信息"""
        try:
            query = "SELECT * FROM projects WHERE project_id = %s"
            result = self.execute_query(query, (project_id,))
            if result:
                project = result[0]
                if project['metadata']:
                    project['metadata'] = json.loads(project['metadata'])
                return project
            return None
        except Exception as e:
            logger.error(f"Failed to get project info for {project_id}: {e}")
            return None
    
    def get_user_projects(self, user_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        """获取用户的项目列表"""
        try:
            query = """
                SELECT * FROM projects 
                WHERE user_id = %s 
                ORDER BY created_at DESC 
                LIMIT %s
            """
            return self.execute_query(query, (user_id, limit))
        except Exception as e:
            logger.error(f"Failed to get projects for user {user_id}: {e}")
            return []
    
    # ==================== 处理日志管理 ====================
    
    def log_page_processing(self, project_id: str, page_number: int, model_type: str,
                           processing_time: float = None, artifacts_count: int = 0,
                           confidence_score: float = None, cache_hit: bool = False,
                           input_image_path: str = None, output_result_path: str = None,
                           error_details: str = None, performance_metrics: Dict = None) -> str:
        """记录页面处理日志"""
        try:
            log_id = str(uuid.uuid4())
            status = 'completed' if error_details is None else 'failed'
            
            query = """
                INSERT INTO page_processing_logs (
                    log_id, project_id, page_number, model_type, processing_status,
                    processing_time, input_image_path, output_result_path,
                    artifacts_count, confidence_score, cache_hit, error_details,
                    performance_metrics
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            
            self.execute_update(query, (
                log_id, project_id, page_number, model_type, status,
                processing_time, input_image_path, output_result_path,
                artifacts_count, confidence_score, cache_hit, error_details,
                json.dumps(performance_metrics) if performance_metrics else None
            ))
            
            # 更新项目处理页数
            if status == 'completed':
                self.execute_update(
                    "UPDATE projects SET processed_pages = processed_pages + 1 WHERE project_id = %s",
                    (project_id,)
                )
            
            logger.info(f"Page processing logged: {log_id}")
            return log_id
        except Exception as e:
            logger.error(f"Failed to log page processing: {e}")
            raise
    
    def get_project_processing_logs(self, project_id: str) -> List[Dict[str, Any]]:
        """获取项目的处理日志"""
        try:
            query = """
                SELECT * FROM page_processing_logs 
                WHERE project_id = %s 
                ORDER BY page_number, created_at
            """
            logs = self.execute_query(query, (project_id,))
            for log in logs:
                if log['performance_metrics']:
                    log['performance_metrics'] = json.loads(log['performance_metrics'])
            return logs
        except Exception as e:
            logger.error(f"Failed to get processing logs for project {project_id}: {e}")
            return []
    
    # ==================== 器物检测结果管理 ====================
    
    def save_artifact_detection(self, project_id: str, page_number: int, artifact_index: int,
                               bounding_box: Dict, confidence_score: float,
                               artifact_type: str = None, segmentation_mask_path: str = None,
                               extracted_image_path: str = None, 
                               processing_metadata: Dict = None) -> str:
        """保存器物检测结果"""
        try:
            detection_id = str(uuid.uuid4())
            query = """
                INSERT INTO artifact_detections (
                    detection_id, project_id, page_number, artifact_index,
                    artifact_type, bounding_box, confidence_score,
                    segmentation_mask_path, extracted_image_path, processing_metadata
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            
            self.execute_update(query, (
                detection_id, project_id, page_number, artifact_index,
                artifact_type, json.dumps(bounding_box), confidence_score,
                segmentation_mask_path, extracted_image_path,
                json.dumps(processing_metadata) if processing_metadata else None
            ))
            
            # 更新项目器物总数
            self.execute_update(
                "UPDATE projects SET total_artifacts_extracted = total_artifacts_extracted + 1 WHERE project_id = %s",
                (project_id,)
            )
            
            logger.info(f"Artifact detection saved: {detection_id}")
            return detection_id
        except Exception as e:
            logger.error(f"Failed to save artifact detection: {e}")
            raise
    
    def get_project_artifacts(self, project_id: str) -> List[Dict[str, Any]]:
        """获取项目的器物检测结果"""
        try:
            query = """
                SELECT * FROM artifact_detections 
                WHERE project_id = %s 
                ORDER BY page_number, artifact_index
            """
            artifacts = self.execute_query(query, (project_id,))
            for artifact in artifacts:
                artifact['bounding_box'] = json.loads(artifact['bounding_box'])
                if artifact['processing_metadata']:
                    artifact['processing_metadata'] = json.loads(artifact['processing_metadata'])
            return artifacts
        except Exception as e:
            logger.error(f"Failed to get artifacts for project {project_id}: {e}")
            return []
    
    # ==================== 用户活动日志 ====================
    
    def log_user_activity(self, user_id: str, activity_type: str, project_id: str = None,
                         activity_details: Dict = None, ip_address: str = None,
                         user_agent: str = None, response_time: float = None) -> str:
        """记录用户活动"""
        try:
            activity_id = str(uuid.uuid4())
            session_id = f"session_{user_id}_{int(datetime.now().timestamp())}"
            
            query = """
                INSERT INTO user_activity_logs (
                    activity_id, user_id, project_id, activity_type,
                    activity_details, ip_address, user_agent, session_id, response_time
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            
            self.execute_update(query, (
                activity_id, user_id, project_id, activity_type,
                json.dumps(activity_details) if activity_details else None,
                ip_address, user_agent, session_id, response_time
            ))
            
            return activity_id
        except Exception as e:
            logger.error(f"Failed to log user activity: {e}")
            return ""
    
    # ==================== 系统性能监控 ====================
    
    def record_performance_metric(self, metric_type: str, metric_value: float,
                                 metric_unit: str = None, component: str = None,
                                 instance_id: str = None, additional_data: Dict = None):
        """记录系统性能指标"""
        try:
            metric_id = str(uuid.uuid4())
            query = """
                INSERT INTO system_performance_logs (
                    metric_id, metric_type, metric_value, metric_unit,
                    component, instance_id, additional_data
                ) VALUES (%s, %s, %s, %s, %s, %s, %s)
            """
            
            self.execute_update(query, (
                metric_id, metric_type, metric_value, metric_unit,
                component, instance_id,
                json.dumps(additional_data) if additional_data else None
            ))
        except Exception as e:
            logger.error(f"Failed to record performance metric: {e}")
    
    # ==================== 数据分析查询 ====================
    
    def get_system_statistics(self, days: int = 7) -> Dict[str, Any]:
        """获取系统统计信息"""
        try:
            since_date = datetime.now() - timedelta(days=days)
            
            # 基础统计
            stats_query = """
                SELECT 
                    COUNT(DISTINCT u.user_id) as total_users,
                    COUNT(DISTINCT p.project_id) as total_projects,
                    SUM(p.total_artifacts_extracted) as total_artifacts,
                    AVG(p.total_pages) as avg_pages_per_project,
                    COUNT(DISTINCT DATE(p.created_at)) as active_days
                FROM users u
                LEFT JOIN projects p ON u.user_id = p.user_id
                WHERE u.created_at >= %s OR p.created_at >= %s
            """
            basic_stats = self.execute_query(stats_query, (since_date, since_date))[0]
            
            # 性能统计
            perf_query = """
                SELECT 
                    metric_type,
                    AVG(metric_value) as avg_value,
                    MIN(metric_value) as min_value,
                    MAX(metric_value) as max_value,
                    COUNT(*) as sample_count
                FROM system_performance_logs
                WHERE recorded_at >= %s
                GROUP BY metric_type
            """
            perf_stats = self.execute_query(perf_query, (since_date,))
            
            # 缓存命中率
            cache_query = """
                SELECT 
                    model_type,
                    AVG(CASE WHEN cache_hit = 1 THEN 100 ELSE 0 END) as cache_hit_rate,
                    AVG(processing_time) as avg_processing_time
                FROM page_processing_logs
                WHERE created_at >= %s
                GROUP BY model_type
            """
            cache_stats = self.execute_query(cache_query, (since_date,))
            
            return {
                'basic_statistics': basic_stats,
                'performance_metrics': {stat['metric_type']: stat for stat in perf_stats},
                'cache_statistics': {stat['model_type']: stat for stat in cache_stats},
                'report_period_days': days,
                'generated_at': datetime.now().isoformat()
            }
        except Exception as e:
            logger.error(f"Failed to get system statistics: {e}")
            return {}

# 全局数据库管理器实例
db_manager = None

def init_database_manager(host='localhost', port=3306, database='segtool_db',
                         user='root', password='password', pool_size=10):
    """初始化全局数据库管理器"""
    global db_manager
    db_manager = DatabaseManager(host, port, database, user, password, pool_size)
    return db_manager

def get_database_manager() -> DatabaseManager:
    """获取全局数据库管理器实例"""
    global db_manager
    if db_manager is None:
        raise RuntimeError("Database manager not initialized. Call init_database_manager() first.")
    return db_manager 