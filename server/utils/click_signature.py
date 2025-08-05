"""
点击签名生成工具模块
用于生成点击序列的缓存键，支持坐标平滑化
"""

import hashlib
from typing import List, Dict


def generate_click_signature(clicks: List[Dict], grid_size: int = 20) -> str:
    """生成点击序列的签名，用于缓存键
    
    Args:
        clicks: 点击列表，每个元素包含x, y, clickType
        grid_size: 网格大小，用于坐标平滑化，默认20像素
    
    Returns:
        16位MD5哈希值作为缓存键
    
    Example:
        >>> clicks = [{"x": 100, "y": 200, "clickType": 1}]
        >>> signature = generate_click_signature(clicks)
        >>> print(signature)
        'a1b2c3d4e5f6g7h8'
    """
    if not clicks:
        return hashlib.md5("".encode()).hexdigest()[:16]
    
    # 坐标平滑化：将坐标量化到网格中
    smoothed_clicks = []
    for click in clicks:
        # 将坐标量化到网格中心
        x = (click['x'] // grid_size) * grid_size + grid_size // 2
        y = (click['y'] // grid_size) * grid_size + grid_size // 2
        smoothed_clicks.append({
            'x': x,
            'y': y, 
            'clickType': click['clickType']
        })
    
    # 按坐标排序，确保相同点击序列的一致性
    smoothed_clicks.sort(key=lambda x: (x['x'], x['y'], x['clickType']))
    
    # 生成签名字符串
    click_str = "_".join([f"{c['x']},{c['y']},{c['clickType']}" for c in smoothed_clicks])
    
    # 返回16位MD5哈希
    return hashlib.md5(click_str.encode()).hexdigest()[:16]


def generate_click_signature_full(clicks: List[Dict], grid_size: int = 20) -> str:
    """生成完整的点击签名（32位MD5）
    
    Args:
        clicks: 点击列表，每个元素包含x, y, clickType
        grid_size: 网格大小，用于坐标平滑化，默认20像素
    
    Returns:
        32位MD5哈希值作为缓存键
    """
    if not clicks:
        return hashlib.md5("".encode()).hexdigest()
    
    # 坐标平滑化：将坐标量化到网格中
    smoothed_clicks = []
    for click in clicks:
        # 将坐标量化到网格中心
        x = (click['x'] // grid_size) * grid_size + grid_size // 2
        y = (click['y'] // grid_size) * grid_size + grid_size // 2
        smoothed_clicks.append({
            'x': x,
            'y': y,
            'clickType': click['clickType']
        })
    
    # 按坐标排序，确保相同点击序列的一致性
    smoothed_clicks.sort(key=lambda x: (x['x'], x['y'], x['clickType']))
    
    # 生成签名字符串（使用分号分隔，与其他实现保持一致）
    click_str = ""
    for click in smoothed_clicks:
        click_str += f"{click['x']},{click['y']},{click['clickType']};"
    
    return hashlib.md5(click_str.encode()).hexdigest()


def test_smooth_signature():
    """测试平滑化签名的效果"""
    # 测试用例1：相同点击
    clicks1 = [{"x": 100, "y": 200, "clickType": 1}]
    clicks2 = [{"x": 100, "y": 200, "clickType": 1}]
    
    sig1 = generate_click_signature(clicks1)
    sig2 = generate_click_signature(clicks2)
    print(f"相同点击: {sig1 == sig2}")  # 应该为True
    
    # 测试用例2：轻微偏移（在网格内）
    clicks3 = [{"x": 105, "y": 205, "clickType": 1}]  # 偏移5像素
    sig3 = generate_click_signature(clicks3)
    print(f"轻微偏移: {sig1 == sig3}")  # 应该为True（网格大小为20）
    
    # 测试用例3：较大偏移（跨网格）
    clicks4 = [{"x": 130, "y": 230, "clickType": 1}]  # 偏移30像素
    sig4 = generate_click_signature(clicks4)
    print(f"较大偏移: {sig1 == sig4}")  # 应该为False
    
    # 测试用例4：多个点击
    clicks5 = [
        {"x": 100, "y": 200, "clickType": 1},
        {"x": 300, "y": 400, "clickType": 0}
    ]
    clicks6 = [
        {"x": 105, "y": 205, "clickType": 1},
        {"x": 305, "y": 405, "clickType": 0}
    ]
    sig5 = generate_click_signature(clicks5)
    sig6 = generate_click_signature(clicks6)
    print(f"多个点击: {sig5 == sig6}")  # 应该为True
    
    print(f"原始点击1: {clicks1}")
    print(f"平滑后1: {[(c['x'] // 20) * 20 + 10, (c['y'] // 20) * 20 + 10] for c in clicks1}")
    print(f"签名1: {sig1}")
    print(f"签名3: {sig3}")


if __name__ == "__main__":
    test_smooth_signature() 