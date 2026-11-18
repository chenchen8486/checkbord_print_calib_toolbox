from pathlib import Path

import pytest

from checkbord_print_calib_toolbox.common.image_io import read_image


CALIBRATION_DIR = Path(r"D:/project/c++/Calibrate_and_Measure/assets/test_data/calibration")


@pytest.fixture(scope="session")
def calibration_images():
    manifest = Path(__file__).parent / "fixtures" / "calibration_manifest.txt"
    names = manifest.read_text(encoding="utf-8").splitlines()
    images = []
    for name in names[:3]:
        image = read_image(CALIBRATION_DIR / name)
        assert image is not None
        images.append(image)
    return images
