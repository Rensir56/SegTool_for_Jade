#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据库迁移脚本
用于初始化MySQL数据库表结构和基础数据
"""

import mysql.connector
import logging
from datetime import datetime
import sys
import os

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 数据库配置
DATABASE_CONFIG = {
    'host': 'localhost',
    'port': 3306,
    'database': 'archaeological_tool',
    'user': 'arch_user',
    'password': 'arch_password_2024',
    'charset': 'utf8mb4',
    'collation': 'utf8mb4_unicode_ci'
}

class DatabaseMigration:
    """数据库迁移管理器"""
    
    def __init__(self):
        self.connection = None
        self.cursor = None
    
    def connect(self):
        """连接数据库"""
        try:
            self.connection = mysql.connector.connect(**DATABASE_CONFIG)
            self.cursor = self.connection.cursor()
            logger.info("数据库连接成功")
            return True
        except mysql.connector.Error as e:
            logger.error(f"数据库连接失败: {e}")
            return False
    
    def disconnect(self):
        """断开数据库连接"""
        if self.cursor:
            self.cursor.close()
        if self.connection:
            self.connection.close()
        logger.info("数据库连接已关闭")
    
    def execute_sql(self, sql: str, params=None):
        """执行SQL语句"""
        try:
            self.cursor.execute(sql, params)
            self.connection.commit()
            return True
        except mysql.connector.Error as e:
            logger.error(f"SQL执行失败: {e}")
            logger.error(f"SQL语句: {sql}")
            self.connection.rollback()
            return False
    
    def table_exists(self, table_name: str) -> bool:
        """检查表是否存在"""
        sql = """
        SELECT COUNT(*) 
        FROM information_schema.tables 
        WHERE table_schema = %s AND table_name = %s
        """
        self.cursor.execute(sql, (DATABASE_CONFIG['database'], table_name))
        return self.cursor.fetchone()[0] > 0
    
    def create_users_table(self):
        """创建用户表"""
        if self.table_exists('users'):
            logger.info("用户表已存在，跳过创建")
            return True
        
        sql = """
        CREATE TABLE users (
            id INT AUTO_INCREMENT PRIMARY KEY,
            username VARCHAR(50) NOT NULL UNIQUE,
            email VARCHAR(100) NOT NULL UNIQUE,
            password_hash VARCHAR(255) NOT NULL,
            full_name VARCHAR(100),
            institution VARCHAR(200),
            role ENUM('admin', 'researcher', 'student') DEFAULT 'researcher',
            is_active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            last_login TIMESTAMP NULL,
            INDEX idx_username (username),
            INDEX idx_email (email),
            INDEX idx_role (role),
            INDEX idx_created_at (created_at)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
        """
        
        if self.execute_sql(sql):
            logger.info("用户表创建成功")
            return True
        return False
    
    def create_projects_table(self):
        """创建项目表"""
        if self.table_exists('projects'):
            logger.info("项目表已存在，跳过创建")
            return True
        
        sql = """
        CREATE TABLE projects (
            id INT AUTO_INCREMENT PRIMARY KEY,
            name VARCHAR(200) NOT NULL,
            description TEXT,
            user_id INT NOT NULL,
            status ENUM('active', 'completed', 'archived') DEFAULT 'active',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            INDEX idx_user_id (user_id),
            INDEX idx_status (status),
            INDEX idx_created_at (created_at)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
        """
        
        if self.execute_sql(sql):
            logger.info("项目表创建成功")
            return True
        return False
    
    def create_images_table(self):
        """创建图像表"""
        if self.table_exists('images'):
            logger.info("图像表已存在，跳过创建")
            return True
        
        sql = """
        CREATE TABLE images (
            id INT AUTO_INCREMENT PRIMARY KEY,
            project_id INT NOT NULL,
            filename VARCHAR(255) NOT NULL,
            original_filename VARCHAR(255) NOT NULL,
            file_path VARCHAR(500) NOT NULL,
            file_size BIGINT NOT NULL,
            image_width INT NOT NULL,
            image_height INT NOT NULL,
            mime_type VARCHAR(100) NOT NULL,
            file_hash VARCHAR(64) NOT NULL,
            uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            processed_at TIMESTAMP NULL,
            processing_status ENUM('pending', 'processing', 'completed', 'failed') DEFAULT 'pending',
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
            INDEX idx_project_id (project_id),
            INDEX idx_filename (filename),
            INDEX idx_file_hash (file_hash),
            INDEX idx_processing_status (processing_status),
            INDEX idx_uploaded_at (uploaded_at)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
        """
        
        if self.execute_sql(sql):
            logger.info("图像表创建成功")
            return True
        return False
    
    def create_processing_logs_table(self):
        """创建处理日志表"""
        if self.table_exists('processing_logs'):
            logger.info("处理日志表已存在，跳过创建")
            return True
        
        sql = """
        CREATE TABLE processing_logs (
            id INT AUTO_INCREMENT PRIMARY KEY,
            image_id INT NOT NULL,
            user_id INT NOT NULL,
            processing_type ENUM('yolo_detection', 'sam_segmentation', 'batch_processing') NOT NULL,
            start_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            end_time TIMESTAMP NULL,
            status ENUM('started', 'completed', 'failed', 'cancelled') DEFAULT 'started',
            input_parameters JSON,
            output_data JSON,
            error_message TEXT,
            processing_time_ms INT,
            gpu_memory_used INT,
            cache_hit BOOLEAN DEFAULT FALSE,
            FOREIGN KEY (image_id) REFERENCES images(id) ON DELETE CASCADE,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            INDEX idx_image_id (image_id),
            INDEX idx_user_id (user_id),
            INDEX idx_processing_type (processing_type),
            INDEX idx_status (status),
            INDEX idx_start_time (start_time),
            INDEX idx_cache_hit (cache_hit)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
        """
        
        if self.execute_sql(sql):
            logger.info("处理日志表创建成功")
            return True
        return False
    
    def create_annotations_table(self):
        """创建标注表"""
        if self.table_exists('annotations'):
            logger.info("标注表已存在，跳过创建")
            return True
        
        sql = """
        CREATE TABLE annotations (
            id INT AUTO_INCREMENT PRIMARY KEY,
            image_id INT NOT NULL,
            user_id INT NOT NULL,
            annotation_type ENUM('yolo_bbox', 'sam_mask', 'manual_polygon') NOT NULL,
            coordinates JSON NOT NULL,
            label VARCHAR(100),
            confidence FLOAT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            is_validated BOOLEAN DEFAULT FALSE,
            validated_by INT NULL,
            validated_at TIMESTAMP NULL,
            metadata JSON,
            FOREIGN KEY (image_id) REFERENCES images(id) ON DELETE CASCADE,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (validated_by) REFERENCES users(id) ON DELETE SET NULL,
            INDEX idx_image_id (image_id),
            INDEX idx_user_id (user_id),
            INDEX idx_annotation_type (annotation_type),
            INDEX idx_label (label),
            INDEX idx_is_validated (is_validated),
            INDEX idx_created_at (created_at)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
        """
        
        if self.execute_sql(sql):
            logger.info("标注表创建成功")
            return True
        return False
    
    def create_system_metrics_table(self):
        """创建系统指标表"""
        if self.table_exists('system_metrics'):
            logger.info("系统指标表已存在，跳过创建")
            return True
        
        sql = """
        CREATE TABLE system_metrics (
            id INT AUTO_INCREMENT PRIMARY KEY,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            metric_type ENUM('performance', 'usage', 'error', 'cache') NOT NULL,
            service_name VARCHAR(50) NOT NULL,
            metric_name VARCHAR(100) NOT NULL,
            metric_value FLOAT NOT NULL,
            unit VARCHAR(20),
            tags JSON,
            INDEX idx_timestamp (timestamp),
            INDEX idx_metric_type (metric_type),
            INDEX idx_service_name (service_name),
            INDEX idx_metric_name (metric_name)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
        """
        
        if self.execute_sql(sql):
            logger.info("系统指标表创建成功")
            return True
        return False
    
    def create_user_sessions_table(self):
        """创建用户会话表"""
        if self.table_exists('user_sessions'):
            logger.info("用户会话表已存在，跳过创建")
            return True
        
        sql = """
        CREATE TABLE user_sessions (
            id INT AUTO_INCREMENT PRIMARY KEY,
            user_id INT NOT NULL,
            session_token VARCHAR(255) NOT NULL UNIQUE,
            ip_address VARCHAR(45) NOT NULL,
            user_agent TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            expires_at TIMESTAMP NOT NULL,
            last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            is_active BOOLEAN DEFAULT TRUE,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            INDEX idx_user_id (user_id),
            INDEX idx_session_token (session_token),
            INDEX idx_expires_at (expires_at),
            INDEX idx_is_active (is_active)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
        """
        
        if self.execute_sql(sql):
            logger.info("用户会话表创建成功")
            return True
        return False
    
    def create_views(self):
        """创建数据库视图"""
        views = {
            'user_stats': """
            CREATE OR REPLACE VIEW user_stats AS
            SELECT 
                u.id,
                u.username,
                u.full_name,
                u.role,
                COUNT(DISTINCT p.id) as project_count,
                COUNT(DISTINCT i.id) as image_count,
                COUNT(DISTINCT a.id) as annotation_count,
                COUNT(DISTINCT pl.id) as processing_count,
                MAX(pl.start_time) as last_activity
            FROM users u
            LEFT JOIN projects p ON u.id = p.user_id
            LEFT JOIN images i ON p.id = i.project_id
            LEFT JOIN annotations a ON i.id = a.image_id AND u.id = a.user_id
            LEFT JOIN processing_logs pl ON i.id = pl.image_id AND u.id = pl.user_id
            WHERE u.is_active = TRUE
            GROUP BY u.id, u.username, u.full_name, u.role;
            """,
            
            'daily_processing_stats': """
            CREATE OR REPLACE VIEW daily_processing_stats AS
            SELECT 
                DATE(start_time) as processing_date,
                processing_type,
                status,
                COUNT(*) as count,
                AVG(processing_time_ms) as avg_processing_time,
                SUM(CASE WHEN cache_hit = TRUE THEN 1 ELSE 0 END) as cache_hits,
                COUNT(*) - SUM(CASE WHEN cache_hit = TRUE THEN 1 ELSE 0 END) as cache_misses
            FROM processing_logs
            WHERE start_time >= DATE_SUB(CURRENT_DATE, INTERVAL 30 DAY)
            GROUP BY DATE(start_time), processing_type, status
            ORDER BY processing_date DESC, processing_type;
            """,
            
            'system_performance': """
            CREATE OR REPLACE VIEW system_performance AS
            SELECT 
                service_name,
                metric_name,
                DATE(timestamp) as metric_date,
                AVG(metric_value) as avg_value,
                MIN(metric_value) as min_value,
                MAX(metric_value) as max_value,
                COUNT(*) as sample_count
            FROM system_metrics
            WHERE timestamp >= DATE_SUB(CURRENT_DATE, INTERVAL 7 DAY)
            GROUP BY service_name, metric_name, DATE(timestamp)
            ORDER BY metric_date DESC, service_name, metric_name;
            """
        }
        
        success = True
        for view_name, view_sql in views.items():
            if self.execute_sql(view_sql):
                logger.info(f"视图 {view_name} 创建成功")
            else:
                success = False
        
        return success
    
    def insert_default_admin(self):
        """插入默认管理员用户"""
        # 检查是否已有管理员用户
        self.cursor.execute("SELECT COUNT(*) FROM users WHERE role = 'admin'")
        admin_count = self.cursor.fetchone()[0]
        
        if admin_count > 0:
            logger.info("已存在管理员用户，跳过创建")
            return True
        
        # 创建默认管理员（密码: admin123）
        import hashlib
        password_hash = hashlib.sha256('admin123'.encode()).hexdigest()
        
        sql = """
        INSERT INTO users (username, email, password_hash, full_name, role, is_active)
        VALUES (%s, %s, %s, %s, %s, %s)
        """
        params = (
            'admin',
            'admin@archaeological-tool.com',
            password_hash,
            '系统管理员',
            'admin',
            True
        )
        
        if self.execute_sql(sql, params):
            logger.info("默认管理员用户创建成功 (用户名: admin, 密码: admin123)")
            return True
        return False
    
    def run_migration(self):
        """运行完整的数据库迁移"""
        logger.info("开始数据库迁移...")
        
        if not self.connect():
            return False
        
        try:
            # 创建所有表
            tables = [
                self.create_users_table,
                self.create_projects_table,
                self.create_images_table,
                self.create_processing_logs_table,
                self.create_annotations_table,
                self.create_system_metrics_table,
                self.create_user_sessions_table
            ]
            
            for create_func in tables:
                if not create_func():
                    logger.error("表创建失败，停止迁移")
                    return False
            
            # 创建视图
            if not self.create_views():
                logger.warning("部分视图创建失败，但继续执行")
            
            # 插入默认数据
            if not self.insert_default_admin():
                logger.warning("默认管理员创建失败，但继续执行")
            
            logger.info("数据库迁移完成!")
            return True
            
        finally:
            self.disconnect()


def main():
    """主函数"""
    migration = DatabaseMigration()
    success = migration.run_migration()
    
    if success:
        logger.info("数据库初始化成功!")
        print("\n" + "="*50)
        print("数据库初始化完成!")
        print("默认管理员账户:")
        print("  用户名: admin")
        print("  密码: admin123")
        print("  邮箱: admin@archaeological-tool.com")
        print("="*50)
        sys.exit(0)
    else:
        logger.error("数据库初始化失败!")
        sys.exit(1)


if __name__ == '__main__':
    main() 