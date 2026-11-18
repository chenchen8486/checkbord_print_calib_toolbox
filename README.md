# 棋盘格制板与相机标定工具箱

　　本工程提供棋盘格打印三件套生成和相机标定两项能力。包名为 `checkbord_print_calib_toolbox`，命令为 `checkbord-toolbox`。支持 Windows 10/11、CPython 3.10/3.11，验收环境使用 CPython 3.11。

## 安装

　　在工程目录执行以下命令，依赖只安装到独立虚拟环境：

```bat
py -3.11 -m venv .venv
.\.venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
pip install -e .
```

　　运行时需要 OpenCV 4.8.0、NumPy 1.26.4、reportlab 4.4.10 和 Pillow 13.0.0，具体 wheel 包版本见 `requirements.txt`。OpenCV 不得升级到 5.x，也不要安装 `opencv-contrib-python`。

## 配置

　　所有接口都显式接收 ini 路径。ini 使用 UTF-8，可带 BOM，支持 `#` 和 `;` 行注释、行尾注释。相对路径一律相对 ini 所在目录。

　　随包 `config.ini` 只有 `[checkerboard]`、`[calibrate]`、`[debug]` 三段。`pattern_cols`、`pattern_rows`、`square_x_mm`、`square_y_mm` 默认不写出，分别跟随当前制板格数减一和 `square_mm`。打印后用卡尺实测格距，再把实测值回填到两个 `square_*_mm` 键。只回填其中一个键时，另一个仍跟随标称格距。

　　`target_mm_per_px=0.136` 表示正射图每像素对应的板面毫米数。它只改变物理覆盖范围和像素到毫米的换算系数，输出图像素宽高始终与标定输入相同。

　　`save_intermediate` 缺键按 `false`。设为 `true` 时，标定在 `qa_dir` 写 QA 图。验证成功且重检完成时为 4 张，正射重检失败时只保留已生成的前 3 张。

## 生成打印文件

```bat
checkbord-toolbox make-board --ini config.ini
```

　　也可使用等价的模块入口：

```bat
python -m checkbord_print_calib_toolbox make-board --ini config.ini
```

　　产物位于 `[checkerboard] out_dir`：

- `checkerboard.pdf`：矢量打印文件，交付打印店时只使用这个文件。
- `checkerboard_preview.png`：4.0 px/mm 的人工核对图，仅供核对，勿用于打印。
- `打印说明.txt`：带 BOM 的 UTF-8 文本，包含实际留白和连续格跨距验收要求。

　　打印时使用 100% 实际尺寸，关闭适应页面、适合纸张和自动缩放。纸张、格数、格边长、最小留白及方向标记规则以 ini 和打印说明为准。

## 相机标定

　　建议同机位连拍 3～5 张，单张也可求解。连拍期间相机、镜头和标定板都必须保持静止。机位、镜头和分辨率须与后续正式使用一致，标定板须吸风展平，并使用与生产相同的光源和工作距离。尽量让标定板充满画面，四周静区完整可见。

　　从 ini 的 `input_dir` 读图：

```bat
checkbord-toolbox calibrate --ini config.ini
```

　　显式指定一张或多张图，顺序就是求解和验证使用的顺序：

```bat
checkbord-toolbox calibrate --ini config.ini --image first.bmp second.bmp third.bmp
```

　　目录扫描只读取当前一层，支持 BMP、PNG、JPG、JPEG、TIF、TIFF，跳过文件名主体含 `demo`（不区分大小写）或 `副本` 的文件，其余按完整路径字典序排列。任一图像读取失败都会终止本次标定，不会跳过坏图。多图必须是同一姿态的重复观测，角点按对应下标取算术均值。QA 和正射验证使用第一张图。

　　成功且质量达标时退出码为 0。质量不达标、读图失败或参数错误时退出码非 0。只要已求解，控制台会打印 RMS、验证 mean 和 p95。

## Python 门面

```python
import cv2
from checkbord_print_calib_toolbox import CalibReport, calibrate, make_board, version

ok, err = make_board("config.ini")
image = cv2.imread("first.bmp", cv2.IMREAD_UNCHANGED)
report = CalibReport()
ok, err, report = calibrate([image], "config.ini", report)
```

　　门面返回 `(ok, err_msg)` 或 `(ok, err_msg, report)`，异常输入不会以异常形式抛给调用方。`report.xml_path` 是解析后的绝对路径。图像只接受 8 位单通道、三通道和四通道数组。

　　XML 使用 OpenCV `FileStorage` 写出并回读自检。`camera_matrix` 为 3×3，`dist_coeffs` 为 1×5，`rvec` 和 `tvec` 为 3×1，`created` 使用本地时间 `YYYY-MM-DDTHH:MM:SS`。

## 质量门禁与产物使用限制

　　质量门禁要求 RMS ≤ 0.3 px，且正射验证 mean ≤ 0.5 px。两项必须同时满足。求解成功后，即使质量不达标，结果仍覆盖 `[calibrate] out_xml`，QA 按调试开关保留，供排查问题。

　　禁止现场在 `ok=false` 或命令行非 0 后启用该 XML 做生产测量。此时文件只供诊断，须检查印刷精度、格距实测值和采图条件后重新标定。

## 自测

　　开发自测需要额外安装测试依赖：

```bat
pip install -e ".[test]"
pytest -v
```

　　真实采图直接读取 `D:\project\c++\Calibrate_and_Measure\assets\test_data\calibration`，不复制进本工程。冻结顺序见 `tests/fixtures/calibration_manifest.txt`。每次 QA 自测使用全新空目录，避免旧图影响判断。
