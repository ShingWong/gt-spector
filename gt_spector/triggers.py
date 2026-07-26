import time

import numpy as np


class Triggers:
    def __init__(self, session):
        self._session = session

    def wait_for_color(
        self, x: int, y: int,
        lo: tuple[int, int, int],
        hi: tuple[int, int, int],
        timeout: float = 600,
    ) -> tuple[bool, np.ndarray]:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self._session.refresh()
            px = self._session.get_pixel(x, y)
            if all(lo[i] <= px[i] <= hi[i] for i in range(3)):
                return True, self._session.frame
            time.sleep(0.1)
        return False, self._session.frame

    def wait_for_change(
        self, region: tuple[int, int, int, int] | None = None,
        timeout: float = 600,
    ) -> tuple[bool, np.ndarray]:
        deadline = time.monotonic() + timeout
        baseline = self._session.frame.copy()
        while time.monotonic() < deadline:
            self._session.refresh()
            curr = self._session.frame
            if region:
                x1, y1, x2, y2 = region
                if not np.array_equal(curr[y1:y2, x1:x2], baseline[y1:y2, x1:x2]):
                    return True, curr
            else:
                if not np.array_equal(curr, baseline):
                    return True, curr
            time.sleep(0.1)
        return False, self._session.frame
