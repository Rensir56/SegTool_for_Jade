import os
import shutil
from PIL import Image, ImageFilter
import numpy as np
from paddleocr import PaddleOCR
import re

# 创建保存裁剪图片的文件夹
def create_save_folder(path):
    if os.path.exists(path):
        shutil.rmtree(path)
    os.makedirs(path)

# 清理文本，确保只包含合法的文件名字符
def clean_text(text):
    # 移除非法字符
    cleaned_text = re.sub(r'[\\/:*?"<>|]', '', text)
    # 移除空白字符
    cleaned_text = cleaned_text.strip()
    # 限制文本长度
    max_length = 1000  # 设定最大长度为100个字符
    if len(cleaned_text) > max_length:
        cleaned_text = cleaned_text[:max_length]
    return cleaned_text

# 全局变量初始化
last_caption = "default_caption"

# 处理图片和坐标
def convert_to_coordinates(box, width, height):
    _, x_center, y_center, w, h = box
    x_min = (x_center - w / 2) * width
    y_min = (y_center - h / 2) * height
    x_max = (x_center + w / 2) * width
    y_max = (y_center + h / 2) * height
    return [x_min, y_min, x_max, y_max]

def calculate_iou(box1, box2):
    x1_min, y1_min, x1_max, y1_max = box1
    x2_min, y2_min, x2_max, y2_max = box2

    inter_x_min = max(x1_min, x2_min)
    inter_y_min = max(y1_min, y2_min)
    inter_x_max = min(x1_max, x2_max)
    inter_y_max = min(y1_max, y2_max)

    if inter_x_min < inter_x_max and inter_y_min < inter_y_max:
        inter_area = (inter_x_max - inter_x_min) * (inter_y_max - inter_y_min)
        box1_area = (x1_max - x1_min) * (y1_max - y1_min)
        box2_area = (x2_max - x2_min) * (y2_max - y2_min)
        iou = inter_area / float(box1_area + box2_area - inter_area)
        # 计算覆盖比率
        coverage_ratio = inter_area / min(box1_area, box2_area)
        return iou, coverage_ratio
    return 0, 0

def is_duplicate_box(box, detections, width, height, iou_threshold=0.7, coverage_threshold=0.5):
    if box[0] in [1, 3]:  # 类别为 1、3 的框不进行重复检测
        return False
    box_coords = convert_to_coordinates(box, width, height)
    for det in detections:
        if det[0] == 4 or box[0] == 4:  # 如果当前框或已有框的 class_id 为 4，跳过 IOU 计算
            continue
        det_coords = convert_to_coordinates(det, width, height)
        iou, coverage_ratio = calculate_iou(box_coords, det_coords)
        if iou > iou_threshold or coverage_ratio > coverage_threshold:
            return True
    return False

def filter_duplicate_boxes(detections, width, height, iou_threshold=0.7, coverage_threshold=0.5):
    unique_boxes = []
    for box in detections:
        if not is_duplicate_box(box, unique_boxes, width, height, iou_threshold, coverage_threshold):
            unique_boxes.append(box)
    return unique_boxes



def read_detections(txt_path):
    detections = []
    with open(txt_path, 'r') as file:
        for line in file:
            parts = line.strip().split(' ')
            box = [int(parts[0])] + [float(part) for part in parts[1:]]
            detections.append(box)
    return detections

def process_image(txt_folder, img_folder, save_folder):
    global last_caption
    ocr = PaddleOCR(use_angle_cls=True, lang="ch")
    create_save_folder(save_folder)
    for txt_file in os.listdir(txt_folder):
        if txt_file.endswith('.txt'):
            used_indices = set()
            txt_path = os.path.join(txt_folder, txt_file)
            img_name_base = os.path.splitext(txt_file)[0]
            img_name_png = img_name_base + '.png'
            img_name_jpg = img_name_base + '.jpg'
            img_path_png = os.path.join(img_folder, img_name_png)
            img_path_jpg = os.path.join(img_folder, img_name_jpg)
            img_path = None
            if os.path.exists(img_path_png):
                img_path = img_path_png
            elif os.path.exists(img_path_jpg):
                img_path = img_path_jpg
            else:
                print(f"Image not found: {img_path_png} or {img_path_jpg}")
                continue
            print(f"Processing: {img_path}")
            detections = read_detections(txt_path)
            img = Image.open(img_path)
            width, height = img.size
            detections = filter_duplicate_boxes(detections, width, height)  # 去重检测框
            overall_found = False
            ocr_texts = []
            for det in detections:
                if det[0] == 4:
                    overall_found = True
                    overall_bounds = [det[1:5], width, height]
                    elements_within_frame = filter_elements(detections, overall_bounds, width, height)
                    caption_text = ""
                    found_caption = False
                    for element in elements_within_frame:
                        if element[0] == 2:
                            caption_text = extract_caption_text(element, img, ocr, width, height)
                            if caption_text:
                                last_caption = caption_text
                                found_caption = True
                                break
                    if not found_caption and last_caption:
                        caption_text = increment_chinese_number(last_caption)
                    for element in elements_within_frame:
                        if element[0] != 2:
                            process_element(element, img, ocr, save_folder, width, height, caption_text, elements_within_frame, used_indices, ocr_texts)
            if not overall_found:
                print(f"No overall box found for {img_path}")
                process_items_without_overall_box(detections, img, ocr, save_folder, width, height, ocr_texts)
            # 保存该页的OCR结果到文本文件
            save_ocr_results(img_name_base, save_folder, ocr_texts)


# 处理没有整体框的情况
def process_items_without_overall_box(detections, img, ocr, save_folder, width, height, ocr_texts):
    items = [det for det in detections if det[0] == 0]
    captions = [det for det in detections if det[0] == 2]
    indices = [det for det in detections if det[0] == 1]
    for item in items:
        caption_text = find_closest_caption(item, captions, width, height, img, ocr)
        index_text, _ = find_closest_index_box(item, indices, width, height, img, ocr)
        if caption_text and index_text:
            filename = os.path.join(save_folder, f"{caption_text}_{index_text}.png")
            img_roi = crop_to_box(item, img, width, height)
            img_roi.save(filename)
            ocr_texts.append(f"{caption_text}_{index_text}")

# 寻找最近的图注
def find_closest_caption(item, captions, width, height, img, ocr):
    x_center, y_center = item[1], item[2]
    min_distance = float('inf')
    closest_caption = None
    for caption in captions:
        cap_x_center, cap_y_center = caption[1], caption[2]
        distance = np.sqrt((x_center - cap_x_center) ** 2 + (y_center - cap_y_center) ** 2)
        if distance < min_distance:
            min_distance = distance
            closest_caption = caption
    if closest_caption:
        img_roi = crop_to_box(closest_caption, img, width, height)
        ocr_result = ocr.ocr(np.array(img_roi), cls=True)
        if ocr_result and ocr_result[0]:
            return clean_text(ocr_result[0][0][1][0])
            print(f"OCR Text for caption: {text}")
    return "default"

# 中文数字映射
chinese_to_arabic = {
    'O': 0, '一': 1, '二': 2, '三': 3, '四': 4,
    '五': 5, '六': 6, '七': 7, '八': 8, '九': 9,
    '十': 10
}

def chinese_to_arabic_num(chinese_str):
    """将连续的中文数字（如“二一八”）直接转换为阿拉伯数字"""
    num_map = {'O': 0, '一': 1, '二': 2, '三': 3, '四': 4, '五': 5, '六': 6, '七': 7, '八': 8, '九': 9, '十': 10}
    result = 0
    for char in chinese_str:
        value = num_map.get(char)
        if value is None:
            continue  # Skip invalid characters
        result = result * 10 + value
    return result

def arabic_to_chinese(num):
    """将阿拉伯数字转换为不带单位的中文数字，例如218转换为“二一八”"""
    num_str = str(num)
    num_map = {0: 'O', 1: '一', 2: '二', 3: '三', 4: '四', 5: '五', 6: '六', 7: '七', 8: '八', 9: '九'}
    result = ''.join(num_map[int(digit)] for digit in num_str)
    return result

def increment_chinese_number(caption):
    """自动递增图注中的末尾连续中文数字"""
    # 匹配连续中文数字部分
    pattern = re.compile(r'[一二三四五六七八九O]+')
    match = pattern.search(caption)
    if match:
        chinese_num = match.group(0)
        arabic_num = chinese_to_arabic_num(chinese_num)
        incremented_num = arabic_num + 1
        new_chinese_num = arabic_to_chinese(incremented_num)
        return caption.replace(chinese_num, new_chinese_num)
    return caption

def intersection_over_union(det, overall_bounds, width, height):
    # 解析整体框的边界
    x_center, y_center, w, h = overall_bounds[0]
    box_x_min = (x_center - w / 2) * width
    box_y_min = (y_center - h / 2) * height
    box_x_max = (x_center + w / 2) * width
    box_y_max = (y_center + h / 2) * height
    # 解析元素的边界
    ele_x_center, ele_y_center, ele_w, ele_h = det[1:5]
    ele_x_min = (ele_x_center - ele_w / 2) * width
    ele_y_min = (ele_y_center - ele_h / 2) * height
    ele_x_max = (ele_x_center + ele_w / 2) * width
    ele_y_max = (ele_y_center + ele_h / 2) * height
    # 计算交集
    inter_x_min = max(box_x_min, ele_x_min)
    inter_y_min = max(box_y_min, ele_y_min)
    inter_x_max = min(box_x_max, ele_x_max)
    inter_y_max = min(box_y_max, ele_y_max)
    if inter_x_min < inter_x_max and inter_y_min < inter_y_max:
        # 交集区域
        inter_area = (inter_x_max - inter_x_min) * (inter_y_max - inter_y_min)
        # 元素的区域
        ele_area = (ele_x_max - ele_x_min) * (ele_y_max - ele_y_min)
        # 计算交集与元素面积的比例
        iou = inter_area / ele_area
        return iou >= 0.5
    return False

def filter_elements(detections, overall_bounds, width, height):
    filtered_elements = []
    for det in detections:
        if intersection_over_union(det, overall_bounds, width, height):
            filtered_elements.append(det)
    return filtered_elements

def extract_caption_text(det, img, ocr, width, height):
    img_roi = crop_to_box(det, img, width, height)
    ocr_result = ocr.ocr(np.array(img_roi), cls=True)
    if ocr_result and ocr_result[0] and len(ocr_result[0]) > 0 and len(ocr_result[0][0]) > 1:
        full_text = ocr_result[0][0][1][0]
        match = re.match(r"^[^\d]*", full_text)
        if match:
            return clean_text(match.group())
    print(f"OCR result is None or not as expected for box: {det}")
    return ""

# Global counter for default indexing
default_index_counter = 0

def increment_default_index():
    global default_index_counter
    default_index_counter += 1
    return f"default_{default_index_counter}"

def process_element(det, img, ocr, save_folder, width, height, caption_text, all_detections, used_indices, ocr_texts):
    img_roi = crop_to_box(det, img, width, height)
    filename = None
    if det[0] == 3:
        filename = os.path.join(save_folder, f"{caption_text}.png")
    elif det[0] == 0:
        idx_text, closest_index_box = find_closest_index_box(det, all_detections, width, height, img, ocr)
        if closest_index_box and idx_text not in used_indices:
            used_indices.add(idx_text)  # 标记此索引为已使用
            filename = os.path.join(save_folder, f"{caption_text}，{idx_text}.png")
            # 裁剪并保存序号框
            index_box_img_roi = crop_to_box(closest_index_box, img, width, height, enlarge=True)
            index_box_img_roi = enlarge_image(index_box_img_roi, 5)  # 放大序号框
        else:
            idx_text = increment_default_index()  # 使用自动递增的默认索引
            filename = os.path.join(save_folder, f"{caption_text}，{idx_text}.png")
    if filename:
        img_roi.save(filename)
        ocr_texts.append(filename)

def find_closest_index_box(det, all_detections, width, height, img, ocr):
    x_center, y_center, w, h = det[1], det[2], det[3], det[4]
    best_coverage = 0
    closest_index_box = None
    idx_text = None
    for idx_box in all_detections:
        if idx_box[0] == 1:
            idx_x_center, idx_y_center, idx_w, idx_h = idx_box[1], idx_box[2], idx_box[3], idx_box[4]
            inter_left = max(x_center - w / 2, idx_x_center - idx_w / 2)
            inter_top = max(y_center - h / 2, idx_y_center - idx_h / 2)
            inter_right = min(x_center + w / 2, idx_x_center + idx_w / 2)
            inter_bottom = min(y_center + h / 2, idx_y_center + idx_h / 2)
            if inter_right > inter_left and inter_bottom > inter_top:
                inter_area = (inter_right - inter_left) * (inter_bottom - inter_top)
                idx_area = idx_w * idx_h
                coverage = inter_area / idx_area
                if coverage > best_coverage and coverage > 0.5:
                    best_coverage = coverage
                    closest_index_box = idx_box
    if closest_index_box:
        idx_img_roi = crop_to_box(closest_index_box, img, width, height, enlarge=True)
        idx_img_roi = enlarge_image(idx_img_roi, 5)
        ocr_result = ocr.ocr(np.array(idx_img_roi), cls=True)
        print("OCR Results:", ocr_result)  # 打印 OCR 结果
        if ocr_result and ocr_result[0] and len(ocr_result[0]) > 0 and len(ocr_result[0][0]) > 1:
            idx_text = clean_text(ocr_result[0][0][1][0])
    if not idx_text:
        idx_text = increment_default_index()
    return idx_text, closest_index_box if closest_index_box else False

# 放大图片
def enlarge_image(image, scale_factor):
    # 获取原图尺寸
    original_size = image.size
    # 计算放大后的尺寸
    new_size = (int(original_size[0] * scale_factor), int(original_size[1] * scale_factor))
    # 放大图片
    enlarged_image = image.resize(new_size, Image.LANCZOS)  # 使用 LANCZOS 替代 ANTIALIAS
        # 锐化图像
    sharpened_image = enlarged_image.filter(ImageFilter.SHARPEN)

    return sharpened_image

def crop_to_box(box, img, width, height, enlarge=False):
    x_center, y_center, w, h = box[1:5]
    x_min = max(0, int((x_center - w / 2) * width))
    y_min = max(0, int((y_center - h / 2) * height))
    x_max = min(width, int((x_center + w / 2) * width))
    y_max = min(height, int((y_center + h / 2) * height))
    img_crop = img.crop((x_min, y_min, x_max, y_max))
    if enlarge:
        img_crop = img_crop.resize((img_crop.width * 5, img_crop.height * 5), Image.LANCZOS)
    return img_crop

def save_ocr_results(img_name_base, save_folder, ocr_texts):
    ocr_text_file = os.path.join(save_folder, f"{img_name_base}_ocr.txt")
    with open(ocr_text_file, 'w', encoding='utf-8') as f:
        for text in ocr_texts:
            f.write(text + '\n')

# 示例调用
# txt_folder = r'D:\CondaEnvStation\yolov10\yolov10\runs\detect\predict\labels'
# img_folder = r'D:\CondaEnvStation\yolov10\yolov10\runs\detect\predict'
# save_folder = r'D:\CondaEnvStation\yolov10\yolov10\runs\detect\predict\Result_single'
# txt_folder = r'D:\PaddleOCR\yolov10\runs\detect\predict2\labels'
# img_folder = r'D:\PaddleOCR\yolov10\runs\detect\predict2'
# save_folder = r'D:\PaddleOCR\ultralytics\weights\Result'
# txt_folder = r'D:\PaddleOCR\yolov10\runs\detect\predict\labels'
# img_folder = r'D:\PaddleOCR\yolov10\runs\detect\predict'
# save_folder = r'D:\PaddleOCR\ultralytics\weights\Result_Z'
# process_image(txt_folder, img_folder, save_folder)