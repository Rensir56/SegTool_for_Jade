-- 考古工具数据库设计
-- Phase 2: MySQL业务数据层

-- 创建数据库
CREATE DATABASE IF NOT EXISTS segtool_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE segtool_db;

-- 1. 用户管理表
CREATE TABLE users (
    id INT PRIMARY KEY AUTO_INCREMENT,
    user_id VARCHAR(64) UNIQUE NOT NULL COMMENT '用户唯一标识',
    username VARCHAR(100) DEFAULT NULL COMMENT '用户名（可选）',
    institution VARCHAR(200) DEFAULT NULL COMMENT '所属机构',
    user_type ENUM('researcher', 'student', 'admin') DEFAULT 'researcher' COMMENT '用户类型',
    last_login_at TIMESTAMP NULL COMMENT '最后登录时间',
    total_projects INT DEFAULT 0 COMMENT '总项目数',
    total_processing_time DECIMAL(10,2) DEFAULT 0 COMMENT '总处理时间（秒）',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_user_id (user_id),
    INDEX idx_institution (institution),
    INDEX idx_last_login (last_login_at)
) COMMENT '用户信息表';

-- 2. 项目管理表
CREATE TABLE projects (
    id INT PRIMARY KEY AUTO_INCREMENT,
    project_id VARCHAR(64) UNIQUE NOT NULL COMMENT '项目唯一标识',
    user_id VARCHAR(64) NOT NULL COMMENT '用户ID',
    pdf_filename VARCHAR(255) NOT NULL COMMENT 'PDF文件名',
    pdf_file_path VARCHAR(500) NOT NULL COMMENT 'PDF文件路径',
    pdf_file_size BIGINT DEFAULT 0 COMMENT 'PDF文件大小（字节）',
    total_pages INT NOT NULL COMMENT 'PDF总页数',
    processed_pages INT DEFAULT 0 COMMENT '已处理页数',
    status ENUM('uploading', 'processing', 'completed', 'failed', 'paused') DEFAULT 'uploading' COMMENT '项目状态',
    processing_start_time TIMESTAMP NULL COMMENT '开始处理时间',
    processing_end_time TIMESTAMP NULL COMMENT '完成处理时间',
    total_artifacts_extracted INT DEFAULT 0 COMMENT '提取的器物总数',
    error_message TEXT DEFAULT NULL COMMENT '错误信息',
    metadata JSON DEFAULT NULL COMMENT '项目元数据',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_user_id (user_id),
    INDEX idx_status (status),
    INDEX idx_created_at (created_at),
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
) COMMENT '项目管理表';

-- 3. 页面处理记录表
CREATE TABLE page_processing_logs (
    id INT PRIMARY KEY AUTO_INCREMENT,
    log_id VARCHAR(64) UNIQUE NOT NULL COMMENT '日志唯一标识',
    project_id VARCHAR(64) NOT NULL COMMENT '项目ID',
    page_number INT NOT NULL COMMENT '页面编号',
    model_type ENUM('yolo', 'sam') NOT NULL COMMENT '使用的模型类型',
    processing_status ENUM('pending', 'processing', 'completed', 'failed') DEFAULT 'pending' COMMENT '处理状态',
    processing_time DECIMAL(8,3) DEFAULT NULL COMMENT '处理耗时（秒）',
    input_image_path VARCHAR(500) DEFAULT NULL COMMENT '输入图片路径',
    output_result_path VARCHAR(500) DEFAULT NULL COMMENT '输出结果路径',
    artifacts_count INT DEFAULT 0 COMMENT '检测到的器物数量',
    confidence_score DECIMAL(5,3) DEFAULT NULL COMMENT '置信度分数',
    cache_hit BOOLEAN DEFAULT FALSE COMMENT '是否命中缓存',
    error_details TEXT DEFAULT NULL COMMENT '错误详情',
    performance_metrics JSON DEFAULT NULL COMMENT '性能指标',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_project_page (project_id, page_number),
    INDEX idx_model_type (model_type),
    INDEX idx_processing_status (processing_status),
    INDEX idx_processing_time (processing_time),
    INDEX idx_created_at (created_at),
    FOREIGN KEY (project_id) REFERENCES projects(project_id) ON DELETE CASCADE
) COMMENT '页面处理日志表';

-- 4. 器物检测结果表
CREATE TABLE artifact_detections (
    id INT PRIMARY KEY AUTO_INCREMENT,
    detection_id VARCHAR(64) UNIQUE NOT NULL COMMENT '检测结果唯一标识',
    project_id VARCHAR(64) NOT NULL COMMENT '项目ID',
    page_number INT NOT NULL COMMENT '页面编号',
    artifact_index INT NOT NULL COMMENT '器物在页面中的索引',
    artifact_type VARCHAR(100) DEFAULT NULL COMMENT '器物类型',
    bounding_box JSON NOT NULL COMMENT '边界框坐标 {x, y, width, height}',
    confidence_score DECIMAL(5,3) NOT NULL COMMENT '检测置信度',
    segmentation_mask_path VARCHAR(500) DEFAULT NULL COMMENT '分割掩码文件路径',
    extracted_image_path VARCHAR(500) DEFAULT NULL COMMENT '提取的器物图片路径',
    manual_verified BOOLEAN DEFAULT FALSE COMMENT '是否人工验证',
    manual_verified_by VARCHAR(64) DEFAULT NULL COMMENT '人工验证者',
    manual_verified_at TIMESTAMP NULL COMMENT '人工验证时间',
    artifact_description TEXT DEFAULT NULL COMMENT '器物描述',
    processing_metadata JSON DEFAULT NULL COMMENT '处理元数据',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_project_page (project_id, page_number),
    INDEX idx_artifact_type (artifact_type),
    INDEX idx_confidence (confidence_score),
    INDEX idx_manual_verified (manual_verified),
    INDEX idx_created_at (created_at),
    FOREIGN KEY (project_id) REFERENCES projects(project_id) ON DELETE CASCADE
) COMMENT '器物检测结果表';

-- 5. 用户操作日志表
CREATE TABLE user_activity_logs (
    id INT PRIMARY KEY AUTO_INCREMENT,
    activity_id VARCHAR(64) UNIQUE NOT NULL COMMENT '活动唯一标识',
    user_id VARCHAR(64) NOT NULL COMMENT '用户ID',
    project_id VARCHAR(64) DEFAULT NULL COMMENT '相关项目ID',
    activity_type ENUM(
        'login', 'logout', 'upload_pdf', 'start_processing', 
        'manual_segment', 'download_results', 'view_project',
        'delete_project', 'export_data'
    ) NOT NULL COMMENT '活动类型',
    activity_details JSON DEFAULT NULL COMMENT '活动详细信息',
    ip_address VARCHAR(45) DEFAULT NULL COMMENT 'IP地址',
    user_agent TEXT DEFAULT NULL COMMENT '用户代理',
    session_id VARCHAR(128) DEFAULT NULL COMMENT '会话ID',
    response_time DECIMAL(8,3) DEFAULT NULL COMMENT '响应时间（秒）',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_user_id (user_id),
    INDEX idx_project_id (project_id),
    INDEX idx_activity_type (activity_type),
    INDEX idx_created_at (created_at),
    INDEX idx_ip_address (ip_address),
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
    FOREIGN KEY (project_id) REFERENCES projects(project_id) ON DELETE SET NULL
) COMMENT '用户活动日志表';

-- 6. 系统性能监控表
CREATE TABLE system_performance_logs (
    id INT PRIMARY KEY AUTO_INCREMENT,
    metric_id VARCHAR(64) UNIQUE NOT NULL COMMENT '指标唯一标识',
    metric_type ENUM(
        'sam_processing_time', 'yolo_processing_time', 
        'cache_hit_rate', 'concurrent_users', 'memory_usage',
        'gpu_utilization', 'disk_usage', 'response_time'
    ) NOT NULL COMMENT '指标类型',
    metric_value DECIMAL(12,4) NOT NULL COMMENT '指标值',
    metric_unit VARCHAR(20) DEFAULT NULL COMMENT '指标单位',
    component VARCHAR(50) DEFAULT NULL COMMENT '组件名称（sam/yolo）',
    instance_id VARCHAR(100) DEFAULT NULL COMMENT '实例标识',
    additional_data JSON DEFAULT NULL COMMENT '附加数据',
    recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_metric_type (metric_type),
    INDEX idx_component (component),
    INDEX idx_recorded_at (recorded_at)
) COMMENT '系统性能监控表';

-- 7. 配置管理表
CREATE TABLE system_configurations (
    id INT PRIMARY KEY AUTO_INCREMENT,
    config_key VARCHAR(100) UNIQUE NOT NULL COMMENT '配置键',
    config_value TEXT NOT NULL COMMENT '配置值',
    config_type ENUM('string', 'integer', 'float', 'boolean', 'json') DEFAULT 'string' COMMENT '配置类型',
    description TEXT DEFAULT NULL COMMENT '配置描述',
    is_active BOOLEAN DEFAULT TRUE COMMENT '是否生效',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_config_key (config_key),
    INDEX idx_is_active (is_active)
) COMMENT '系统配置表';

-- 插入默认配置
INSERT INTO system_configurations (config_key, config_value, config_type, description) VALUES
('redis.cache.sam_embedding_ttl', '3600', 'integer', 'SAM embedding缓存TTL（秒）'),
('redis.cache.sam_logit_ttl', '1800', 'integer', 'SAM logit缓存TTL（秒）'),
('redis.cache.user_session_ttl', '86400', 'integer', '用户会话TTL（秒）'),
('processing.max_concurrent_jobs', '5', 'integer', '最大并发处理任务数'),
('yolo.confidence_threshold', '0.5', 'float', 'YOLO检测置信度阈值'),
('sam.max_points_per_request', '10', 'integer', 'SAM单次请求最大点击数'),
('system.cleanup_old_files_days', '30', 'integer', '文件清理周期（天）');

-- 创建视图：项目统计概览
CREATE VIEW project_statistics AS
SELECT 
    p.project_id,
    p.pdf_filename,
    p.user_id,
    p.total_pages,
    p.processed_pages,
    p.status,
    p.total_artifacts_extracted,
    TIMESTAMPDIFF(SECOND, p.processing_start_time, p.processing_end_time) as total_processing_seconds,
    COUNT(DISTINCT pl.page_number) as pages_with_logs,
    AVG(pl.processing_time) as avg_processing_time_per_page,
    SUM(CASE WHEN pl.cache_hit = 1 THEN 1 ELSE 0 END) / COUNT(*) * 100 as cache_hit_percentage,
    COUNT(ad.id) as total_detections,
    AVG(ad.confidence_score) as avg_confidence_score
FROM projects p
LEFT JOIN page_processing_logs pl ON p.project_id = pl.project_id
LEFT JOIN artifact_detections ad ON p.project_id = ad.project_id
GROUP BY p.project_id;

-- 创建视图：用户活跃度统计
CREATE VIEW user_activity_statistics AS
SELECT 
    u.user_id,
    u.username,
    u.institution,
    COUNT(DISTINCT p.project_id) as total_projects,
    COUNT(DISTINCT DATE(ual.created_at)) as active_days,
    MAX(ual.created_at) as last_activity,
    SUM(p.total_artifacts_extracted) as total_artifacts_extracted,
    AVG(TIMESTAMPDIFF(SECOND, p.processing_start_time, p.processing_end_time)) as avg_project_duration
FROM users u
LEFT JOIN projects p ON u.user_id = p.user_id
LEFT JOIN user_activity_logs ual ON u.user_id = ual.user_id
GROUP BY u.user_id; 