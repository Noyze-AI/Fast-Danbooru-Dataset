# -*- coding: utf-8 -*-
from flask import Flask, render_template, request, jsonify, send_from_directory
import sys
import os
import re
import base64
import threading
import webbrowser
from PIL import Image
from danbooru_downloader import danbooru_downloader
from post_processor import PostProcessor

# 设置控制台编码
if sys.platform.startswith('win'):
    import locale
    try:
        locale.setlocale(locale.LC_ALL, 'zh_CN.UTF-8')
    except:
        try:
            locale.setlocale(locale.LC_ALL, 'Chinese_China.65001')
        except:
            pass

app = Flask(__name__)
app.config['SECRET_KEY'] = 'danbooru-simple-downloader'

# 全局实例
downloader = danbooru_downloader()
post_processor = PostProcessor()

@app.route('/')
def index():
    """主页面"""
    return render_template('index.html')

@app.route('/api/download', methods=['POST'])
def start_download():
    """开始下载"""
    try:
        data = request.get_json()
        tag = data.get('tag', '').strip()
        download_dir = data.get('download_dir', '').strip()
        max_count = data.get('max_count', 50)
        
        if not tag:
            return jsonify({
                'success': False,
                'message': '请输入标签'
            })
        
        if not download_dir:
            return jsonify({
                'success': False,
                'message': '请输入下载目录'
            })
        
        # 验证最大下载数量
        try:
            max_count = int(max_count)
            if max_count < 1 or max_count > 1000:
                return jsonify({
                    'success': False,
                    'message': '最大下载数量必须在1-1000之间'
                })
        except (ValueError, TypeError):
            max_count = 50
        
        success, message = downloader.start_download(tag, download_dir, max_count)
        
        return jsonify({
            'success': success,
            'message': message
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'请求处理出错: {str(e)}'
        })

@app.route('/api/status')
def get_status():
    """获取下载状态"""
    try:
        status = downloader.get_status()
        return jsonify(status)
    except Exception as e:
        return jsonify({
            'is_downloading': False,
            'status': f'获取状态出错: {str(e)}',
            'file_count': 0,
            'gallery_dl_available': False
        })

@app.route('/api/cancel', methods=['POST'])
def cancel_download():
    """取消下载"""
    try:
        success, message = downloader.cancel_download()
        
        return jsonify({
            'success': success,
            'message': message
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'取消下载出错: {str(e)}'
        })

@app.route('/api/manual_tag_process', methods=['POST'])
def manual_tag_process():
    """手动标签处理"""
    try:
        data = request.get_json()
        folder_path = data.get('folder_path', '').strip()
        remove_tags = data.get('remove_tags', [])
        remove_containing = data.get('remove_containing', [])
        add_tags = data.get('add_tags', [])
        
        if not folder_path:
            return jsonify({
                'success': False,
                'message': '请指定文件夹路径'
            })
        
        # 处理标签列表（去除空字符串）
        remove_tags = [tag.strip() for tag in remove_tags if tag.strip()]
        remove_containing = [tag.strip() for tag in remove_containing if tag.strip()]
        add_tags = [tag.strip() for tag in add_tags if tag.strip()]
        
        result = post_processor.manual_tag_process(
            folder_path, remove_tags, remove_containing, add_tags
        )
        
        success = result.success
        message = result.message
        
        return jsonify({
            'success': success,
            'message': message
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'手动标签处理出错: {str(e)}'
        })

@app.route('/api/auto_standardize', methods=['POST'])
def auto_standardize():
    """自动标准化标签（无需用户确认）"""
    try:
        data = request.get_json()
        folder_path = data.get('folder_path', '').strip()
        
        if not folder_path:
            return jsonify({
                'success': False,
                'message': '请指定文件夹路径'
            })
        
        # 扫描文件
        file_infos, unpaired_files = post_processor.scan_and_match_files(folder_path)
        
        if not file_infos:
            return jsonify({
                'success': False,
                'message': '未找到可处理的文件'
            })
        
        # 执行自动标准化
        result = post_processor.standardize_tags(folder_path, file_infos)
        
        success = result.success
        message = result.message
        
        return jsonify({
            'success': success,
            'message': message
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'自动标准化出错: {str(e)}'
        })

@app.route('/api/rename_files', methods=['POST'])
def rename_files():
    """批量重命名文件"""
    try:
        data = request.get_json()
        folder_path = data.get('folder_path', '').strip()
        
        if not folder_path:
            return jsonify({
                'success': False,
                'message': '请指定文件夹路径'
            })
            
        # 扫描文件
        file_infos, _ = post_processor.scan_and_match_files(folder_path)
        
        if not file_infos:
            return jsonify({
                'success': False,
                'message': '未找到可处理的文件'
            })
            
        # 执行重命名
        result = post_processor.rename_files(folder_path, file_infos)
        
        return jsonify({
            'success': result.success,
            'message': result.message
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'重命名出错: {str(e)}'
        })


@app.route('/api/dataset_structure')
def get_dataset_structure():
    """Get the file structure of the dataset directory"""
    dataset_dir = 'dataset'
    if not os.path.exists(dataset_dir):
        os.makedirs(dataset_dir)
        
    def natural_sort_key(s):
        """Natural sort key function"""
        return [int(text) if text.isdigit() else text.lower()
                for text in re.split('([0-9]+)', s)]
        
    def scan_dir(path):
        result = []
        try:
            with os.scandir(path) as it:
                # Use natural sort key
                entries = sorted(list(it), key=lambda e: (not e.is_dir(), natural_sort_key(e.name)))
                for entry in entries:
                    if entry.name.startswith('.'):
                        continue
                        
                    item = {
                        'name': entry.name,
                        'path': entry.path.replace('\\', '/'),
                        'type': 'directory' if entry.is_dir() else 'file'
                    }
                    
                    if entry.is_dir():
                        item['children'] = scan_dir(entry.path)
                        result.append(item)
                    elif entry.is_file() and entry.name.lower().endswith(('.png', '.jpg', '.jpeg', '.webp', '.gif', '.bmp')):
                        result.append(item)
        except Exception as e:
            print(f"Error scanning {path}: {e}")
        return result
        
    return jsonify(scan_dir(dataset_dir))

@app.route('/dataset/<path:filename>')
def serve_dataset_file(filename):
    """Serve files from the dataset directory"""
    return send_from_directory('dataset', filename)

@app.route('/api/get_image_tags', methods=['POST'])
def get_image_tags():
    """Get tags for a specific image"""
    try:
        data = request.get_json()
        image_path = data.get('image_path', '')
        
        if not image_path or not os.path.exists(image_path):
            return jsonify({'success': False, 'message': 'Image file not found'})
            
        # Determine potential text file paths
        base_path = os.path.splitext(image_path)[0]
        txt_path_1 = base_path + '.txt'
        txt_path_2 = image_path + '.txt'
        
        target_txt = None
        content = ""
        
        if os.path.exists(txt_path_1):
            target_txt = txt_path_1
        elif os.path.exists(txt_path_2):
            target_txt = txt_path_2
            
        if target_txt:
            try:
                with open(target_txt, 'r', encoding='utf-8') as f:
                    content = f.read()
            except Exception as e:
                return jsonify({'success': False, 'message': f'Error reading tags: {str(e)}'})
                
        return jsonify({
            'success': True, 
            'tags': content,
            'txt_path': target_txt
        })
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/api/save_image_tags', methods=['POST'])
def save_image_tags():
    """Save tags for a specific image"""
    try:
        data = request.get_json()
        image_path = data.get('image_path', '')
        tags = data.get('tags', '')
        
        if not image_path or not os.path.exists(image_path):
            return jsonify({'success': False, 'message': 'Image file not found'})
            
        # Determine text file path
        # If .txt exists, overwrite it. If .png.txt exists, overwrite it.
        # If neither, create .txt
        
        base_path = os.path.splitext(image_path)[0]
        txt_path_1 = base_path + '.txt'
        txt_path_2 = image_path + '.txt'
        
        target_txt = txt_path_1
        if os.path.exists(txt_path_2):
            target_txt = txt_path_2
            
        try:
            with open(target_txt, 'w', encoding='utf-8') as f:
                f.write(tags)
            return jsonify({'success': True, 'message': 'Tags saved successfully'})
        except Exception as e:
            return jsonify({'success': False, 'message': f'Error saving tags: {str(e)}'})
            
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})


@app.route('/api/batch_process_images', methods=['POST'])
def batch_process_images():
    """批量处理图片：缩放或添加背景"""
    try:
        data = request.get_json()
        folder_path = data.get('folder_path', '')
        action = data.get('action', '')
        params = data.get('params', {})
        
        # Adjust path if relative to dataset
        if folder_path.startswith('dataset/'):
            folder_path = os.path.join(os.getcwd(), folder_path)
        
        if not folder_path or not os.path.exists(folder_path):
            return jsonify({'success': False, 'message': '目标文件夹不存在'})
            
        processed_count = 0
        errors = []
        
        # Scan for images
        for filename in os.listdir(folder_path):
            file_path = os.path.join(folder_path, filename)
            if not os.path.isfile(file_path):
                continue
                
            ext = os.path.splitext(filename)[1].lower()
            if ext not in ('.png', '.jpg', '.jpeg', '.webp', '.bmp'):
                continue
                
            try:
                img = Image.open(file_path)
                original_format = img.format
                
                if action == 'resize':
                    max_edge = int(params.get('max_edge', 0))
                    if max_edge > 0:
                        width, height = img.size
                        # Force resize regardless of whether it's smaller or larger
                        if max(width, height) != max_edge:
                            scale_ratio = max_edge / max(width, height)
                            
                            new_width = int(width * scale_ratio)
                            new_height = int(height * scale_ratio)
                            
                            # Use LANCZOS for high quality scaling
                            img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
                            img.save(file_path, format=original_format)
                            processed_count += 1
                                
                elif action == 'add_background':
                    color_name = params.get('color', 'white')
                    # White or Gray (128, 128, 128)
                    bg_color = (255, 255, 255) if color_name == 'white' else (128, 128, 128)
                    
                    # Always convert to RGBA to ensure we have an alpha channel for composition
                    if img.mode != 'RGBA':
                        img = img.convert("RGBA")
                        
                    # Create background image
                    background = Image.new("RGBA", img.size, bg_color + (255,))
                    
                    # Paste original image over background
                    # Use alpha_composite for proper blending
                    final_img = Image.alpha_composite(background, img)
                    
                    # Convert to RGB to remove alpha channel (flatten)
                    final_img = final_img.convert("RGB")
                    
                    # Save as JPG
                    # Construct new filename with .jpg extension
                    base_name = os.path.splitext(file_path)[0]
                    new_file_path = base_name + ".jpg"
                    
                    final_img.save(new_file_path, "JPEG", quality=95)
                    
                    # If original file was not jpg, remove it
                    if file_path != new_file_path:
                        try:
                            os.remove(file_path)
                            # Also check if there was a .txt file for the original image and rename it if needed
                            # Naming convention 1: image.png -> image.txt
                            # Naming convention 2: image.png -> image.png.txt
                            
                            # Case 1: image.txt exists (remains valid for image.jpg)
                            # No change needed usually, unless user strictly wants matched extensions?
                            # Usually dataset loaders look for image_base_name.txt
                            
                            # Case 2: image.png.txt exists -> rename to image.jpg.txt
                            old_txt_path = file_path + ".txt"
                            if os.path.exists(old_txt_path):
                                new_txt_path = new_file_path + ".txt"
                                os.rename(old_txt_path, new_txt_path)
                                
                        except OSError as e:
                            print(f"Error removing original file {file_path}: {e}")
                            
                    processed_count += 1
                        
            except Exception as e:
                errors.append(f"{filename}: {str(e)}")
                print(f"Error processing {filename}: {e}")
                
        return jsonify({
            'success': True, 
            'message': f'成功处理 {processed_count} 张图片' + (f'，{len(errors)} 个错误' if errors else ''),
            'errors': errors
        })
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})


@app.route('/api/save_image', methods=['POST'])
def save_image():
    """保存编辑后的图片"""
    try:
        data = request.get_json()
        image_path = data.get('image_path', '')
        image_data = data.get('image_data', '')

        if not image_path or not os.path.exists(image_path):
            return jsonify({'success': False, 'message': 'Image file not found'})
        
        if not image_data:
            return jsonify({'success': False, 'message': 'No image data provided'})

        # Remove header of base64 string if present
        if ',' in image_data:
            header, encoded = image_data.split(",", 1)
        else:
            encoded = image_data
        
        try:
            with open(image_path, "wb") as fh:
                fh.write(base64.b64decode(encoded))
            return jsonify({'success': True, 'message': 'Image saved successfully'})
        except Exception as e:
            return jsonify({'success': False, 'message': f'Error saving image: {str(e)}'})
            
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})


def open_browser(port):
    """延迟打开浏览器"""
    import time
    time.sleep(1.5)  # 等待服务器启动
    try:
        webbrowser.open(f'http://localhost:{port}')
    except:
        pass  # 忽略浏览器打开失败

if __name__ == '__main__':
    port = 5678
    
    print(f"\n🌐 FastDanbooruDataset已启动")
    print(f"📍 访问地址: http://localhost:{port}")
    print(f"🛑 按 Ctrl+C 停止服务器\n")
    
    # 自动打开浏览器
    browser_thread = threading.Thread(target=open_browser, args=(port,))
    browser_thread.daemon = True
    browser_thread.start()
    
    # 启动Flask应用
    app.run(debug=False, host='0.0.0.0', port=port)