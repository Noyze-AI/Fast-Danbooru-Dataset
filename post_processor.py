#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import re
import shutil
import threading
from typing import List, Optional, Tuple, Set
from dataclasses import dataclass

import logging


@dataclass
class ProcessResult:
    """
    处理结果数据类
    """
    success: bool
    message: str
    processed_files: int = 0
    renamed_files: int = 0
    standardized_tags: int = 0
    unpaired_files: int = 0
    errors: List[str] = None
    
    def __post_init__(self):
        if self.errors is None:
            self.errors = []


@dataclass
class FileInfo:
    """
    文件信息数据类
    """
    image_path: Optional[str] = None
    text_path: Optional[str] = None
    base_name: str = ""
    is_paired: bool = False


class PostProcessor:
    """
    数据集后处理器
    
    负责处理下载完成后的图片和标签文件，包括：
    1. 文件配对和重命名
    2. 标签标准化处理
    3. 未配对文件管理
    """
    
    def __init__(self):
        """
        初始化后处理器
        """
        # 硬编码配置项
        self.rename_start_index = 1
        self.create_unpaired_folder = True
        self.log_level = 'INFO'
        self._lock = threading.Lock()
        self.logger = self._setup_logger()
        
        # 支持的图片格式
        self.image_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp'}
        # 支持的文本格式
        self.text_extensions = {'.txt'}
    
    def _setup_logger(self) -> logging.Logger:
        """
        设置日志记录器
        
        Returns:
            配置好的日志记录器
        """
        logger = logging.getLogger('PostProcessor')
        logger.setLevel(getattr(logging, self.log_level))
        
        # 避免重复添加处理器
        if not logger.handlers:
            # 控制台处理器
            console_handler = logging.StreamHandler()
            console_handler.setLevel(logging.INFO)
            console_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            console_handler.setFormatter(console_formatter)
            logger.addHandler(console_handler)
        
        return logger
    
    def scan_and_match_files(self, folder_path: str) -> Tuple[List[FileInfo], List[str]]:
        """
        扫描文件夹并匹配图片和文本文件
        
        支持两种配对模式：
        1. xxx.png 和 xxx.txt
        2. xxx.png 和 xxx.png.txt
        
        Args:
            folder_path: 要扫描的文件夹路径
            
        Returns:
            (配对的文件信息列表, 未配对的文件路径列表)
        """
        if not os.path.exists(folder_path):
            raise ValueError(f"文件夹不存在: {folder_path}")
        
        self.logger.info(f"开始扫描文件夹: {folder_path}")
        
        try:
            files = os.listdir(folder_path)
            
            # 分离图片和文本文件
            images = sorted([f for f in files if os.path.splitext(f)[1].lower() in self.image_extensions])
            texts = sorted([f for f in files if f.lower().endswith('.txt')])
            
            paired_files = []
            unpaired_images = []
            
            # 按照参考代码的逻辑进行匹配
            for img in images:
                base_name = os.path.splitext(img)[0]
                txt_name_1 = base_name + '.txt'  # xxx.txt 格式
                txt_name_2 = img + '.txt'        # xxx.png.txt 格式
                
                file_info = FileInfo(base_name=base_name)
                file_info.image_path = os.path.join(folder_path, img)
                
                # 优先匹配 xxx.txt 格式
                if txt_name_1 in texts:
                    file_info.text_path = os.path.join(folder_path, txt_name_1)
                    file_info.is_paired = True
                    self.logger.debug(f"匹配到基础文件名格式: {base_name}")
                # 其次匹配 xxx.png.txt 格式
                elif txt_name_2 in texts:
                    file_info.text_path = os.path.join(folder_path, txt_name_2)
                    file_info.is_paired = True
                    self.logger.debug(f"匹配到完整文件名格式: {img}")
                else:
                    file_info.is_paired = False
                    unpaired_images.append(file_info.image_path)
                
                paired_files.append(file_info)
            
            # 收集未配对的文本文件
            used_texts = set()
            for file_info in paired_files:
                if file_info.is_paired:
                    used_texts.add(os.path.basename(file_info.text_path))
            
            unpaired_files = []
            for txt in texts:
                if txt not in used_texts:
                    unpaired_files.append(os.path.join(folder_path, txt))
            
            paired_count = sum(1 for f in paired_files if f.is_paired)
            self.logger.info(f"扫描完成: 图片文件 {len(images)} 个, 配对文件 {paired_count} 个, 未配对图片 {len(unpaired_images)} 个, 未配对文本 {len(unpaired_files)} 个")
            
        except Exception as e:
            self.logger.error(f"扫描文件夹失败: {e}")
            raise
        
        return paired_files, unpaired_files
    
    def rename_files(self, folder_path: str, file_infos: List[FileInfo]) -> ProcessResult:
        """
        重命名文件为按序数字格式
        
        Args:
            folder_path: 文件夹路径
            file_infos: 文件信息列表
            
        Returns:
            处理结果
        """
        result = ProcessResult(success=False, message="")
        start_index = self.rename_start_index
        
        self.logger.info(f"开始重命名文件，起始序号: {start_index}")
        
        try:
            # 创建临时重命名映射，避免文件名冲突
            temp_renames = []
            final_renames = []
            
            for i, file_info in enumerate(file_infos):
                new_index = start_index + i
                
                # 处理图片文件
                if file_info.image_path:
                    old_image_path = file_info.image_path
                    image_ext = os.path.splitext(old_image_path)[1]
                    temp_image_name = f"temp_{new_index}{image_ext}"
                    final_image_name = f"{new_index}{image_ext}"
                    
                    temp_image_path = os.path.join(folder_path, temp_image_name)
                    final_image_path = os.path.join(folder_path, final_image_name)
                    
                    temp_renames.append((old_image_path, temp_image_path))
                    final_renames.append((temp_image_path, final_image_path))
                
                # 处理文本文件
                if file_info.text_path:
                    old_text_path = file_info.text_path
                    temp_text_name = f"temp_{new_index}.txt"
                    final_text_name = f"{new_index}.txt"
                    
                    temp_text_path = os.path.join(folder_path, temp_text_name)
                    final_text_path = os.path.join(folder_path, final_text_name)
                    
                    temp_renames.append((old_text_path, temp_text_path))
                    final_renames.append((temp_text_path, final_text_path))
            
            # 执行临时重命名
            for old_path, temp_path in temp_renames:
                try:
                    os.rename(old_path, temp_path)
                    result.renamed_files += 1
                except Exception as e:
                    error_msg = f"临时重命名失败: {old_path} -> {temp_path}, 错误: {e}"
                    self.logger.error(error_msg)
                    result.errors.append(error_msg)
            
            # 执行最终重命名
            for temp_path, final_path in final_renames:
                try:
                    os.rename(temp_path, final_path)
                except Exception as e:
                    error_msg = f"最终重命名失败: {temp_path} -> {final_path}, 错误: {e}"
                    self.logger.error(error_msg)
                    result.errors.append(error_msg)
            
            if not result.errors:
                result.success = True
                result.message = f"成功重命名 {result.renamed_files} 个文件"
                self.logger.info(result.message)
            else:
                result.message = f"重命名过程中出现 {len(result.errors)} 个错误"
                self.logger.warning(result.message)
        
        except Exception as e:
            error_msg = f"重命名过程失败: {e}"
            self.logger.error(error_msg)
            result.errors.append(error_msg)
            result.message = error_msg
        
        return result
    
    def auto_standardize_tags(self, tags_text: str) -> str:
        """
        自动标准化标签文本
        1. 以换行拆分tag
        2. 合并为逗号分隔字符串
        3. 替换 - 和 _
        4. 对未转义括号加转义
        
        Args:
            tags_text: 原始标签文本
            
        Returns:
            标准化后的标签文本
        """
        if not tags_text or not tags_text.strip():
            return ""
        
        # 1. 以换行符拆分tag（同时支持逗号分隔）
        # 先按换行符分割，再按逗号分割
        lines = tags_text.split('\n')
        tags = []
        for line in lines:
            if ',' in line:
                # 如果行中包含逗号，按逗号分割
                tags.extend([tag.strip() for tag in line.split(',') if tag.strip()])
            else:
                # 否则整行作为一个标签
                if line.strip():
                    tags.append(line.strip())
        
        
        # 3. 替换 - 和 _
        tags = [tag.replace('_', ' ').replace('-', ' ') for tag in tags]
        
        # 4. 对未转义括号加转义
        processed_tags = []
        for tag in tags:
            # 只对未转义的括号进行转义
            tag = re.sub(r'(?<!\\)\(', r'\(', tag)  # 转义未转义的左括号
            tag = re.sub(r'(?<!\\)\)', r'\)', tag)  # 转义未转义的右括号
            processed_tags.append(tag)
        
        # 去除空白和去重
        tags = [tag.strip() for tag in processed_tags if tag.strip()]
        seen = set()
        unique_tags = []
        for tag in tags:
            if tag not in seen:
                seen.add(tag)
                unique_tags.append(tag)
        
        # 2. 合并为逗号分隔字符串
        return ', '.join(unique_tags)
    
    def clean_and_edit_tags(self, tags_text: str, remove_tags: Set[str] = None, 
                           remove_containing: Set[str] = None, add_tags: Set[str] = None) -> str:
        """
        清洗和编辑标签文本
        
        Args:
            tags_text: 原始标签文本
            remove_tags: 要删除的标签集合
            remove_containing: 要删除包含特定内容的标签集合
            add_tags: 要添加的标签集合
            
        Returns:
            处理后的标签文本
        """
        if not tags_text or not tags_text.strip():
            return ""
        
        # 初始化集合
        remove_tags = remove_tags or set()
        remove_containing = remove_containing or set()
        add_tags = add_tags or set()
        
        # 分割标签
        tags = [tag.strip() for tag in tags_text.split(',') if tag.strip()]
        
        # 精确删除标签
        if remove_tags:
            tags = [tag for tag in tags if tag not in remove_tags]
        
        # 删除包含特定内容的标签
        if remove_containing:
            filtered_tags = []
            for tag in tags:
                should_remove = False
                for contain_text in remove_containing:
                    if contain_text in tag:
                        should_remove = True
                        break
                if not should_remove:
                    filtered_tags.append(tag)
            tags = filtered_tags
        
        # 添加新标签（避免重复）
        if add_tags:
            existing_tags_set = set(tags)
            for new_tag in add_tags:
                if new_tag not in existing_tags_set:
                    tags.append(new_tag)
        
        # 去除空白和去重
        tags = [tag.strip() for tag in tags if tag.strip()]
        seen = set()
        unique_tags = []
        for tag in tags:
            if tag not in seen:
                seen.add(tag)
                unique_tags.append(tag)
        
        # 返回逗号分隔的格式
        return ', '.join(unique_tags)
    
    def standardize_tags(self, folder_path: str, file_infos: List[FileInfo]) -> ProcessResult:
        """
        标准化标签文件
        
        Args:
            folder_path: 文件夹路径
            file_infos: 文件信息列表
            
        Returns:
            处理结果
        """
        result = ProcessResult(success=False, message="")
        
        self.logger.info("开始标准化标签文件")
        
        try:
            for file_info in file_infos:
                if not file_info.text_path or not os.path.exists(file_info.text_path):
                    continue
                
                try:
                    # 读取原始标签
                    with open(file_info.text_path, 'r', encoding='utf-8') as f:
                        original_content = f.read()
                    
                    # 自动标准化处理（无需用户确认）
                    standardized_content = self.auto_standardize_tags(original_content)
                    
                    # 写回文件
                    with open(file_info.text_path, 'w', encoding='utf-8') as f:
                        f.write(standardized_content)
                    
                    result.standardized_tags += 1
                    
                except Exception as e:
                    error_msg = f"标准化标签文件失败: {file_info.text_path}, 错误: {e}"
                    self.logger.error(error_msg)
                    result.errors.append(error_msg)
            
            if not result.errors:
                result.success = True
                result.message = f"成功标准化 {result.standardized_tags} 个标签文件"
                self.logger.info(result.message)
            else:
                result.message = f"标准化过程中出现 {len(result.errors)} 个错误"
                self.logger.warning(result.message)
        
        except Exception as e:
            error_msg = f"标准化过程失败: {e}"
            self.logger.error(error_msg)
            result.errors.append(error_msg)
            result.message = error_msg
        
        return result
    
    def handle_unpaired_files(self, folder_path: str, unpaired_files: List[str]) -> ProcessResult:
        """
        处理未配对的文件
        
        Args:
            folder_path: 文件夹路径
            unpaired_files: 未配对文件路径列表
            
        Returns:
            处理结果
        """
        result = ProcessResult(success=False, message="")
        
        if not unpaired_files:
            result.success = True
            result.message = "没有未配对的文件需要处理"
            return result
        
        if not self.create_unpaired_folder:
            result.success = True
            result.message = "配置禁用了未配对文件夹创建"
            return result
        
        self.logger.info(f"开始处理 {len(unpaired_files)} 个未配对文件")
        
        try:
            # 创建unpaired文件夹
            unpaired_folder = os.path.join(folder_path, 'unpaired')
            os.makedirs(unpaired_folder, exist_ok=True)
            
            # 移动未配对文件
            for file_path in unpaired_files:
                try:
                    filename = os.path.basename(file_path)
                    dest_path = os.path.join(unpaired_folder, filename)
                    
                    # 如果目标文件已存在，添加序号
                    counter = 1
                    original_dest = dest_path
                    while os.path.exists(dest_path):
                        name, ext = os.path.splitext(original_dest)
                        dest_path = f"{name}_{counter}{ext}"
                        counter += 1
                    
                    shutil.move(file_path, dest_path)
                    result.unpaired_files += 1
                    
                except Exception as e:
                    error_msg = f"移动未配对文件失败: {file_path}, 错误: {e}"
                    self.logger.error(error_msg)
                    result.errors.append(error_msg)
            
            if not result.errors:
                result.success = True
                result.message = f"成功处理 {result.unpaired_files} 个未配对文件"
                self.logger.info(result.message)
            else:
                result.message = f"处理未配对文件时出现 {len(result.errors)} 个错误"
                self.logger.warning(result.message)
        
        except Exception as e:
            error_msg = f"处理未配对文件失败: {e}"
            self.logger.error(error_msg)
            result.errors.append(error_msg)
            result.message = error_msg
        
        return result
    
    def auto_post_process(self, folder_path: str) -> ProcessResult:
        """
        自动后处理：文件重命名 + 标签标准化
        
        Args:
            folder_path: 要处理的文件夹路径
            
        Returns:
            处理结果
        """
        overall_result = ProcessResult(success=False, message="")
        
        self.logger.info(f"开始自动后处理: {folder_path}")
        
        try:
            with self._lock:
                # 1. 扫描和匹配文件
                file_infos, unpaired_files = self.scan_and_match_files(folder_path)
                overall_result.processed_files = len(file_infos)
                
                # 2. 处理未配对文件
                unpaired_result = self.handle_unpaired_files(folder_path, unpaired_files)
                overall_result.unpaired_files = unpaired_result.unpaired_files
                overall_result.errors.extend(unpaired_result.errors)
                
                # 3. 重命名文件
                rename_result = self.rename_files(folder_path, file_infos)
                overall_result.renamed_files = rename_result.renamed_files
                overall_result.errors.extend(rename_result.errors)
                
                # 4. 标准化标签
                # 重新扫描文件（因为文件名已改变）
                updated_file_infos, _ = self.scan_and_match_files(folder_path)
                standardize_result = self.standardize_tags(folder_path, updated_file_infos)
                overall_result.standardized_tags = standardize_result.standardized_tags
                overall_result.errors.extend(standardize_result.errors)
                
                # 5. 汇总结果
                if not overall_result.errors:
                    overall_result.success = True
                    overall_result.message = (
                        f"自动后处理完成: 处理 {overall_result.processed_files} 个文件对, "
                        f"重命名 {overall_result.renamed_files} 个文件, "
                        f"标准化 {overall_result.standardized_tags} 个标签文件, "
                        f"处理 {overall_result.unpaired_files} 个未配对文件"
                    )
                else:
                    overall_result.message = f"自动后处理完成，但出现 {len(overall_result.errors)} 个错误"
                
                self.logger.info(overall_result.message)
        
        except Exception as e:
            error_msg = f"自动后处理失败: {e}"
            self.logger.error(error_msg)
            overall_result.errors.append(error_msg)
            overall_result.message = error_msg
        
        return overall_result
    
    def manual_tag_process(self, folder_path: str, remove_tags: List[str] = None,
                          remove_containing: List[str] = None, add_tags: List[str] = None) -> ProcessResult:
        """
        手动标签处理：删除/添加指定标签
        
        Args:
            folder_path: 要处理的文件夹路径
            remove_tags: 要删除的标签列表
            remove_containing: 要删除包含特定内容的标签列表
            add_tags: 要添加的标签列表
            
        Returns:
            处理结果
        """
        result = ProcessResult(success=False, message="")
        
        # 转换为集合
        remove_tags_set = set(remove_tags) if remove_tags else set()
        remove_containing_set = set(remove_containing) if remove_containing else set()
        add_tags_set = set(add_tags) if add_tags else set()
        
        self.logger.info(f"开始手动标签处理: {folder_path}")
        self.logger.info(f"删除标签: {remove_tags_set}")
        self.logger.info(f"删除包含: {remove_containing_set}")
        self.logger.info(f"添加标签: {add_tags_set}")
        
        try:
            # 扫描所有txt文件
            txt_files = []
            for filename in os.listdir(folder_path):
                if filename.lower().endswith('.txt'):
                    txt_files.append(os.path.join(folder_path, filename))
            
            for txt_file in txt_files:
                try:
                    # 读取原始内容
                    with open(txt_file, 'r', encoding='utf-8') as f:
                        original_content = f.read()
                    
                    # 处理标签
                    processed_content = self.clean_and_edit_tags(
                        original_content, 
                        remove_tags_set, 
                        remove_containing_set, 
                        add_tags_set
                    )
                    
                    # 写回文件
                    with open(txt_file, 'w', encoding='utf-8') as f:
                        f.write(processed_content)
                    
                    result.processed_files += 1
                    
                except Exception as e:
                    error_msg = f"处理标签文件失败: {txt_file}, 错误: {e}"
                    self.logger.error(error_msg)
                    result.errors.append(error_msg)
            
            if not result.errors:
                result.success = True
                result.message = f"成功处理 {result.processed_files} 个标签文件"
                self.logger.info(result.message)
            else:
                result.message = f"手动标签处理完成，但出现 {len(result.errors)} 个错误"
                self.logger.warning(result.message)
        
        except Exception as e:
            error_msg = f"手动标签处理失败: {e}"
            self.logger.error(error_msg)
            result.errors.append(error_msg)
            result.message = error_msg
        
        return result