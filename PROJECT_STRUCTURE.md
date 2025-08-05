# 项目结构说明

## 📁 目录结构

```
SegTool_for_Jade/
├── 📁 front/                    # Vue3前端应用
│   ├── src/                    # 源代码
│   ├── public/                 # 静态资源
│   ├── package.json            # 前端依赖配置
│   └── README.md               # 前端说明文档
│
├── 📁 server/                  # SAM分割服务 (FastAPI)
│   ├── segment_anything/       # SAM模型相关代码
│   ├── main.py                 # 主服务入口
│   ├── requirements.txt        # Python依赖
│   └── checkpoints/            # 模型文件目录 (需手动下载)
│
├── 📁 yolo-server/             # YOLOv10检测服务
│   ├── ultralytics/            # YOLO框架代码
│   ├── app.py                  # Flask应用入口
│   ├── requirements.txt        # Python依赖
│   └── models/                 # YOLO模型文件
│
├── 📁 pdf_server/              # PDF解析服务 (Go)
│   ├── main.go                 # Go服务入口
│   ├── go.mod                  # Go模块配置
│   └── uploads/                # 上传文件目录
│
├── 📁 nginx/                   # Nginx配置
│   └── nginx.conf              # Nginx配置文件
│
├── 📁 docs/                    # 项目文档
│   ├── LOCAL_DEPLOYMENT.md     # 本地部署指南
│   ├── PHASE1_DEPLOYMENT.md    # Phase 1 部署指南
│   ├── PHASE2_DEPLOYMENT.md    # Phase 2 部署指南
│   ├── PHASE3_DEPLOYMENT.md    # Phase 3 部署指南
│   └── README_DEPLOYMENT.md    # 部署说明文档
│
├── 📁 scripts/                 # 部署和工具脚本
│   ├── quick_setup.py          # 快速设置脚本
│   ├── setup_local_environment.py  # 本地环境配置
│   └── start_services.py       # 服务启动脚本
│
├── 📁 config/                  # 配置文件
│   └── redis.conf              # Redis配置文件
│
├── 📁 database/                # 数据库相关文件
│   └── database_schema.sql     # 数据库架构文件
│
├── 📁 services/                # 微服务相关文件
│   ├── rocketmq_integration.py # RocketMQ集成
│   ├── rocketmq_message_handlers.py  # 消息处理器
│   └── requirements_rocketmq.txt     # RocketMQ依赖
│
├── README.md                   # 项目主说明文档
└── PROJECT_STRUCTURE.md        # 本文件 - 项目结构说明
```

## 🔧 各服务说明

### 前端服务 (front/)
- **技术栈**: Vue 3 + Element Plus + Axios
- **功能**: 用户界面，图像上传，分割结果展示
- **端口**: 8080 (开发环境)

### SAM分割服务 (server/)
- **技术栈**: FastAPI + PyTorch + SAM
- **功能**: 图像分割，提供分割API
- **端口**: 8006
- **模型**: 需要下载SAM模型文件到 checkpoints/ 目录

### YOLO检测服务 (yolo-server/)
- **技术栈**: Flask + Ultralytics + YOLOv10
- **功能**: 目标检测，自动识别图像中的对象
- **端口**: 5000
- **模型**: 自动下载或使用预训练模型

### PDF解析服务 (pdf_server/)
- **技术栈**: Go + Poppler
- **功能**: PDF文档解析，提取图像
- **端口**: 8081
- **依赖**: 需要安装 poppler-utils

### Nginx服务 (nginx/)
- **功能**: 反向代理，负载均衡
- **配置**: nginx.conf

## 📋 部署阶段

### Phase 1: Redis缓存层
- 添加Redis缓存支持
- 优化SAM embedding缓存
- 提升响应速度

### Phase 2: 微服务架构
- 服务解耦
- 消息队列集成
- 容器化部署

### Phase 3: 生产环境优化
- 性能优化
- 监控告警
- 高可用部署

## 🚀 快速启动

```bash
# 1. 环境准备
python scripts/setup_local_environment.py

# 2. 启动所有服务
python scripts/start_services.py

# 3. 访问应用
# 前端: http://localhost:8080
```

## 📝 注意事项

1. **模型文件**: SAM模型需要手动下载到 `server/checkpoints/` 目录
2. **环境依赖**: PDF服务需要安装 poppler-utils
3. **端口配置**: 确保各服务端口未被占用
4. **权限设置**: 确保上传目录有写入权限

## 🔍 故障排除

- 查看各服务的日志文件
- 检查端口占用情况
- 验证模型文件是否正确下载
- 确认环境依赖是否完整安装 