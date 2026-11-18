# 棋盘格制板与相机标定工具箱实施计划

> For agentic workers: REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

　　Goal: 按已确认需求与设计交付只含制板、相机标定两项能力的 Python 工程，并用真实采图完成自测。

　　Architecture: 采用 src 布局。配置模块统一处理 ini、缺省和跟随。制板、标定、内部正射各自独立。门面捕获异常，CLI 只负责参数、读图和结果输出。

　　Tech Stack: CPython 3.11、OpenCV 4.8.0、NumPy 1.26.4、reportlab 4.4.10、pytest。

　　Spec: `docs/需求文档.md`、`docs/设计文档.md`、`C:/Users/chenc/AppData/Local/Temp/kimi_checkbord_impl_task.md`

## Global Constraints

- 只在当前工程写实现，C++ 工程和全局 Kimi 配置保持只读。
- 不执行 git init、commit、push，不创建 `.git`。
- 包名和目录名保持 `checkbord_print_calib_toolbox`，只提供 `make-board`、`calibrate`。
- 依赖钉死 `opencv-python==4.8.0.76`、`numpy==1.26.4`、`reportlab==4.4.10`，Pillow 按实际安装结果钉版。
- 不把验收 BMP 复制进工程，验收图直接从已授权 C++ 目录读取。
- 质量门禁固定为 RMS ≤ 0.3 px 且 verify mean ≤ 0.5 px。对拍刻度固定为 0.136。
- 不达标仍写正式 XML，但接口、日志和 README 明确禁止在失败后启用它做生产测量。
- 不修改需求文档和设计文档正文。

## Review Focus

- 非法配置与异常输入：门面不得抛异常，测试覆盖空列表、错误数组、非法数值和缺失 ini。
- 多图输入：任一格式、尺寸或角点失败必须整次失败，测试覆盖第二张尺寸不一致与格式错误。
- 输出污染：制板校验失败不得创建三件套，标定测试每次使用全新空 QA 目录。
- 配置显式性：四个跟随键独立判断，测试覆盖注释键、部分回填、缺省 debug 和非 15 mm 告警。
- 正射边界：输出尺寸不随刻度改变，重检失败不得伪造 0 px 达标，测试覆盖失败构造和输出形状。

---

### Task 1: 基线核对与冻结输入

　　Files:
- Create: `tests/fixtures/calibration_manifest.txt`
- Read: C++ 基线中的制板、标定、正射、ini、读图与入口文件

　　Interfaces:
- Produces: 排序后的真实采图文件名清单，以及只读算法核对记录。

- [ ] 核对 C++ 基线提交与相关实现，确认文档中的公式、默认值和控制流。
- [ ] 用设计第 3.5 节规则扫描验收目录，将完整排序文件名写入清单。
- [ ] 检查已有 C++ 可执行程序能否在不改文件的情况下冻结基准。不能则记录原因。

### Task 2: 工程骨架、配置与制板

　　Files:
- Create: `pyproject.toml`、`requirements.txt`、`config.ini`
- Create: `src/checkbord_print_calib_toolbox/config/ini.py`
- Create: `src/checkbord_print_calib_toolbox/board/generator.py`
- Create: `src/checkbord_print_calib_toolbox/common/logger.py`
- Test: `tests/test_config.py`、`tests/test_board.py`

　　Interfaces:
- Produces: `load_config(ini_path)`、配置数据类、`generate_board(config) -> (bool, str)`。
- Produces: 可替换中文日志钩子，默认 INFO，WARN/ERROR 到 stderr。

- [ ] 先写配置失败测试：BOM、行尾注释、非法段头、数值前缀、相对 ini 路径、四个键独立跟随、告警显式性和 debug 缺键。
- [ ] 运行测试确认缺少实现而失败，再实现统一 ini 解析和配置数据类。
- [ ] 先写制板失败测试：出厂三件套、PDF 尺寸、预览尺寸、说明编码和模板、同奇偶、留白、非法参数、标记侵入、小棋盘和加大纸张。
- [ ] 运行测试确认失败后，实现先校验再建目录的 PDF、预览、说明生成流程。
- [ ] 运行 `pytest tests/test_config.py tests/test_board.py -v`，要求全部通过。

### Task 3: 图像读写与标定核心

　　Files:
- Create: `src/checkbord_print_calib_toolbox/common/image_io.py`
- Create: `src/checkbord_print_calib_toolbox/calibration/rectifier.py`
- Create: `src/checkbord_print_calib_toolbox/calibration/calibrator.py`
- Test: `tests/test_calibration.py`、`tests/test_image_io.py`

　　Interfaces:
- Consumes: Task 2 的配置对象与日志。
- Produces: `list_images(directory)`、`read_image(path)`、`calibrate_images(images, config) -> (bool, str, CalibReport)`。
- Produces: 内部正射构建、矫正和板面坐标逆变换，不暴露独立业务门面。

- [ ] 先写扫图和读图测试：扩展名、不递归、跳过 demo/副本、路径字典序、坏图、BMP 兜底和 8UC1/3/4 转灰度。
- [ ] 先写标定失败测试：空列表、格式、尺寸、缺角、非法内角点与异常不抛出门面。
- [ ] 实现 SB 检测、21×21 亚像素、多图算术均值、固定求解标志、5 项畸变和 XML 字段及回读校验。
- [ ] 实现中心锚点、方向符号、正射 remap、重检统计和四张 QA 的规则。
- [ ] 使用清单第一张和前三张运行真实图标定，核验矩阵形状、created、XML 回读、正射尺寸、QA 文件名和报告字段。
- [ ] 运行 `pytest tests/test_image_io.py tests/test_calibration.py -v`，要求全部通过。

### Task 4: 门面、CLI 与交付说明

　　Files:
- Create: `src/checkbord_print_calib_toolbox/__init__.py`、`__main__.py`、`cli.py`
- Create: `README.md` 与占位目录说明
- Test: `tests/test_facade_cli.py`

　　Interfaces:
- Produces: `version()`、`make_board(ini_path)`、`calibrate(board_images, ini_path, report=None)`。
- Produces: `checkbord-toolbox` 与 `python -m checkbord_print_calib_toolbox` 两个等价入口。

- [ ] 先写门面和 CLI 测试：版本、异常捕获、显式图顺序、目录读取、退出码、中文输出和未知命令。
- [ ] 实现门面就地填写报告，CLI 打印 RMS、mean、p95 和已产出的路径。
- [ ] 编写安装、采图、打印、质量禁令和两条命令示例，确保没有测量功能入口或配置段。
- [ ] 运行 `pytest tests/test_facade_cli.py -v`，要求全部通过。

### Task 5: 独立环境与完整验收

　　Files:
- Modify: `requirements.txt`、`pyproject.toml` 中 Pillow 的实际钉版
- Create: 任务书指定的仓库外实施报告

　　Interfaces:
- Consumes: 全部产品代码和测试。

- [ ] 用 `py -3.11 -m venv .venv` 创建环境，升级 pip，安装钉版依赖并以可编辑方式安装本工程。
- [ ] 确认 `cv2.__version__ == 4.8.0`，记录 OpenCV、NumPy、reportlab、Pillow 实际版本。
- [ ] 运行完整 pytest、真实 CLI、出厂制板和单张/多张标定，保存关键数值。
- [ ] 分别验证 save_intermediate 为 true、false、缺键，QA 目录均为空目录起步。
- [ ] 构造并运行 RMS 超限与正射验证失败用例，检查正式 XML、总门禁句和后续验证控制流。
- [ ] 若可获得不改 C++ 的同清单基准，按设计第 8.3 节计算偏差。否则明确记录未冻结原因。
- [ ] 检查工程无大图、无功能 3、无 Git 操作，文档与配置注释符合最终行为。
