from utils.decorators import singleton


@singleton
class ThrustService:
    def __init__(self):
        self._throttle = 0

    def set_throttle(self, throttle: int) -> int:
        clamped = max(0, min(100, throttle))
        self._throttle = clamped

        return clamped

    def get_throttle(self) -> int:
        return self._throttle
