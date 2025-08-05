# SegTool for Jade - 图像分割工具

一个基于SAM (Segment Anything Model) 和YOLOv10的智能图像分割工具，支持PDF文档处理和自动目标检测。

## 🏗️ 项目架构

```
SegTool_for_Jade/
├── 📁 front/                 # Vue3前端应用
├── 📁 server/               # SAM分割服务 (FastAPI)
├── 📁 yolo-server/          # YOLOv10检测服务
├── 📁 pdf_server/           # PDF解析服务 (Go)
├── 📁 nginx/                # Nginx配置
├── 📁 docs/                 # 项目文档
├── 📁 scripts/              # 部署和工具脚本
├── 📁 config/               # 配置文件
└── 📁 database/             # 数据库相关文件
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



