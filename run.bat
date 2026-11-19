chcp 65001 >nul
@echo off
cd /d "%~dp0"
set "PYTHON_EXE=.venv\Scripts\python.exe"

if not exist "%PYTHON_EXE%" (
    echo 错误：未找到 .venv\Scripts\python.exe。
    echo 请先在工程根目录创建或准备 .venv 虚拟环境，并安装项目依赖。
    pause
    exit /b 1
)

"%PYTHON_EXE%" "run.py"
set "EXIT_CODE=%errorlevel%"
if not "%EXIT_CODE%"=="0" echo 程序异常退出，退出码：%EXIT_CODE%
exit /b %EXIT_CODE%
