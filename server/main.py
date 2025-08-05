import os
import shutil
import time
import hashlib
import logging

from PIL import Image
import numpy as np
import io
import base64
from segment_anything import SamPredictor, SamAutomaticMaskGenerator, sam_model_registry
from pycocotools import mask as mask_utils
import lzstring

from fastapi import FastAPI, UploadFile, File, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles

from redis_cache import init_redis_cache, get_redis_cache
from utils.click_signature import generate_click_signature

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 初始化模型
def init():
    # your model path
    # checkpoint = "checkpoints/sam_vit_b_01ec64.pth"
    # checkpoint = "checkpoints/sam_vit_h_4b8939.pth"
    checkpoint = "checkpoints/sam_vit_l_0b3195.pth"
    model_type = "vit_l"
    sam = sam_model_registry[model_type](checkpoint=checkpoint)
    sam.to(device='cuda')
    predictor = SamPredictor(sam)
    mask_generator = SamAutomaticMaskGenerator(sam)
    
    # 初始化Redis缓存
    try:
        init_redis_cache(host='localhost', port=6379, db=0)
        logger.info("Redis cache initialized successfully")
    except Exception as e:
        logger.warning(f"Redis cache initialization failed: {e}, fallback to memory cache")
    
    return predictor, mask_generator


predictor, mask_generator = init()

app = FastAPI()

app.mount("/upload", StaticFiles(directory="upload"), name="upload")

app.add_middleware(
    CORSMiddleware,
    allow_origins="*",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 保留全局变量作为fallback（当Redis不可用时）
last_image = ""
last_logit = None

def get_user_id_from_request(user_agent: str = Header(None), x_forwarded_for: str = Header(None)) -> str:
    """从请求头生成用户ID（简单实现，生产环境应使用JWT等）"""
    user_signature = f"{user_agent}_{x_forwarded_for}_{int(time.time() / 86400)}"  # 按天分组
    return hashlib.md5(user_signature.encode()).hexdigest()[:16]



# 上传文件接口
@app.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    print("上传图片", file.filename)
    file_path = os.path.join("upload", file.filename)
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    # 构造返回的图片 URL
    return JSONResponse(content={
        "src": f"http://10.22.125.155:8080/api/fastapi/upload/{file.filename}",
        "path": os.path.abspath(file_path)
    })

# 获取图片
@app.get("/img/{path}")
async def get_image(path: str):
    file_path = os.path.join("upload", path)
    return FileResponse(file_path)

# 处理分割请求
@app.post("/segment")
def process_image(body: dict, user_agent: str = Header(None), x_forwarded_for: str = Header(None)):
    global last_image, last_logit
    
    start_time = time.time()
    logger.info(f"Start processing image at {start_time}")
    
    path = body["path"]
    clicks = body["clicks"]
    user_id = get_user_id_from_request(user_agent, x_forwarded_for)
    click_signature = generate_click_signature(clicks)
    
    # 尝试使用Redis缓存
    redis_cache = None
    try:
        redis_cache = get_redis_cache()
    except Exception as e:
        logger.warning(f"Redis cache not available: {e}")
    
    is_first_segment = False
    
    # 检查SAM embedding缓存
    if redis_cache:
        cached_embedding = redis_cache.get_sam_embedding(path)
        if cached_embedding:
            # 从缓存恢复embedding状态
            logger.info("Using cached SAM embedding")
            # 注意：实际的embedding已经在predictor内部，这里只是标记
            if cached_embedding.get('image_path') != path:
                is_first_segment = True
        else:
            is_first_segment = True
            logger.info("SAM embedding cache miss, generating new embedding")
    else:
        # Fallback到原有逻辑
        if path != last_image:
            is_first_segment = True
    
    # 如果是第一次处理该图片，生成embedding
    if is_first_segment:
        pil_image = Image.open(path)
        np_image = np.array(pil_image)
        predictor.set_image(np_image)
        
        # 缓存embedding信息
        if redis_cache:
            embedding_data = {
                'image_path': path,
                'processed_at': time.time(),
                'image_shape': np_image.shape
            }
            redis_cache.set_sam_embedding(path, embedding_data, ttl=3600)  # 1小时缓存
        
        # Fallback
        last_image = path
        logger.info(f"Generated new embedding for {path}")
    
    # 检查logit缓存（基于点击历史）
    cached_logit = None
    if redis_cache and not is_first_segment:
        cached_logit = redis_cache.get_sam_logit(path, click_signature)
    
    # 准备预测参数
    input_points = []
    input_labels = []
    for click in clicks:
        input_points.append([click["x"], click["y"]])
        input_labels.append(click["clickType"])
    
    logger.info(f"input_points: {input_points}, input_labels: {input_labels}")
    input_points = np.array(input_points)
    input_labels = np.array(input_labels)
    
    # 执行预测
    masks, scores, logits = predictor.predict(
        point_coords=input_points,
        point_labels=input_labels,
        mask_input=cached_logit[None, :, :] if cached_logit is not None else (last_logit[None, :, :] if not is_first_segment and last_logit is not None else None),
        multimask_output=is_first_segment  # 第一次产生3个结果，选择最优的
    )
    
    # 选择最佳结果
    best = np.argmax(scores)
    best_logit = logits[best, :, :]
    best_mask = masks[best, :, :]
    
    # 缓存logit供下次使用
    if redis_cache:
        redis_cache.set_sam_logit(path, click_signature, best_logit, ttl=1800)  # 30分钟缓存
    
    # Fallback
    last_logit = best_logit
    
    # 编码mask结果
    source_mask = mask_utils.encode(np.asfortranarray(best_mask))["counts"]
    if isinstance(source_mask, bytes):
        source_mask = source_mask.decode("utf-8")
    
    lzs = lzstring.LZString()
    encoded = lzs.compressToEncodedURIComponent(source_mask)

    # 更新用户会话
    if redis_cache:
        session_data = {
            'last_processed_image': path,
            'last_processed_time': time.time(),
            'total_clicks': len(clicks)
        }
        redis_cache.set_user_session(user_id, session_data)
    
    processing_time = time.time() - start_time
    logger.info(f"Processing completed in {processing_time:.2f}s")
    
    return {
        "shape": best_mask.shape, 
        "mask": encoded,
        "processing_time": processing_time,
        "cache_hit": cached_logit is not None
    }

# 缓存监控接口
@app.get("/cache/stats")
def get_cache_stats():
    """获取缓存统计信息"""
    try:
        redis_cache = get_redis_cache()
        if redis_cache:
            stats = redis_cache.get_cache_performance_stats()
            return {
                "success": True,
                "stats": stats,
                "timestamp": time.time()
            }
        else:
            return {
                "success": False,
                "error": "Redis cache not available",
                "timestamp": time.time()
            }
    except Exception as e:
        logger.error(f"Error getting cache stats: {e}")
        return {
            "success": False,
            "error": str(e),
            "timestamp": time.time()
        }

@app.post("/cache/cleanup")
def cleanup_cache():
    """清理过期缓存"""
    try:
        redis_cache = get_redis_cache()
        if redis_cache:
            redis_cache.cleanup_expired_chunks()
            return {
                "success": True,
                "message": "Cache cleanup completed",
                "timestamp": time.time()
            }
        else:
            return {
                "success": False,
                "error": "Redis cache not available",
                "timestamp": time.time()
            }
    except Exception as e:
        logger.error(f"Error cleaning up cache: {e}")
        return {
            "success": False,
            "error": str(e),
            "timestamp": time.time()
        }

# 一键分割接口
@app.get("/everything")
def segment_everything(path: str):
    start_time = time.time()
    print("start segment_everything", start_time)
    pil_image = Image.open(path)
    np_image = np.array(pil_image)
    masks = mask_generator.generate(np_image)
    
    sorted_anns = sorted(masks, key=(lambda x: x['area']), reverse=True)
    img = np.zeros((sorted_anns[0]['segmentation'].shape[0], sorted_anns[0]['segmentation'].shape[1]), dtype=np.uint8)
    for idx, ann in enumerate(sorted_anns, 0):
        img[ann['segmentation']] = idx % 255 + 1  # color can only be in range [1, 255]
    # 压缩数组
    result = my_compress(img)
    end_time = time.time()
    print("finished segment_everything", end_time)
    print("time cost", end_time - start_time)
    return {"shape": img.shape, "mask": result}

# 自动生成mask
@app.get("/automatic_masks")
def automatic_masks(path: str):
    pil_image = Image.open(path)
    np_image = np.array(pil_image)
    mask = mask_generator.generate(np_image)
    
    sorted_anns = sorted(mask, key=(lambda x: x['area']), reverse=True)
    lzs = lzstring.LZString()
    res = []
    for ann in sorted_anns:
        m = ann['segmentation']
        source_mask = mask_utils.encode(m)['counts'].decode("utf-8")
        encoded = lzs.compressToEncodedURIComponent(source_mask)
        res.append({
            "encodedMask": encoded,
            "point_coord": ann['point_coords'][0],
        })
    return res

# 压缩图片辅助函数
def my_compress(img):
    result = []
    last_pixel = img[0][0]
    count = 0
    for line in img:
        for pixel in line:
            if pixel == last_pixel:
                count += 1
            else:
                result.append(count)
                result.append(int(last_pixel))
                last_pixel = pixel
                count = 1
    result.append(count)
    result.append(int(last_pixel))
    return result