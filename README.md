# 棋盘格制板与相机标定工具箱

本工程用于生成棋盘格打印文件，并对相机进行标定。

- 包名：`checkbord_print_calib_toolbox`
- 命令：`checkbord-toolbox`
- 版本：`1.0.0`
- 环境：Windows 10/11，CPython 3.10 / 3.11（建议 3.11）

## 目录

1. [简介](#1-简介)
2. [工程结构](#2-工程结构)
3. [环境与安装](#3-环境与安装)
4. [快速运行 Demo](#4-快速运行-demo)
5. [配置说明](#5-配置说明)
6. [命令行说明](#6-命令行说明)
7. [Python 调用](#7-python-调用)
8. [质量门禁与产物使用限制](#8-质量门禁与产物使用限制)

## 1. 简介

本工具箱提供两项能力：

1. **制板**：按 `config.ini` 生成打印三件套（矢量 PDF、预览图、打印说明）。
2. **标定**：对 1 张或多张同一姿态的棋盘格图像求解相机内参和畸变，并写出可供后续使用的 XML。

## 2. 工程结构

```text
checkbord_print_calib_toolbox/
├── README.md
├── config.ini                          # 出厂配置
├── pyproject.toml
├── requirements.txt
├── assets/
│   ├── checkerboard/                   # 制板输出目录（出厂示例已生成）
│   │   ├── checkerboard.pdf            # 矢量打印文件，仅此文件用于印刷
│   │   ├── checkerboard_preview.png    # 预览图，仅供核对
│   │   └── 打印说明.txt
│   └── test_data/calibration/          # 默认标定读图目录
│       └── 说明.txt                    # 请将标定图像放到此目录
├── docs/
│   ├── 需求文档.md
│   └── 设计文档.md
├── src/checkbord_print_calib_toolbox/
│   ├── cli.py                          # 命令行入口
│   ├── board/                          # 制板
│   ├── calibration/                    # 标定
│   ├── common/
│   └── config/                         # ini 读取
└── tests/
```

## 3. 环境与安装

在工程根目录执行：

```bat
py -3.11 -m venv .venv
.\.venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
pip install -e .
```

说明：

1. 依赖只安装到独立虚拟环境，不要装到系统 Python。
2. 运行时依赖为 OpenCV 4.8.0、NumPy 1.26.4、reportlab 4.4.10、Pillow 13.0.0，以 `requirements.txt` 为准。
3. 不要将 OpenCV 升级到 5.x，也不要安装 `opencv-contrib-python`。

## 4. 快速运行 Demo

安装并激活虚拟环境后，在工程根目录执行下面两个示例。

### 4.1 生成打印三件套

```bat
checkbord-toolbox make-board --ini config.ini
```

等价写法：

```bat
python -m checkbord_print_calib_toolbox make-board --ini config.ini
```

成功后，产物写到 `assets/checkerboard/`（即 ini 中的 `out_dir`）：

1. `checkerboard.pdf`：矢量打印文件。交给印刷店时只使用这个文件。
2. `checkerboard_preview.png`：4.0 px/mm 预览图，仅供核对，不要用于打印。
3. `打印说明.txt`：UTF-8（带 BOM）文本，含实际留白和连续格跨距验收要求。

打印时请使用 **100% 实际尺寸**，关闭「适应页面」「适合纸张」和自动缩放。

### 4.2 相机标定

先将标定图像放到 `assets/test_data/calibration/`，或使用 `--image` 直接指定文件。建议同机位连拍 3～5 张，单张也可求解。连拍期间相机、镜头和标定板都必须保持静止。

从 ini 的 `input_dir` 读图：

```bat
checkbord-toolbox calibrate --ini config.ini
```

或者显式指定图像，顺序就是求解和验证使用的顺序：

```bat
checkbord-toolbox calibrate --ini config.ini --image first.bmp second.bmp third.bmp
```

成功且质量达标时退出码为 0；质量不达标、读图失败或参数错误时退出码非 0。只要已经求解，控制台会打印 RMS、验证 mean 和 p95。标定结果默认写到 `assets/calibration/checkerboard_calib.xml`。

采图时，机位、镜头和分辨率须与后续正式使用一致，标定板须吸风展平，并使用与生产相同的光源和工作距离。尽量让标定板充满画面，四周静区完整可见。

## 5. 配置说明

所有接口都要显式传入 ini 路径。ini 使用 UTF-8（可带 BOM），支持 `#`、`;` 行注释和行尾注释。相对路径一律相对 ini 所在目录。

随包 `config.ini` 只有三段：`[checkerboard]`、`[calibrate]`、`[debug]`。

要点：

1. `pattern_cols`、`pattern_rows`、`square_x_mm`、`square_y_mm` 默认不写出，分别跟随当前制板格数减一和 `square_mm`。
2. 打印后请用卡尺实测格距，再把实测值回填到两个 `square_*_mm` 键。只回填其中一个时，另一个仍跟随标称格距。
3. `target_mm_per_px=0.136` 表示正射图每像素对应的板面毫米数。它只改变物理覆盖范围和像素到毫米的换算，输出图像素宽高始终与标定输入相同。
4. `save_intermediate` 缺键按 `false`。设为 `true` 时，标定在 `qa_dir` 写 QA 图：验证成功且重检完成时为 4 张，正射重检失败时只保留已生成的前 3 张。

## 6. 命令行说明

统一入口为 `checkbord-toolbox`，也可用 `python -m checkbord_print_calib_toolbox`。

1. `make-board --ini <路径>`：生成打印三件套。
2. `calibrate --ini <路径> [--image <文件> ...]`：执行标定。

从目录扫描图像时：

1. 只读取 `input_dir` 当前一层，不递归。
2. 支持 BMP、PNG、JPG、JPEG、TIF、TIFF。
3. 跳过文件名主体含 `demo`（不区分大小写）或 `副本` 的文件，其余按完整路径字典序排列。
4. 任一图像读取失败都会终止本次标定，不会跳过坏图。
5. 多图必须是同一姿态的重复观测，角点按对应下标取算术均值。
6. QA 和正射验证使用排序后的第一张图。

## 7. Python 调用

```python
import cv2
from checkbord_print_calib_toolbox import CalibReport, calibrate, make_board, version

ok, err = make_board("config.ini")
image = cv2.imread("first.bmp", cv2.IMREAD_UNCHANGED)
report = CalibReport()
ok, err, report = calibrate([image], "config.ini", report)
```

说明：

1. `make_board` 返回 `(ok, err_msg)`，`calibrate` 返回 `(ok, err_msg, report)`。
2. 异常输入不会以异常形式抛给调用方。
3. `report.xml_path` 是解析后的绝对路径。
4. 图像只接受 8 位单通道、三通道和四通道数组。
5. XML 使用 OpenCV `FileStorage` 写出：`camera_matrix` 为 3×3，`dist_coeffs` 为 1×5，`rvec` 和 `tvec` 为 3×1，`created` 使用本地时间 `YYYY-MM-DDTHH:MM:SS`。

## 8. 质量门禁与产物使用限制

质量门禁要求同时满足：

1. RMS ≤ 0.3 px
2. 正射验证 mean ≤ 0.5 px

求解成功后，即使质量不达标，结果仍会覆盖 `[calibrate] out_xml`，QA 按调试开关保留，供排查问题。

禁止在 `ok=false` 或命令行退出码非 0 后，把该 XML 用于生产测量。此时文件只供诊断，须检查印刷精度、格距实测值和采图条件后重新标定。
