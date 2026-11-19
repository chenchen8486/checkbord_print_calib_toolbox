import os
import sys


if getattr(sys, "frozen", False):
    EXE_OUTER_DIR = os.path.dirname(sys.executable)
else:
    EXE_OUTER_DIR = os.path.dirname(os.path.abspath(__file__))
    SRC_DIR = os.path.join(EXE_OUTER_DIR, "src")
    if os.path.isdir(SRC_DIR) and SRC_DIR not in sys.path:
        sys.path.insert(0, SRC_DIR)

INI_PATH = os.path.join(EXE_OUTER_DIR, "config.ini")

from checkbord_print_calib_toolbox import calibrate, make_board
from checkbord_print_calib_toolbox.common.image_io import ImageIoError, list_images, read_image
from checkbord_print_calib_toolbox.config.ini import ConfigError, load_config


def run_board():
    try:
        ok, err = make_board(INI_PATH)
        if not ok:
            print(f"制板失败: {err}")
            return
        cfg = load_config(INI_PATH)
        output_dir = cfg.checkerboard.out_dir
        print(f"PDF: {os.path.join(output_dir, 'checkerboard.pdf')}")
        print(f"预览图: {os.path.join(output_dir, 'checkerboard_preview.png')}")
        print(f"打印说明: {os.path.join(output_dir, '打印说明.txt')}")
        print("制板成功")
    except Exception as exc:
        print(f"制板失败: {exc}")


def run_calibration():
    try:
        cfg = load_config(INI_PATH)
        paths = list_images(cfg.calibrate.input_dir)
        if not paths:
            print(f"标定采图目录为空，请先把棋盘格采图放入: {cfg.calibrate.input_dir}")
            return
        images = []
        for path in paths:
            image = read_image(path)
            if image is None:
                print(f"图像读取失败: {path}")
                return
            images.append(image)
        ok, err, report = calibrate(images, INI_PATH)
        if report._solved:
            print(
                f"RMS {report.rms:.4f} px, verify mean {report.verify_mean_px:.3f} px, "
                f"p95 {report.verify_p95_px:.3f} px"
            )
        if report._xml_written:
            print(f"标定文件: {report.xml_path}")
        if cfg.debug.save_intermediate and os.path.isdir(cfg.calibrate.qa_dir):
            print(f"QA 目录: {cfg.calibrate.qa_dir}")
        if not ok:
            print(f"标定失败: {err}")
            return
        print("标定成功，质量门禁通过")
    except (ConfigError, ImageIoError) as exc:
        print(str(exc))
    except Exception as exc:
        print(f"标定失败: {exc}")


def reload_config():
    try:
        load_config(INI_PATH)
        print(f"配置文件已重新加载: {os.path.abspath(INI_PATH)}")
    except ConfigError as exc:
        print(str(exc))
    except Exception as exc:
        print(f"重新加载配置失败: {exc}")


def main():
    try:
        while True:
            print("\n========================================")
            print("棋盘格制板与相机标定工具箱")
            print(f"当前工作目录: {EXE_OUTER_DIR}")
            print("功能 1：制板")
            print("功能 2：标定")
            print("功能 3：重新加载 config.ini")
            print("其他输入：退出")
            print("========================================")
            try:
                choice = input("请选择功能号码: ").strip()
                if choice == "1":
                    run_board()
                elif choice == "2":
                    run_calibration()
                elif choice == "3":
                    reload_config()
                else:
                    break
            except KeyboardInterrupt:
                print("\n用户中断，程序退出。")
                break
            except EOFError:
                break
            except Exception as exc:
                print(f"操作失败: {exc}")
    finally:
        try:
            input("按回车键关闭窗口...")
        except EOFError:
            pass


if __name__ == "__main__":
    main()
