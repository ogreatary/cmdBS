@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

echo.
echo ╔══════════════════════════════════════════════════════════════╗
echo ║                    CMD脚本管理器 - 安装启动器                    ║
echo ║                     Professional Script Manager                ║
echo ╚══════════════════════════════════════════════════════════════╝
echo.

:: 设置颜色
for /f "tokens=1,2 delims=#" %%a in ('"prompt #$H#$E# & echo on & for %%b in (1) do rem"') do (
  set "DEL=%%a"
)

:: 检查管理员权限
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo ⚠️  警告: 建议以管理员身份运行以获得最佳体验
    echo.
)

:: 显示系统信息
echo 📊 系统信息检查:
echo ├─ 操作系统: %OS%
echo ├─ 处理器架构: %PROCESSOR_ARCHITECTURE%
echo ├─ 当前目录: %CD%
echo └─ 当前用户: %USERNAME%
echo.

:: 检查Python安装
echo 🔍 检查Python环境...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ❌ 错误: 未找到Python
    echo.
    echo 📥 请先安装Python 3.7或更高版本:
    echo    下载地址: https://www.python.org/downloads/
    echo.
    echo 💡 安装提示:
    echo    1. 下载Python安装包
    echo    2. 安装时勾选 "Add Python to PATH"
    echo    3. 重新运行此脚本
    echo.
    pause
    exit /b 1
)

:: 获取Python版本
for /f "tokens=2" %%i in ('python --version 2^>^&1') do set PYTHON_VERSION=%%i
echo ✅ Python版本: %PYTHON_VERSION%

:: 检查pip
echo 🔍 检查pip包管理器...
pip --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ❌ pip未找到，尝试安装...
    python -m ensurepip --upgrade
    if !errorlevel! neq 0 (
        echo ❌ pip安装失败
        pause
        exit /b 1
    )
)
echo ✅ pip检查通过
echo.

:: 检查必要文件
echo 🔍 检查必要文件...
set "MISSING_FILES="
if not exist "cmd_manager.py" set "MISSING_FILES=!MISSING_FILES! cmd_manager.py"
if not exist "requirements_cmd_manager.txt" set "MISSING_FILES=!MISSING_FILES! requirements_cmd_manager.txt"
if not exist "templates\index.html" set "MISSING_FILES=!MISSING_FILES! templates\index.html"

if not "!MISSING_FILES!"=="" (
    echo ❌ 缺少必要文件: !MISSING_FILES!
    echo 请确保所有文件都在当前目录中
    pause
    exit /b 1
)
echo ✅ 必要文件检查通过
echo.

:: 创建虚拟环境
if not exist "venv" (
    echo 🔧 创建Python虚拟环境...
    python -m venv venv
    if %errorlevel% neq 0 (
        echo ❌ 创建虚拟环境失败
        echo 可能原因:
        echo - 磁盘空间不足
        echo - 权限不够
        echo - Python安装不完整
        pause
        exit /b 1
    )
    echo ✅ 虚拟环境创建成功
else (
    echo ✅ 虚拟环境已存在
)
echo.

:: 激活虚拟环境
echo 🔧 激活虚拟环境...
if not exist "venv\Scripts\activate.bat" (
    echo ❌ 虚拟环境损坏，正在重新创建...
    rmdir /s /q venv
    python -m venv venv
    if %errorlevel% neq 0 (
        echo ❌ 重新创建虚拟环境失败
        pause
        exit /b 1
    )
)

call venv\Scripts\activate.bat
if %errorlevel% neq 0 (
    echo ❌ 激活虚拟环境失败
    pause
    exit /b 1
)
echo ✅ 虚拟环境激活成功
echo.

:: 升级pip
echo 🔧 升级pip到最新版本...
python -m pip install --upgrade pip >nul 2>&1
echo ✅ pip升级完成
echo.

:: 安装依赖
echo 📦 安装依赖包...
echo 正在安装: Flask, psutil, 等依赖包...
pip install -r requirements_cmd_manager.txt
if %errorlevel% neq 0 (
    echo ❌ 安装依赖包失败
    echo.
    echo 🔧 尝试解决方案:
    echo 1. 检查网络连接
    echo 2. 尝试使用国内镜像源:
    echo    pip install -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements_cmd_manager.txt
    echo.
    pause
    exit /b 1
)
echo ✅ 依赖包安装完成
echo.

:: 创建必要目录
echo 🔧 创建必要目录...
if not exist "logs" (
    mkdir logs
    echo ✅ 创建日志目录: logs\
else (
    echo ✅ 日志目录已存在: logs\
)

if not exist "templates" (
    mkdir templates
    echo ✅ 创建模板目录: templates\
else (
    echo ✅ 模板目录已存在: templates\
)
echo.

:: 检查端口占用
echo 🔍 检查端口5000占用情况...
netstat -an | find ":5000" >nul 2>&1
if %errorlevel% equ 0 (
    echo ⚠️  警告: 端口5000已被占用
    echo 如果启动失败，请检查其他程序是否占用了该端口
else (
    echo ✅ 端口5000可用
)
echo.

:: 显示启动信息
echo ╔══════════════════════════════════════════════════════════════╗
echo ║                        启动信息                              ║
echo ╠══════════════════════════════════════════════════════════════╣
echo ║ 🌐 Web界面地址: http://localhost:5000                        ║
echo ║ 📁 工作目录:   %CD%                    ║
echo ║ 📝 日志目录:   %CD%\logs               ║
echo ║ ⚙️  配置文件:   %CD%\cmd_config.json   ║
echo ║                                                              ║
echo ║ 💡 使用提示:                                                  ║
echo ║    - 在浏览器中打开上述地址访问管理界面                        ║
echo ║    - 首次使用请先添加脚本配置                                  ║
echo ║    - 按 Ctrl+C 可以停止服务                                  ║
echo ║    - 查看 README_CMD_Manager.md 获取详细使用说明              ║
echo ╚══════════════════════════════════════════════════════════════╝
echo.

:: 等待用户确认
echo 按任意键启动CMD脚本管理器...
pause >nul
echo.

echo 🚀 正在启动CMD脚本管理器...
echo ═══════════════════════════════════════════════════════════════
echo.

:: 启动服务
python cmd_manager.py

:: 服务停止后的处理
echo.
echo ═══════════════════════════════════════════════════════════════
echo 👋 CMD脚本管理器已停止
echo.
echo 如果是意外停止，请检查:
echo 1. 错误日志信息
echo 2. 端口是否被占用
echo 3. Python环境是否正常
echo.
echo 按任意键退出...
pause >nul