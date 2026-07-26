import numpy as np
from PIL import Image


def generate_test_pattern(
    path: str,
    width: int = 1152,
    height: int = 864,
) -> str:
    arr = np.zeros((height, width, 3), dtype=np.uint8)
    arr[:, :, 0] = 30
    arr[50:100, 50:200] = [255, 0, 0]
    arr[200:250, 50:200] = [0, 255, 0]
    arr[350:400, 50:200] = [0, 0, 255]
    arr[500:550, 50:200] = [255, 255, 0]

    arr[50:100, 400:800, :] = [200, 200, 200]

    Image.fromarray(arr).save(path)
    return path
