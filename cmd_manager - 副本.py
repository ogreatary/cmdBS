#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CMD脚本管理器 - Web服务
功能：通过Web界面管理多个CMD脚本的运行状态
作者：AI Assistant
版本：1.0.0
"""

import os
import sys
import json
import time
import threading
import subprocess
import psutil
from datetime import datetime
from flask import Flask, render_template, request, jsonify, redirect, url_for
import logging
import signal
from logging.handlers import RotatingFileHandler

# 配置
CONFIG_FILE = 'cmd_config.json'
LOG_DIR = 'logs'
MAX_LOG_SIZE = 10 * 1024 * 1024  # 10MB
MAX_LOG_FILES = 5
MONITOR_INTERVAL = 5  # 监控间隔（秒）

# 创建Flask应用
app = Flask(__name__)
app.secret_key = 'cmd_manager_secret_key_2024'

# 全局变量
scripts = {}
script_processes = {}
script_logs = {}
monitor_thread = None
running = True

class ScriptManager:
    """脚本管理器类"""
    
    def __init__(self):
        self.scripts = {}
        self.processes = {}
        self.logs = {}
        self.stop_reasons = {}  # 存储停止原因
        self.groups = {}  # 存储分组配置
        self.script_groups = {}  # 存储脚本所属分组
        self.script_order = {}  # 存储脚本顺序：{group_id: [script_id1, script_id2, ...], 'ungrouped': [...]}
        self.load_config()
        # 自动启动所有已启用的脚本
        self.auto_start_enabled_scripts()
        
    def load_config(self):
        """加载配置文件"""
        try:
            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    config_data = json.load(f)
                    # 兼容旧版本配置文件
                    if isinstance(config_data, dict) and 'scripts' in config_data:
                        self.scripts = config_data.get('scripts', {})
                        self.groups = config_data.get('groups', {})
                        self.script_groups = config_data.get('script_groups', {})
                        self.script_order = config_data.get('script_order', {})
                        
                        # 初始化脚本顺序（如果配置文件中没有）
                        self._initialize_script_order()
                    else:
                        # 旧版本格式，直接作为scripts
                        self.scripts = config_data
                        self.groups = {}
                        self.script_groups = {}
                app.logger.info(f"已加载配置文件，共{len(self.scripts)}个脚本，{len(self.groups)}个分组")
            else:
                self.scripts = {}
                self.groups = {}
                self.script_groups = {}
                app.logger.info("配置文件不存在，创建空配置")
                self.save_config()
        except Exception as e:
            app.logger.error(f"加载配置文件失败: {e}")
            self.scripts = {}
            self.groups = {}
            self.script_groups = {}
            
    def _initialize_script_order(self):
        """初始化脚本顺序"""
        # 为每个分组初始化脚本顺序
        for group_id in self.groups.keys():
            if group_id not in self.script_order:
                # 获取该分组的所有脚本
                group_scripts = [sid for sid, gid in self.script_groups.items() if gid == group_id]
                self.script_order[group_id] = sorted(group_scripts)  # 按ID排序作为默认顺序
        
        # 初始化未分组脚本的顺序
        if 'ungrouped' not in self.script_order:
            ungrouped_scripts = [sid for sid in self.scripts.keys() if sid not in self.script_groups]
            self.script_order['ungrouped'] = sorted(ungrouped_scripts)  # 按ID排序作为默认顺序
            
    def save_config(self):
        """保存配置文件"""
        try:
            config_data = {
                'scripts': self.scripts,
                'groups': self.groups,
                'script_groups': self.script_groups,
                'script_order': self.script_order
            }
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(config_data, f, ensure_ascii=False, indent=2)
            app.logger.info("配置文件已保存")
        except Exception as e:
            app.logger.error(f"保存配置文件失败: {e}")
    
    def save_scripts_order_only(self):
        """只保存 scripts 对象的顺序（用于列表视图拖拽）"""
        try:
            # 读取现有配置
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                config_data = json.load(f)
            
            # 只更新 scripts 部分
            config_data['scripts'] = self.scripts
            
            # 保存回文件
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(config_data, f, ensure_ascii=False, indent=2)
            app.logger.info("Scripts顺序已保存（列表视图）")
        except Exception as e:
            app.logger.error(f"保存Scripts顺序失败: {e}")
    
    def save_script_order_only(self):
        """只保存 script_order（用于分组视图拖拽）"""
        try:
            # 读取现有配置
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                config_data = json.load(f)
            
            # 只更新 script_order 部分
            config_data['script_order'] = self.script_order
            
            # 保存回文件
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(config_data, f, ensure_ascii=False, indent=2)
            app.logger.info("Script_order已保存（分组视图）")
        except Exception as e:
            app.logger.error(f"保存Script_order失败: {e}")
            
    def auto_start_enabled_scripts(self):
        """自动启动所有已启用的脚本"""
        if not self.scripts:
            return
            
        started_count = 0
        failed_count = 0
        
        for script_id, script_config in self.scripts.items():
            # 检查脚本是否启用（默认为启用）
            if script_config.get('enabled', True):
                try:
                    success, message = self.start_script(script_id)
                    if success:
                        started_count += 1
                        print(f"✅ 自动启动脚本: {script_config.get('name', script_id)}")
                    else:
                        failed_count += 1
                        print(f"❌ 启动脚本失败: {script_config.get('name', script_id)} - {message}")
                except Exception as e:
                    failed_count += 1
                    print(f"❌ 启动脚本异常: {script_config.get('name', script_id)} - {str(e)}")
            else:
                print(f"⏸️  跳过已禁用脚本: {script_config.get('name', script_id)}")
        
        if started_count > 0 or failed_count > 0:
            print(f"\n📊 自动启动结果: 成功 {started_count} 个，失败 {failed_count} 个")
        else:
            print("\n📝 没有需要自动启动的脚本")
            
    def add_script(self, script_id, config):
        """添加脚本"""
        self.scripts[script_id] = config
        self.logs[script_id] = []
        self.save_config()
        app.logger.info(f"添加脚本: {script_id} - {config.get('name', 'Unknown')}")
        
    def remove_script(self, script_id):
        """删除脚本"""
        if script_id in self.scripts:
            # 先停止脚本
            self.stop_script(script_id)
            # 删除配置
            del self.scripts[script_id]
            if script_id in self.logs:
                del self.logs[script_id]
            self.save_config()
            app.logger.info(f"删除脚本: {script_id}")
            
    def start_script(self, script_id):
        """启动脚本"""
        if script_id not in self.scripts:
            return False, "脚本不存在"
            
        if script_id in self.processes and self.is_process_running(script_id):
            return False, "脚本已在运行"
            
        # 清理旧的停止原因记录，确保能正确识别新的异常退出
        if script_id in self.stop_reasons:
            del self.stop_reasons[script_id]
            
        script_config = self.scripts[script_id]
        try:
            # 准备启动参数
            command = script_config['command']
            working_dir = script_config.get('working_dir', os.getcwd())
            
            # 启动进程
            # 设置环境变量支持UTF-8编码
            env = os.environ.copy()
            env['PYTHONIOENCODING'] = 'utf-8'
            env['PYTHONLEGACYWINDOWSSTDIO'] = '0'
            
            # 处理不同类型的脚本命令，确保输出不被缓冲
            command_lower = command.strip().lower()
            
            # Python脚本处理
            if command_lower.startswith('python '):
                command = command.replace('python ', 'python -u ', 1)
            elif command_lower.startswith('python.exe '):
                command = command.replace('python.exe ', 'python.exe -u ', 1)
            elif command_lower.endswith('.py') or ' .py' in command_lower:
                # 直接运行.py文件的情况，在前面添加python -u
                if not command_lower.startswith(('python', 'py ')):
                    command = f'python -u {command}'
            
            # PowerShell脚本处理
            elif command_lower.startswith('powershell '):
                # 为PowerShell添加-NoBuffering参数
                if '-nobuffering' not in command_lower:
                    command = command.replace('powershell ', 'powershell -NoBuffering ', 1)
            elif command_lower.startswith('pwsh '):
                # PowerShell Core处理
                if '-nobuffering' not in command_lower:
                    command = command.replace('pwsh ', 'pwsh -NoBuffering ', 1)
            elif command_lower.endswith('.ps1'):
                # 直接运行.ps1文件
                command = f'powershell -NoBuffering -ExecutionPolicy Bypass -File {command}'
            
            # 批处理文件通常不需要特殊处理，但可以确保使用cmd /c
            elif command_lower.endswith('.bat') or command_lower.endswith('.cmd'):
                if not command_lower.startswith('cmd '):
                    command = f'cmd /c "{command}"'
            
            # 设置进程创建标志，确保能够正确管理子进程
            creation_flags = 0
            if os.name == 'nt':  # Windows
                # 使用CREATE_NEW_PROCESS_GROUP确保能够管理整个进程树
                creation_flags = subprocess.CREATE_NEW_PROCESS_GROUP
            
            process = subprocess.Popen(
                command,
                shell=True,
                cwd=working_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,              # 替换 universal_newlines=True
                encoding='utf-8',       # 明确指定UTF-8编码
                errors='replace',       # 编码错误时用替换字符处理
                bufsize=0,              # 无缓冲输出，确保实时显示
                env=env,
                creationflags=creation_flags
            )
            
            self.processes[script_id] = {
                'process': process,
                'start_time': datetime.now(),
                'restart_count': 0
            }
            
            # 启动日志读取线程
            log_thread = threading.Thread(
                target=self._read_process_output,
                args=(script_id, process),
                daemon=True
            )
            log_thread.start()
            
            self.add_log(script_id, f"脚本启动成功 (PID: {process.pid})")
            app.logger.info(f"启动脚本: {script_id} (PID: {process.pid})")
            return True, "启动成功"
            
        except Exception as e:
            error_msg = f"启动失败: {str(e)}"
            self.add_log(script_id, error_msg)
            app.logger.error(f"启动脚本失败 {script_id}: {e}")
            return False, error_msg
            
    def stop_script(self, script_id, reason="manual"):
        """停止脚本
        Args:
            script_id: 脚本ID
            reason: 停止原因 ('manual' 手动停止, 'crash' 异常退出)
        """
        if script_id not in self.processes:
            return False, "脚本未运行"
            
        try:
            process_info = self.processes[script_id]
            process = process_info['process']
            
            # 先记录停止原因，避免监控线程误判为crash
            self.stop_reasons[script_id] = reason
            
            if process.poll() is None:  # 进程仍在运行
                self.add_log(script_id, f"正在停止进程 (PID: {process.pid})...")
                
                try:
                    # 导入psutil模块，确保在整个try块中可用
                    import psutil
                    
                    # Windows下首先尝试发送CTRL_BREAK_EVENT到进程组
                    if os.name == 'nt':
                        try:
                            # 发送CTRL_BREAK_EVENT到整个进程组
                            os.kill(process.pid, signal.CTRL_BREAK_EVENT)
                            self.add_log(script_id, "已发送CTRL_BREAK_EVENT信号")
                            
                            # 等待进程响应信号
                            try:
                                process.wait(timeout=5)
                                self.add_log(script_id, "进程已响应CTRL_BREAK_EVENT信号停止")
                            except subprocess.TimeoutExpired:
                                self.add_log(script_id, "CTRL_BREAK_EVENT超时，继续使用其他方法")
                        except (OSError, ProcessLookupError) as e:
                            self.add_log(script_id, f"发送CTRL_BREAK_EVENT失败: {e}")
                    
                    # 如果进程仍在运行，使用psutil获取进程树
                    if process.poll() is None:
                        parent = psutil.Process(process.pid)
                        children = parent.children(recursive=True)
                        
                        self.add_log(script_id, f"发现 {len(children)} 个子进程，准备全部停止")
                        
                        # 首先尝试优雅停止所有进程
                        all_processes = children + [parent]
                        
                        # 第一步：发送SIGTERM/terminate信号
                        for p in all_processes:
                            try:
                                p.terminate()
                            except psutil.NoSuchProcess:
                                pass
                    
                        # 等待进程优雅退出
                        gone, alive = psutil.wait_procs(all_processes, timeout=5)
                        
                        if alive:
                            self.add_log(script_id, f"仍有 {len(alive)} 个进程未退出，强制杀死")
                            # 第二步：强制杀死仍在运行的进程
                            for p in alive:
                                try:
                                    p.kill()
                                except psutil.NoSuchProcess:
                                    pass
                            
                            # 再次等待
                            psutil.wait_procs(alive, timeout=3)
                        
                        self.add_log(script_id, "所有相关进程已停止")
                    else:
                        self.add_log(script_id, "进程已通过信号停止，无需进一步处理")
                    
                except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
                    # 如果psutil方法失败，回退到原始方法
                    self.add_log(script_id, f"psutil停止失败: {e}，使用基本停止方法")
                    
                    # Windows下额外使用taskkill命令
                    if os.name == 'nt':
                        try:
                            # 使用taskkill强制终止进程树
                            result = subprocess.run(
                                ['taskkill', '/F', '/T', '/PID', str(process.pid)], 
                                capture_output=True, 
                                text=True,
                                timeout=10
                            )
                            if result.returncode == 0:
                                self.add_log(script_id, "已使用taskkill强制终止进程树")
                            else:
                                self.add_log(script_id, f"taskkill失败: {result.stderr}")
                        except Exception as taskkill_error:
                            self.add_log(script_id, f"taskkill执行失败: {taskkill_error}")
                    
                    # 最后的回退方法
                    try:
                        process.terminate()
                        process.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
                
                except Exception as stop_error:
                    self.add_log(script_id, f"停止过程中出错: {stop_error}")
                    # 最基本的停止方法
                    try:
                        process.terminate()
                        process.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
            
            # 验证进程是否真的停止了
            try:
                if process.poll() is None:
                    self.add_log(script_id, "警告: 进程可能仍在运行")
                else:
                    self.add_log(script_id, f"进程已确认停止 (退出码: {process.returncode})")
            except:
                pass
            
            del self.processes[script_id]
            stop_msg = "脚本已停止" if reason == "manual" else "脚本异常退出"
            self.add_log(script_id, stop_msg)
            app.logger.info(f"停止脚本: {script_id}, 原因: {reason}")
            return True, "停止成功"
            
        except Exception as e:
            error_msg = f"停止失败: {str(e)}"
            self.add_log(script_id, error_msg)
            app.logger.error(f"停止脚本失败 {script_id}: {e}")
            return False, error_msg
            
    def restart_script(self, script_id):
        """重启脚本"""
        self.stop_script(script_id)
        time.sleep(1)  # 等待1秒
        return self.start_script(script_id)
        
    def toggle_script(self, script_id):
        """切换脚本启用/禁用状态"""
        if script_id not in self.scripts:
            return False, "脚本不存在", False
            
        script_config = self.scripts[script_id]
        current_enabled = script_config.get('enabled', True)
        new_enabled = not current_enabled
        
        # 更新配置
        script_config['enabled'] = new_enabled
        self.save_config()
        
        # 如果禁用了脚本且正在运行，则停止它
        if not new_enabled and self.is_process_running(script_id):
            self.stop_script(script_id, "manual")
            
        # 如果禁用了脚本，清除停止原因记录
        if not new_enabled and script_id in self.stop_reasons:
            del self.stop_reasons[script_id]
            
        action = "启用" if new_enabled else "禁用"
        message = f"脚本已{action}"
        self.add_log(script_id, message)
        app.logger.info(f"切换脚本状态: {script_id} - {action}")
        
        return True, message, new_enabled
        
    def is_process_running(self, script_id):
        """检查进程是否运行"""
        if script_id not in self.processes:
            return False
            
        process = self.processes[script_id]['process']
        return process.poll() is None
        
    def get_script_status(self, script_id):
        """获取脚本状态"""
        if script_id not in self.scripts:
            return 'unknown'
            
        if self.is_process_running(script_id):
            return 'running'
        else:
            return 'stopped'
            
    def get_script_info(self, script_id):
        """获取脚本详细信息"""
        if script_id not in self.scripts:
            return None
            
        info = self.scripts[script_id].copy()
        info['status'] = self.get_script_status(script_id)
        
        if script_id in self.processes:
            process_info = self.processes[script_id]
            info['pid'] = process_info['process'].pid if self.is_process_running(script_id) else None
            info['start_time'] = process_info['start_time'].strftime('%Y-%m-%d %H:%M:%S')
            info['restart_count'] = process_info['restart_count']
            
            # 获取CPU和内存使用率
            if self.is_process_running(script_id):
                try:
                    p = psutil.Process(process_info['process'].pid)
                    info['cpu_percent'] = p.cpu_percent()
                    info['memory_mb'] = p.memory_info().rss / 1024 / 1024
                except:
                    info['cpu_percent'] = 0
                    info['memory_mb'] = 0
        
        return info
        
    def add_log(self, script_id, message):
        """添加日志"""
        if script_id not in self.logs:
            self.logs[script_id] = []
            
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        log_entry = f"[{timestamp}] {message}"
        self.logs[script_id].append(log_entry)
        
        # 限制日志条数
        if len(self.logs[script_id]) > 1000:
            self.logs[script_id] = self.logs[script_id][-500:]
            
    def get_logs(self, script_id, lines=100):
        """获取日志"""
        if script_id not in self.logs:
            return []
        return self.logs[script_id][-lines:]
        
    def _read_process_output(self, script_id, process):
        """读取进程输出"""
        try:
            for line in iter(process.stdout.readline, ''):
                if line:
                    # 处理可能的编码问题
                    try:
                        clean_line = line.strip()
                    except UnicodeDecodeError as ue:
                        # 如果出现编码错误，尝试用不同的编码方式处理
                        try:
                            clean_line = line.encode('utf-8', errors='replace').decode('utf-8').strip()
                        except:
                            clean_line = f"[编码错误] 无法正确显示的输出内容"
                    self.add_log(script_id, clean_line)
                if process.poll() is not None:
                    break
        except Exception as e:
            self.add_log(script_id, f"读取输出失败: {e}")
            
    def monitor_scripts(self):
        """监控脚本状态"""
        while running:
            try:
                for script_id in list(self.processes.keys()):
                    if not self.is_process_running(script_id):
                        # 进程已退出
                        process_info = self.processes[script_id]
                        exit_code = process_info['process'].returncode
                        
                        # 标记为异常退出（如果不是手动停止）
                        # 只有在没有停止原因记录时才设置为crash，避免覆盖手动停止的记录
                        if script_id not in self.stop_reasons:
                            self.stop_reasons[script_id] = 'crash'
                        
                        self.add_log(script_id, f"进程退出 (退出码: {exit_code})")
                        
                        # 检查是否需要自动重启
                        script_config = self.scripts.get(script_id, {})
                        if script_config.get('auto_restart', False) and script_config.get('enabled', False):
                            self.add_log(script_id, "准备自动重启...")
                            process_info['restart_count'] += 1
                            
                            # 等待一段时间后重启
                            time.sleep(5)
                            success, message = self.start_script(script_id)
                            if success:
                                self.add_log(script_id, f"自动重启成功 (第{process_info['restart_count']}次重启)")
                            else:
                                self.add_log(script_id, f"自动重启失败: {message}")
                        else:
                            # 清理进程信息
                            del self.processes[script_id]
                            
                time.sleep(MONITOR_INTERVAL)
            except Exception as e:
                app.logger.error(f"监控线程错误: {e}")
                time.sleep(MONITOR_INTERVAL)
    
    def create_group(self, group_id, name, description=""):
        """创建分组"""
        self.groups[group_id] = {
            'name': name,
            'description': description,
            'created_at': datetime.now().isoformat()
        }
        self.save_config()
        app.logger.info(f"创建分组: {group_id} - {name}")
        return True
    
    def delete_group(self, group_id):
        """删除分组"""
        if group_id in self.groups:
            # 将该分组中的脚本移出分组
            scripts_to_remove = [script_id for script_id, gid in self.script_groups.items() if gid == group_id]
            for script_id in scripts_to_remove:
                del self.script_groups[script_id]
            
            del self.groups[group_id]
            self.save_config()
            app.logger.info(f"删除分组: {group_id}")
            return True
        return False
    
    def update_group(self, group_id, name=None, description=None):
        """更新分组信息"""
        if group_id in self.groups:
            if name is not None:
                self.groups[group_id]['name'] = name
            if description is not None:
                self.groups[group_id]['description'] = description
            self.save_config()
            app.logger.info(f"更新分组: {group_id}")
            return True
        return False
    
    def move_script_to_group(self, script_id, group_id, position=None):
        """将脚本移动到分组"""
        try:
            if script_id not in self.scripts:
                return False, "脚本不存在"
            
            # 从原位置移除脚本
            old_group = self.script_groups.get(script_id)
            if old_group:
                old_group_key = old_group
            else:
                old_group_key = 'ungrouped'
            
            if old_group_key in self.script_order and script_id in self.script_order[old_group_key]:
                self.script_order[old_group_key].remove(script_id)
            
            if group_id is None or group_id == "":
                # 移出分组
                if script_id in self.script_groups:
                    del self.script_groups[script_id]
                target_group_key = 'ungrouped'
                message = "脚本已移出分组"
            else:
                # 移动到指定分组
                if group_id not in self.groups:
                    return False, "目标分组不存在"
                
                self.script_groups[script_id] = group_id
                target_group_key = group_id
                message = f"脚本已移动到分组 {self.groups[group_id]['name']}"
            
            # 添加到新位置
            if target_group_key not in self.script_order:
                self.script_order[target_group_key] = []
            
            if position is not None and 0 <= position <= len(self.script_order[target_group_key]):
                self.script_order[target_group_key].insert(position, script_id)
            else:
                self.script_order[target_group_key].append(script_id)
            
            self.save_config()
            app.logger.info(f"脚本 {script_id} 移动到分组 {group_id}")
            return True, message
                
        except Exception as e:
            app.logger.error(f"移动脚本到分组失败: {e}")
            return False, f"移动失败: {str(e)}"
    
    def get_groups_info(self):
        """获取所有分组信息"""
        groups_info = []
        for group_id, group_data in self.groups.items():
            # 按保存的顺序获取分组中的脚本
            if group_id in self.script_order:
                scripts_in_group = [sid for sid in self.script_order[group_id] if sid in self.script_groups and self.script_groups[sid] == group_id]
            else:
                # 如果没有保存的顺序，按ID排序
                scripts_in_group = [script_id for script_id, gid in self.script_groups.items() if gid == group_id]
                scripts_in_group.sort()
                self.script_order[group_id] = scripts_in_group  # 保存默认顺序
            
            group_info = {
                'id': group_id,
                'name': group_data['name'],
                'description': group_data.get('description', ''),
                'created_at': group_data.get('created_at', ''),
                'script_count': len(scripts_in_group),
                'scripts': scripts_in_group
            }
            groups_info.append(group_info)
        return groups_info
    
    def get_ungrouped_scripts(self):
        """获取未分组的脚本"""
        ungrouped_scripts = [sid for sid in self.scripts.keys() if sid not in self.script_groups]
        if 'ungrouped' in self.script_order:
            # 按保存的顺序排列，过滤掉已分组的脚本
            ordered_ungrouped = [sid for sid in self.script_order['ungrouped'] if sid in ungrouped_scripts]
            # 添加新的未分组脚本（如果有的话）
            new_ungrouped = [sid for sid in ungrouped_scripts if sid not in self.script_order['ungrouped']]
            ordered_ungrouped.extend(sorted(new_ungrouped))
            self.script_order['ungrouped'] = ordered_ungrouped
            return ordered_ungrouped
        else:
            # 如果没有保存的顺序，按ID排序
            ordered_ungrouped = sorted(ungrouped_scripts)
            self.script_order['ungrouped'] = ordered_ungrouped
            return ordered_ungrouped

# 创建脚本管理器实例
script_manager = ScriptManager()

# 路由定义
@app.route('/dawson/')
def index():
    """主页"""
    return render_template('index.html')

@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def catch_all(path):
    """捕获所有其他路径，返回未知路径"""
    # 如果访问的是dawson路径，重定向到正确的路径
    if path == 'dawson':
        return redirect('/dawson/')
    # 其他所有路径都返回"未知路径"
    return '未知路径', 404

@app.route('/dawson/api/scripts')
def api_scripts():
    """获取所有脚本信息"""
    scripts_info = []
    view_mode = request.args.get('view', 'all')  # all, ungrouped, grouped
    
    if view_mode == 'ungrouped':
        # 只返回未分组的脚本（按配置文件中的顺序）
        ungrouped_scripts = script_manager.get_ungrouped_scripts()
        for script_id in ungrouped_scripts:
            script_info = script_manager.get_script_info(script_id)
            if script_info:
                script_info['id'] = script_id
                scripts_info.append(script_info)
    else:
        # 返回所有脚本，按照配置文件中的原始顺序
        # 按照配置文件中scripts的定义顺序返回所有脚本
        for script_id in script_manager.scripts.keys():
            script_info = script_manager.get_script_info(script_id)
            if script_info:
                script_info['id'] = script_id
                scripts_info.append(script_info)
    
    return jsonify(scripts_info)

@app.route('/dawson/api/scripts/<script_id>')
def api_script_info(script_id):
    """获取单个脚本信息"""
    info = script_manager.get_script_info(script_id)
    if info:
        return jsonify(info)
    else:
        return jsonify({'error': '脚本不存在'}), 404

@app.route('/dawson/api/scripts/<script_id>/start', methods=['POST'])
def api_start_script(script_id):
    """启动脚本"""
    success, message = script_manager.start_script(script_id)
    return jsonify({'success': success, 'message': message})

@app.route('/dawson/api/scripts/<script_id>/stop', methods=['POST'])
def api_stop_script(script_id):
    """停止脚本"""
    data = request.get_json() or {}
    reason = data.get('reason', 'manual')  # 默认为手动停止
    success, message = script_manager.stop_script(script_id, reason)
    return jsonify({'success': success, 'message': message, 'reason': reason})

@app.route('/dawson/api/scripts/<script_id>/restart', methods=['POST'])
def api_restart_script(script_id):
    """重启脚本"""
    success, message = script_manager.restart_script(script_id)
    return jsonify({'success': success, 'message': message})

@app.route('/dawson/api/scripts/<script_id>/toggle', methods=['POST'])
def api_toggle_script(script_id):
    """切换脚本启用/禁用状态"""
    success, message, enabled = script_manager.toggle_script(script_id)
    return jsonify({'success': success, 'message': message, 'enabled': enabled})

@app.route('/dawson/api/scripts/<script_id>/logs')
def api_script_logs(script_id):
    """获取脚本日志"""
    lines = request.args.get('lines', 100, type=int)
    logs = script_manager.get_logs(script_id, lines)
    return jsonify({'logs': logs})

@app.route('/dawson/api/scripts/<script_id>/stop-reason')
def api_script_stop_reason(script_id):
    """获取脚本停止原因"""
    reason = script_manager.stop_reasons.get(script_id, 'unknown')
    return jsonify({'script_id': script_id, 'stop_reason': reason})

@app.route('/dawson/api/scripts', methods=['POST'])
def api_add_script():
    """添加脚本"""
    try:
        data = request.get_json()
        script_id = data.get('id')
        
        if not script_id:
            return jsonify({'success': False, 'message': '脚本ID不能为空'}), 400
            
        if script_id in script_manager.scripts:
            return jsonify({'success': False, 'message': '脚本ID已存在'}), 400
            
        config = {
            'name': data.get('name', ''),
            'command': data.get('command', ''),
            'working_dir': data.get('working_dir', os.getcwd()),
            'auto_restart': data.get('auto_restart', True),
            'enabled': data.get('enabled', True),
            'description': data.get('description', '')
        }
        
        script_manager.add_script(script_id, config)
        return jsonify({'success': True, 'message': '脚本添加成功'})
        
    except Exception as e:
        return jsonify({'success': False, 'message': f'添加失败: {str(e)}'}), 500

@app.route('/dawson/api/scripts/<script_id>', methods=['DELETE'])
def api_delete_script(script_id):
    """删除脚本"""
    if script_id not in script_manager.scripts:
        return jsonify({'success': False, 'message': '脚本不存在'}), 404
        
    script_manager.remove_script(script_id)
    return jsonify({'success': True, 'message': '脚本删除成功'})

@app.route('/dawson/api/system/info')
def api_system_info():
    """获取系统信息"""
    try:
        cpu_percent = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        
        return jsonify({
            'cpu_percent': cpu_percent,
            'memory_percent': memory.percent,
            'memory_used_gb': memory.used / 1024 / 1024 / 1024,
            'memory_total_gb': memory.total / 1024 / 1024 / 1024,
            'disk_percent': disk.percent,
            'disk_used_gb': disk.used / 1024 / 1024 / 1024,
            'disk_total_gb': disk.total / 1024 / 1024 / 1024
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# 分组管理API
@app.route('/dawson/api/groups')
def api_groups():
    """获取所有分组信息"""
    groups_info = script_manager.get_groups_info()
    ungrouped_scripts = script_manager.get_ungrouped_scripts()
    return jsonify({
        'groups': groups_info,
        'ungrouped_scripts': ungrouped_scripts
    })

@app.route('/dawson/api/groups', methods=['POST'])
def api_create_group():
    """创建分组"""
    try:
        data = request.get_json()
        group_id = data.get('id')
        name = data.get('name')
        description = data.get('description', '')
        
        if not group_id or not name:
            return jsonify({'success': False, 'message': '分组ID和名称不能为空'}), 400
            
        if group_id in script_manager.groups:
            return jsonify({'success': False, 'message': '分组ID已存在'}), 400
            
        success = script_manager.create_group(group_id, name, description)
        if success:
            return jsonify({'success': True, 'message': '分组创建成功'})
        else:
            return jsonify({'success': False, 'message': '分组创建失败'}), 500
            
    except Exception as e:
        return jsonify({'success': False, 'message': f'创建分组失败: {str(e)}'}), 500

@app.route('/dawson/api/groups/<group_id>', methods=['PUT'])
def api_update_group(group_id):
    """更新分组信息"""
    try:
        data = request.get_json()
        name = data.get('name')
        description = data.get('description')
        
        success = script_manager.update_group(group_id, name, description)
        if success:
            return jsonify({'success': True, 'message': '分组更新成功'})
        else:
            return jsonify({'success': False, 'message': '分组不存在'}), 404
            
    except Exception as e:
        return jsonify({'success': False, 'message': f'更新分组失败: {str(e)}'}), 500

@app.route('/dawson/api/groups/<group_id>', methods=['DELETE'])
def api_delete_group(group_id):
    """删除分组"""
    try:
        success = script_manager.delete_group(group_id)
        if success:
            return jsonify({'success': True, 'message': '分组删除成功'})
        else:
            return jsonify({'success': False, 'message': '分组不存在'}), 404
            
    except Exception as e:
        return jsonify({'success': False, 'message': f'删除分组失败: {str(e)}'}), 500

@app.route('/dawson/api/scripts/<script_id>/group', methods=['PUT'])
def move_script_to_group(script_id):
    """移动脚本到分组"""
    try:
        data = request.get_json()
        group_id = data.get('group_id')
        position = data.get('position')  # 新增：目标位置
        
        if script_id not in script_manager.scripts:
            return jsonify({'error': '脚本不存在'}), 404
        
        # 从原位置移除脚本
        old_group = script_manager.script_groups.get(script_id)
        if old_group:
            old_group_key = old_group
        else:
            old_group_key = 'ungrouped'
        
        if old_group_key in script_manager.script_order and script_id in script_manager.script_order[old_group_key]:
            script_manager.script_order[old_group_key].remove(script_id)
        
        # 如果group_id为None或空字符串，表示移出分组
        if group_id is None or group_id == '':
            if script_id in script_manager.script_groups:
                del script_manager.script_groups[script_id]
            target_group_key = 'ungrouped'
        else:
            # 检查分组是否存在
            if group_id not in script_manager.groups:
                return jsonify({'error': '分组不存在'}), 404
            script_manager.script_groups[script_id] = group_id
            target_group_key = group_id
        
        # 添加到新位置
        if target_group_key not in script_manager.script_order:
            script_manager.script_order[target_group_key] = []
        
        if position is not None and 0 <= position <= len(script_manager.script_order[target_group_key]):
            script_manager.script_order[target_group_key].insert(position, script_id)
        else:
            script_manager.script_order[target_group_key].append(script_id)
        
        script_manager.save_config()
        return jsonify({'message': '脚本分组更新成功'})
    
    except Exception as e:
        app.logger.error(f"移动脚本到分组失败: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/dawson/api/scripts/reorder', methods=['PUT'])
def reorder_scripts():
    """重新排序脚本"""
    try:
        data = request.get_json()
        group_id = data.get('group_id', 'ungrouped')  # 默认为未分组
        script_ids = data.get('script_ids', [])
        
        app.logger.info(f"收到重排序请求 - 分组: {group_id}, 脚本顺序: {script_ids}")
        
        # 验证脚本ID是否存在
        for script_id in script_ids:
            if script_id not in script_manager.scripts:
                return jsonify({'error': f'脚本 {script_id} 不存在'}), 404
        
        # 如果是全局排序（列表视图），需要重新排列 scripts 对象的键顺序
        if group_id == 'all':
            app.logger.info("处理全局排序（列表视图）- 重新排列scripts对象顺序")
            
            # 保存原始的scripts数据
            old_scripts = script_manager.scripts.copy()
            
            # 创建新的有序scripts字典
            new_scripts = {}
            for script_id in script_ids:
                if script_id in old_scripts:
                    new_scripts[script_id] = old_scripts[script_id]
            
            # 添加任何遗漏的脚本（防止数据丢失）
            for script_id, script_data in old_scripts.items():
                if script_id not in new_scripts:
                    new_scripts[script_id] = script_data
            
            # 更新scripts对象的顺序
            script_manager.scripts = new_scripts
            
            # 只保存scripts对象的顺序
            script_manager.save_scripts_order_only()
            app.logger.info(f"列表视图全局排序完成 - 新的scripts顺序: {list(new_scripts.keys())}")
        else:
            # 单个分组排序
            old_order = script_manager.script_order.get(group_id, [])
            script_manager.script_order[group_id] = script_ids
            app.logger.info(f"分组排序完成 - 分组: {group_id}, 旧顺序: {old_order}, 新顺序: {script_ids}")
            
            # 只保存script_order
            script_manager.save_script_order_only()
        return jsonify({'message': '脚本顺序更新成功'})
    
    except Exception as e:
        app.logger.error(f"重新排序脚本失败: {e}")
        return jsonify({'error': str(e)}), 500

def setup_logging():
    """设置日志"""
    # 创建日志目录
    if not os.path.exists(LOG_DIR):
        os.makedirs(LOG_DIR)
        
    # 设置日志格式
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # 文件日志处理器
    file_handler = RotatingFileHandler(
        os.path.join(LOG_DIR, 'cmd_manager.log'),
        maxBytes=MAX_LOG_SIZE,
        backupCount=MAX_LOG_FILES,
        encoding='utf-8'
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.INFO)
    
    # 控制台日志处理器
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.setLevel(logging.INFO)
    
    # 配置应用日志
    app.logger.setLevel(logging.INFO)
    app.logger.addHandler(file_handler)
    app.logger.addHandler(console_handler)
    
    # 禁用Werkzeug日志
    logging.getLogger('werkzeug').setLevel(logging.WARNING)

def main():
    """主函数"""
    global monitor_thread, running
    
    try:
        print("\n" + "="*60)
        print("🚀 CMD脚本管理器启动中...")
        print("="*60)
        print(f"Python版本: {sys.version}")
        print(f"工作目录: {os.getcwd()}")
        
        # 检查模板文件
        template_path = os.path.join('templates', 'index.html')
        if not os.path.exists(template_path):
            print(f"❌ 模板文件不存在: {template_path}")
            return
        else:
            print(f"✅ 模板文件存在: {template_path}")
        
        # 设置日志
        print("🔧 设置日志系统...")
        setup_logging()
        print("✅ 日志系统设置完成")
        
        # 启动监控线程
        print("🔧 启动监控线程...")
        monitor_thread = threading.Thread(target=script_manager.monitor_scripts, daemon=True)
        monitor_thread.start()
        print("✅ 监控线程启动完成")
        
        app.logger.info("CMD脚本管理器启动")
        
        print(f"\n📊 服务信息:")
        print(f"├─ Web界面: http://localhost:5009")
        print(f"├─ 配置文件: {os.path.abspath(CONFIG_FILE)}")
        print(f"├─ 日志目录: {os.path.abspath(LOG_DIR)}")
        print(f"└─ 工作目录: {os.getcwd()}")
        print(f"\n💡 使用提示:")
        print(f"├─ 在浏览器中打开 http://localhost:5009")
        print(f"├─ 首次使用请先添加脚本配置")
        print(f"└─ 按 Ctrl+C 停止服务")
        print("\n" + "="*60)
        print("✅ 正在启动Flask服务器...")
        print("="*60 + "\n")
        
        # 启动Flask应用
        app.run(
            host='0.0.0.0',
            port=5009,
            debug=False,
            threaded=True,
            use_reloader=False
        )
        
    except KeyboardInterrupt:
        print("\n\n🛑 收到停止信号，正在关闭服务...")
    except Exception as e:
        print(f"\n❌ 服务启动失败: {e}")
        import traceback
        traceback.print_exc()
        if hasattr(app, 'logger'):
            app.logger.error(f"服务启动失败: {e}")
    finally:
        running = False
        # 停止所有脚本
        try:
            for script_id in list(script_manager.processes.keys()):
                script_manager.stop_script(script_id)
        except:
            pass
        print("👋 CMD脚本管理器已停止")
        if hasattr(app, 'logger'):
            app.logger.info("CMD脚本管理器已停止")

if __name__ == '__main__':
    main()