# 考古工具项目本地部署指南

## 系统架构

本项目采用RocketMQ消息队列 + Redis缓存 + MySQL数据库的架构，支持YOLO自动检测和SAM手动分割功能。

### 核心组件
- **RocketMQ**: 消息队列，负责GPU资源调度和并发控制
- **Redis**: 缓存系统，存储SAM嵌入向量和YOLO检测结果
- **MySQL**: 业务数据库，存储用户、项目、处理日志等数据
- **SAM服务器**: 端口8080，集成RocketMQ的分割服务
- **YOLO服务器**: 端口8005，集成RocketMQ的检测服务
- **Vue.js前端**: 用户界面

## 系统要求

### 硬件要求
- GPU: NVIDIA显卡（推荐RTX 3060或以上）
- 内存: 16GB+ （推荐32GB）
- 存储: 50GB+ 可用空间
- 网络: 稳定的网络连接

### 软件要求
- **操作系统**: Linux/macOS/Windows
- **Python**: 3.8+
- **Java**: 1.8+ （RocketMQ需要）
- **MySQL**: 8.0+
- **Redis**: 6.0+
- **Node.js**: 16+ （前端构建）

## 安装步骤

### 1. 基础环境准备

#### 1.1 安装Java环境
```bash
# Ubuntu/Debian
sudo apt update
sudo apt install openjdk-8-jdk

# CentOS/RHEL
sudo yum install java-1.8.0-openjdk

# macOS
brew install openjdk@8
```

#### 1.2 安装MySQL
```bash
# Ubuntu/Debian
sudo apt install mysql-server

# CentOS/RHEL
sudo yum install mysql-server

# macOS
brew install mysql
```

#### 1.3 安装Redis
```bash
# Ubuntu/Debian
sudo apt install redis-server

# CentOS/RHEL
sudo yum install redis

# macOS
brew install redis
```

### 2. 下载并配置RocketMQ

#### 2.1 下载RocketMQ
```bash
cd /opt
wget https://archive.apache.org/dist/rocketmq/5.1.4/rocketmq-all-5.1.4-bin-release.zip
unzip rocketmq-all-5.1.4-bin-release.zip
mv rocketmq-all-5.1.4-bin-release rocketmq
```

#### 2.2 配置环境变量
```bash
# 添加到 ~/.bashrc 或 ~/.zshrc
export ROCKETMQ_HOME=/opt/rocketmq
export PATH=$PATH:$ROCKETMQ_HOME/bin
```

#### 2.3 创建RocketMQ配置文件
创建 `/opt/rocketmq/conf/broker-local.conf`:
```
brokerClusterName = DefaultCluster
brokerName = broker-a
brokerId = 0
deleteWhen = 04
fileReservedTime = 120
brokerRole = ASYNC_MASTER
flushDiskType = ASYNC_FLUSH
brokerIP1 = 127.0.0.1
listenPort = 10911
namesrvAddr = 127.0.0.1:9876
storePathRootDir = /opt/rocketmq/store
storePathCommitLog = /opt/rocketmq/store/commitlog
maxMessageSize = 67108864
```

### 3. 数据库初始化

#### 3.1 创建MySQL数据库
```sql
-- 登录MySQL
mysql -u root -p

-- 创建数据库和用户
CREATE DATABASE archaeological_tool DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'arch_user'@'localhost' IDENTIFIED BY 'arch_password_2024';
GRANT ALL PRIVILEGES ON archaeological_tool.* TO 'arch_user'@'localhost';
FLUSH PRIVILEGES;
```

#### 3.2 运行数据库迁移
```bash
cd server
python database_migration.py
```

### 4. Python环境配置

#### 4.1 创建虚拟环境
```bash
cd server
python -m venv venv
source venv/bin/activate  # Linux/macOS
# 或 venv\Scripts\activate  # Windows
```

#### 4.2 安装Python依赖
```bash
# SAM服务器依赖
pip install -r requirements.txt

# RocketMQ支持
pip install -r requirements_rocketmq.txt

# YOLO服务器依赖
cd ../yolo-server
pip install -r requirements.txt
```

### 5. 前端环境配置

```bash
cd front
npm install
npm run build
```

## 启动服务

### 方式一：使用统一启动脚本

```bash
# 启动所有服务
python start_services.py

# 只启动特定服务
python start_services.py --services nameserver,broker,redis,mysql

# 停止所有服务
python start_services.py --stop
```

### 方式二：手动启动

#### 1. 启动NameServer
```bash
cd /opt/rocketmq
nohup bin/mqnamesrv > logs/namesrv.log 2>&1 &
```

#### 2. 启动Broker
```bash
cd /opt/rocketmq
nohup bin/mqbroker -c conf/broker-local.conf > logs/broker.log 2>&1 &
```

#### 3. 启动Redis
```bash
redis-server
```

#### 4. 启动MySQL
```bash
sudo systemctl start mysql  # Linux
brew services start mysql   # macOS
```

#### 5. 启动SAM服务器
```bash
cd server
python main_rocketmq.py
```

#### 6. 启动YOLO服务器
```bash
cd yolo-server
python main_rocketmq.py
```

#### 7. 启动前端开发服务器（可选）
```bash
cd front
npm run serve
```

## 服务验证

### 1. 检查RocketMQ状态
```bash
# 检查NameServer
telnet 127.0.0.1 9876

# 检查Broker
/opt/rocketmq/bin/mqadmin clusterList -n 127.0.0.1:9876
```

### 2. 检查Redis连接
```bash
redis-cli ping
```

### 3. 检查MySQL连接
```bash
mysql -u arch_user -p -e "SELECT 1;"
```

### 4. 检查API服务
```bash
# SAM服务器
curl http://localhost:8080/health

# YOLO服务器
curl http://localhost:8005/health
```

## 配置文件

### 数据库配置 (server/config.py)
```python
DATABASE_CONFIG = {
    'host': 'localhost',
    'port': 3306,
    'database': 'archaeological_tool',
    'user': 'arch_user',
    'password': 'arch_password_2024'
}

REDIS_CONFIG = {
    'host': 'localhost',
    'port': 6379,
    'db': 0
}

ROCKETMQ_CONFIG = {
    'nameserver': '127.0.0.1:9876'
}
```

## 性能调优

### 1. RocketMQ调优
- 根据内存大小调整 `maxMessageSize`
- 设置合适的消息保留时间
- 配置消费者组数量

### 2. Redis调优
- 设置最大内存限制
- 配置LRU淘汰策略
- 启用持久化（可选）

### 3. MySQL调优
- 配置innodb_buffer_pool_size
- 调整连接数限制
- 启用查询缓存

## 故障排除

### 常见问题

1. **RocketMQ启动失败**
   - 检查Java版本
   - 确认端口9876和10911未被占用
   - 检查磁盘空间

2. **GPU内存不足**
   - 减小batch_size
   - 启用模型量化
   - 使用更小的模型

3. **数据库连接失败**
   - 检查MySQL服务状态
   - 验证用户权限
   - 确认防火墙设置

### 日志位置
- RocketMQ: `/opt/rocketmq/logs/`
- SAM服务器: `server/logs/`
- YOLO服务器: `yolo-server/logs/`
- MySQL: `/var/log/mysql/`
- Redis: `/var/log/redis/`

## 监控和维护

### 1. 系统监控
- CPU和内存使用率
- GPU利用率
- 网络连接数
- 磁盘使用情况

### 2. 业务监控
- 处理请求数量
- 响应时间分布
- 错误率统计
- 缓存命中率

### 3. 定期维护
- 清理过期日志
- 数据库备份
- 性能指标分析
- 系统更新

## 扩展建议

### 1. 负载均衡
- Nginx反向代理
- HAProxy负载均衡
- 多实例部署

### 2. 高可用性
- MySQL主从复制
- Redis集群
- RocketMQ集群

### 3. 容灾备份
- 定期数据备份
- 异地容灾
- 快速恢复方案 