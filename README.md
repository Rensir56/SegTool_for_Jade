

### 准备工作

建议安装在虚拟机环境下，pdf-server依赖虚拟机环境运行

#### SAM前端依赖

```bash
npm install
or
yarn install
```

#### SAM后端依赖

前端使用了Vue3+ElementPlus（https://element-plus.org/zh-CN/#/zh-CN）+axios+lz-string

后端是fastapi（https://fastapi.tiangolo.com/），FastAPI 依赖 Python 3.8 及更高版本

安装 FastAPI 

```bash
pip install fastapi
pip install "uvicorn[standard]"
```

后端基于SAM的代码 https://github.com/facebookresearch/segment-anything

```bash
pip install --upgrade protobuf
pip install torchvision
pip install lzstring
pip install python-multipar
```

需要自行下载模型文件，保存到后端目录/checkpoints中

- **`default` or `vit_h`: [ViT-H SAM model.](https://dl.fbaipublicfiles.com/segment_anything/sam_vit_h_4b8939.pth)**
- `vit_l`: [ViT-L SAM model.](https://dl.fbaipublicfiles.com/segment_anything/sam_vit_l_0b3195.pth)
- `vit_b`: [ViT-B SAM model.](https://dl.fbaipublicfiles.com/segment_anything/sam_vit_b_01ec64.pth)

#### yolo后端依赖

```bash
pip install -r requirements.txt
pip install -e .
```

#### pdf后端依赖

```bash
sudo apt-get install poppler-utils
```

### 2.启动

在cmd或者pycharm终端，cd到后端server目录下，输入`uvicorn main:app --port 8006`，启动SAM服务器
在cmd终端，cd到后端pdf_server目录下，输入 `go run main.go`，启动pdf解析服务器
在cmd终端，cd到后端yolo-server目录下，输入 `python ./main.py`，启动yolo服务器
在cmd终端，cd到前端front目录下，输入 `npm run serve`，启动前端服务器



