chcp 65001 >nul
@echo off
cd /d "%~dp0"
set "PYTHON_EXE=.venv\Scripts\python.exe"
set "DIST_DIR=dist\CheckbordToolbox"

if not exist "%PYTHON_EXE%" (
    echo 错误：未找到 .venv\Scripts\python.exe。
    echo 请先在工程根目录创建或准备 .venv 虚拟环境，并安装项目依赖。
    pause
    exit /b 1
)

"%PYTHON_EXE%" -m PyInstaller --version >nul 2>&1
if errorlevel 1 (
    echo 未检测到 PyInstaller，正在 .venv 内安装 pyinstaller==6.22.3...
    "%PYTHON_EXE%" -m pip install "pyinstaller==6.22.3"
    if errorlevel 1 (
        echo 错误：PyInstaller 安装失败，请检查上方 pip 输出。
        pause
        exit /b 1
    )
)

echo 正在以目录模式打包 CheckbordToolbox，请稍候...
"%PYTHON_EXE%" -m PyInstaller CheckbordToolbox.spec --clean --noconfirm
if errorlevel 1 (
    echo 错误：PyInstaller 打包失败，请检查上方日志。
    pause
    exit /b 1
)

if not exist "%DIST_DIR%\" (
    echo 错误：未生成 %DIST_DIR% 目录。
    pause
    exit /b 1
)

rmdir /s /q "build" 2>nul

if not exist "%DIST_DIR%\assets\checkerboard" mkdir "%DIST_DIR%\assets\checkerboard"
if not exist "%DIST_DIR%\assets\test_data\calibration" mkdir "%DIST_DIR%\assets\test_data\calibration"
if not exist "%DIST_DIR%\assets\calibration" mkdir "%DIST_DIR%\assets\calibration"
if not exist "%DIST_DIR%\temp\calibration_qa" mkdir "%DIST_DIR%\temp\calibration_qa"

copy /Y "config.ini" "%DIST_DIR%\config.ini" >nul
if errorlevel 1 goto prepare_failed
copy /Y "README.md" "%DIST_DIR%\README.md" >nul
if errorlevel 1 goto prepare_failed

for %%F in (checkerboard.pdf checkerboard_preview.png 打印说明.txt) do (
    if exist "assets\checkerboard\%%F" (
        copy /Y "assets\checkerboard\%%F" "%DIST_DIR%\assets\checkerboard\%%F" >nul
        if errorlevel 1 goto prepare_failed
    )
)

"%PYTHON_EXE%" -c "from pathlib import Path; Path(r'%DIST_DIR%\使用说明.txt').write_text('棋盘格制板与相机标定工具箱 - 使用说明\n\n1. 双击 CheckbordToolbox.exe 启动。\n2. 菜单：1 制板 / 2 标定 / 3 重新加载 config.ini / 其他输入退出。\n3. config.ini 与 CheckbordToolbox.exe 同目录，修改后可用功能 3 重新加载。\n4. 标定采图放入 assets\\test_data\\calibration。\n5. 制板输出到 assets\\checkerboard，标定 XML 输出到 assets\\calibration，QA 图输出到 temp\\calibration_qa。\n6. 不要删除 _internal，否则程序无法运行。\n7. 退出前按提示按回车键关闭窗口。\n', encoding='utf-8-sig')"
if errorlevel 1 goto prepare_failed

if not exist "%DIST_DIR%\CheckbordToolbox.exe" (
    echo 错误：打包命令已结束，但未找到 %DIST_DIR%\CheckbordToolbox.exe。
    pause
    exit /b 1
)

echo 打包成功：%CD%\%DIST_DIR%\CheckbordToolbox.exe
echo 请整体复制 CheckbordToolbox 目录，不要删除 _internal。
pause
exit /b 0

:prepare_failed
echo 错误：打包后的配置、说明或工厂制板文件准备失败。
pause
exit /b 1
