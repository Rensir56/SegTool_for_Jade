# SegTool for Jade - 图像分割工具

一个基于SAM (Segment Anything Model) 和YOLOv10的智能图像分割工具，支持PDF文档处理和自动目标检测。

## 🏗️ 项目架构

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
└── PROJECT_STRUCTURE.md        # 项目结构说明文档
```

## 🚀 快速开始

### 1. 环境准备

```bash
# 克隆项目
git clone <repository-url>
cd SegTool_for_Jade

# 运行自动环境配置脚本
python setup_local_environment.py
```

### 2. 启动服务

```bash
# 一键启动所有服务
python start_services.py

# 或手动启动各个服务
cd server && uvicorn main:app --port 8006      # SAM服务
cd yolo-server && python main.py               # YOLO服务  
cd pdf_server && go run main.go                # PDF服务
cd front && npm run serve                      # 前端服务
```

### 3. 访问应用

- 前端界面: http://localhost:8080
- SAM API: http://localhost:8006
- YOLO API: http://localhost:5000
- PDF服务: http://localhost:8081

## 🛠️ 技术栈

### 前端
- Vue 3 + Element Plus
- Axios + LZ-String
- Canvas绘图

### 后端服务
- **SAM服务**: FastAPI + PyTorch
- **YOLO服务**: Flask + Ultralytics
- **PDF服务**: Go + Poppler

### 基础设施
- Redis缓存
- Nginx反向代理
- Docker容器化

## 📋 依赖模型

### SAM模型 (需手动下载到 server/checkpoints/)
- [ViT-H SAM model](https://dl.fbaipublicfiles.com/segment_anything/sam_vit_h_4b8939.pth) (推荐)
- [ViT-L SAM model](https://dl.fbaipublicfiles.com/segment_anything/sam_vit_l_0b3195.pth)
- [ViT-B SAM model](https://dl.fbaipublicfiles.com/segment_anything/sam_vit_b_01ec64.pth)

### YOLOv10模型
- 自动下载或使用预训练模型

## 🤝 贡献

请查看 [CONTRIBUTING.md](docs/CONTRIBUTING.md) 了解如何参与项目开发。

## 📄 许可证

本项目基于 MIT 许可证开源。



