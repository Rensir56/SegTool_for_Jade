from flask import Flask, request, jsonify, send_from_directory, url_for
from flask_cors import CORS  # 引入CORS扩展
import os
import subprocess
import shutil
import atexit
from natsort import natsorted
from Newcut import process_image

app = Flask(__name__)

# 为整个应用启用CORS
CORS(app)

# 基础路径配置
base_detect_path = r'.\runs\detect'
model_path = "best.pt"
flag_clean = True  # 你可以在运行时设置这个开关

# 路由：上传并处理图像
@app.route('/uploadimg', methods=['POST'])
def upload_image():
    image_path = request.json.get('path')
    page_id = request.json.get('page')
    file_name = request.json.get('filename')
    if not image_path or not os.path.exists(image_path):
        return jsonify({'error': 'Invalid path'}), 400

    # 确定运行次数目录名称
    i = 1
    while os.path.exists(os.path.join(base_detect_path, f'predict{i}')):
        i += 1

    

    # 构建并执行命令
    command = [
        "yolo", "predict",
        f"model={model_path}",
        f"source={image_path}",
        "save_txt=True",
        "hide_labels=False",
        "hide_conf=False",
        "show_boxes=False",
        f"name=predict{page_id}",
        f"project={os.path.join(base_detect_path, file_name)}"
    ]
    print(command)
    # 使用 UTF-8 编码捕获输出
    result = subprocess.run(command, capture_output=True, text=True, encoding='utf-8')

    # 检查命令结果
    if result.returncode == 0:
        print("Command executed successfully:", result.stdout)
    else:
        return jsonify({'error': result.stderr}), 500

    return jsonify({'message': 'Image processed successfully'})

# 路由：分割并返回结果图像
@app.route('/segmentimg', methods=['POST'])
def segment_image():
    page_id = request.json.get('pageId')
    file_name = request.json.get('filename')
    if not page_id:
        return jsonify({'error': 'Missing pageId parameter'}), 400

    img_folder = os.path.join(os.path.join(base_detect_path, file_name), f'predict{page_id}')
    txt_folder = os.path.join(img_folder, 'labels')
    save_folder = os.path.join(img_folder, 'Result_single')

    if not os.path.exists(txt_folder):
        return jsonify({'error': 'Label folder not found'}), 404

    process_image(txt_folder, img_folder, save_folder)

    images = []
    for filename in natsorted(os.listdir(save_folder)):
        if filename.endswith('.jpg') or filename.endswith('.png'):
            image_url = url_for('serve_image',file_name=file_name, folder=f'predict{page_id}/Result_single', filename=filename, _external=True)
            images.append({
                'name': filename,
                'image': image_url
            })

    print(f"save_folder: {save_folder}")
    print(f"images: {images}")

    if not images:
        return jsonify({"images": []}), 200

    return jsonify({"images": images}), 200

# 构造文件路径
@app.route('/image/<path:file_name>/<path:folder>/<filename>')
def serve_image(file_name, folder, filename):
    folder_path = os.path.join(base_detect_path, file_name, folder)
    print(f"Requested folder_path: {folder_path}")
    print(f"Requested filename: {filename}")

    # 确保使用正确的路径分隔符
    if not os.path.exists(os.path.join(folder_path, filename)):
        return jsonify({'error': 'File not found'}), 404

    return send_from_directory(folder_path, filename)

# 清理：在服务器关闭时执行清理
@atexit.register
def clean_up():
    if flag_clean:  # 确保这个条件成立时才进行清理
        for item_name in os.listdir(base_detect_path):
            item_path = os.path.join(base_detect_path, item_name)
            if os.path.isdir(item_path):
                # 删除文件夹及其内容
                shutil.rmtree(item_path, ignore_errors=True)
            else:
                # 删除文件
                os.remove(item_path)

# 运行服务器
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8005, debug=True)
