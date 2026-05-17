from typing import Callable
import typing
import time

from PyQt6.QtWidgets import QFileDialog, QMessageBox
from utils.decorators import singleton
from services.thrust_service import ThrustService
import numpy as np

# This is for basic LP filtering
# If both |n - n_prev| and |n+1 - n| exceed this value the middle point is
# replaced with the mean of its neighbors.
SPIKE_THRESHOLD = 50_000


@singleton
class DataService:
    def __init__(self):
        self.data = {
            "time": np.array([], dtype=np.long),
            "timestamps": np.array([], dtype=np.float64),
            "thrust": np.array([], dtype=np.long),
            "torqueA": np.array([], dtype=np.long),
            "torqueB": np.array([], dtype=np.long),
            "torque": np.array([], dtype=np.float64),
            "current": np.array([], dtype=np.float64),
            "voltage": np.array([], dtype=np.float64),
            "power": np.array([], dtype=np.float64),
            "throttle": np.array([], dtype=np.int64),
        }

        self.calibrationPoints: dict[str, dict[str, typing.Optional[float]]] = {
            "thrust": {"sensitivity": None, "zero": None},
            "torqueA": {"sensitivity": None, "zero": None},
            "torqueB": {"sensitivity": None, "zero": None},
            "torque": {"sensitivity": None, "zero": None},
        }
        self.callbacks = []
        # One-point buffer for spike detection (None = no point buffered yet)
        self._pending: typing.Optional[dict] = None

    def get_calibrated_value(self, sensor: str) -> typing.Optional[float]:
        if sensor not in self.calibrationPoints:
            raise ValueError(f"Unknown sensor: {sensor}")
        if self.data[sensor].size == 0:
            return None
        cal = self.calibrationPoints[sensor]
        latest = float(self.data[sensor][-1])
        sensitivity, zero = cal["sensitivity"], cal["zero"]
        if sensitivity is None or zero is None:
            return latest
        return (latest - zero) * sensitivity

    def get_calibrated_series(self, sensor: str) -> np.ndarray:
        if sensor not in self.calibrationPoints:
            raise ValueError(f"Unknown sensor: {sensor}")
        raw = self.data[sensor].astype(np.float64)
        cal = self.calibrationPoints[sensor]
        sensitivity, zero = cal["sensitivity"], cal["zero"]
        if sensitivity is not None and zero is not None:
            return (raw - zero) * sensitivity
        return raw

    def add_data(
        self, thrust: int, torqueA: int, torqueB: int, current: float, voltage: float
    ):
        incoming = {
            "thrust": thrust,
            "torqueA": torqueA,
            "torqueB": torqueB,
            "current": current,
            "voltage": voltage,
            "timestamp": time.time(),
        }

        if self._pending is None:
            # First point ever - buffer it, nothing to commit yet
            self._pending = incoming
            return

        # Spike check: if both derivatives around the pending point exceed the
        # threshold, the pending point is a spike - replace it with the mean of
        # its two neighbours.
        if self.data["timestamps"].size > 0:
            for sensor in ("thrust", "torqueA", "torqueB"):
                prev = int(self.data[sensor][-1])
                n = self._pending[sensor]
                n1 = incoming[sensor]
                if abs(n - prev) > SPIKE_THRESHOLD and abs(n1 - n) > SPIKE_THRESHOLD:
                    self._pending[sensor] = (prev + n1) // 2

        self._commit(self._pending)
        self._pending = incoming
        self.notify_callbacks()

    def _commit(self, point: dict):
        self.data["time"] = np.append(
            self.data["time"],
            self.data["time"][-1] + 1 if self.data["time"].size > 0 else 0,
        )
        self.data["timestamps"] = np.append(self.data["timestamps"], point["timestamp"])
        self.data["thrust"] = np.append(self.data["thrust"], point["thrust"])
        self.data["torqueA"] = np.append(self.data["torqueA"], point["torqueA"])
        self.data["torqueB"] = np.append(self.data["torqueB"], point["torqueB"])
        self.data["torque"] = np.append(
            self.data["torque"],
            self._compute_torque(point["torqueA"], point["torqueB"]),
        )
        self.data["current"] = np.append(
            self.data["current"], abs(point["current"]) / 1000.0
        )
        self.data["voltage"] = np.append(self.data["voltage"], point["voltage"])
        self.data["power"] = np.append(
            self.data["power"],
            abs(point["current"] * point["voltage"] / 1000.0 / 1000.0),
        )
        self.data["throttle"] = np.append(
            self.data["throttle"], ThrustService().get_throttle()
        )

    def _compute_torque(self, raw_A: int, raw_B: int) -> float:
        sens_A = self.calibrationPoints["torqueA"]["sensitivity"]
        zero_A = self.calibrationPoints["torqueA"]["zero"]
        sens_B = self.calibrationPoints["torqueB"]["sensitivity"]
        zero_B = self.calibrationPoints["torqueB"]["zero"]
        zero_torque = self.calibrationPoints["torque"]["zero"]

        if (
            sens_A is None
            or zero_A is None
            or sens_B is None
            or zero_B is None
            or zero_torque is None
        ):
            return np.nan
        calibrated_A = (raw_A - float(zero_A)) * float(sens_A)
        calibrated_B = (raw_B - float(zero_B)) * float(sens_B)

        torque_sens = self.calibrationPoints["torque"]["sensitivity"]
        if torque_sens is not None:
            return torque_sens * ((calibrated_A - calibrated_B) - float(zero_torque))
        else:
            return np.nan

    def set_zero(self, sensor: str, zero: float):
        if sensor not in self.calibrationPoints:
            raise ValueError(f"Unknown sensor: {sensor}")
        self.calibrationPoints[sensor]["zero"] = zero
        self.notify_callbacks()

    def set_sensitivity(self, sensor: str, sensitivity: float):
        if sensor not in self.calibrationPoints:
            raise ValueError(f"Unknown sensor: {sensor}")
        self.calibrationPoints[sensor]["sensitivity"] = sensitivity
        self.notify_callbacks()

    def export_to_csv(self, start_idx: int, end_idx: int):
        path, _ = QFileDialog.getSaveFileName(
            None, "Export to CSV", "", "CSV Files (*.csv)"
        )
        if not path:
            return

        timestamps = self.data["timestamps"][start_idx:end_idx]
        thrust_raw = self.data["thrust"][start_idx:end_idx]
        thrust_gf = self.get_calibrated_series("thrust")[start_idx:end_idx]
        torque_ncm = self.data["torque"][start_idx:end_idx] * 100
        power = self.data["power"][start_idx:end_idx]
        voltage = self.data["voltage"][start_idx:end_idx]
        current = self.data["current"][start_idx:end_idx]
        throttle = self.data["throttle"][start_idx:end_idx]

        t0 = timestamps[0] if len(timestamps) > 0 else 0.0
        with open(path, "w") as f:
            f.write(
                "timestamp_s,thrust_raw,thrust_gf,torque_ncm,efficiency_gpw,voltage_mv,current_a,throttle_pct\n"
            )
            for ts, tr, tg, tq, pw, v, c, th in zip(
                timestamps,
                thrust_raw,
                thrust_gf,
                torque_ncm,
                power,
                voltage,
                current,
                throttle,
            ):
                torque_str = f"{tq:.4f}" if not np.isnan(tq) else ""
                efficiency_str = f"{tg / pw:.4f}" if pw > 0 else ""
                f.write(
                    f"{ts - t0:.6f},{int(tr)},{tg:.3f},{torque_str},{efficiency_str},{v:.3f},{c:.6f},{int(th)}\n"
                )

    def user_request_clear_data(self):
        if (
            QMessageBox.question(
                None,
                "Clear Data",
                "Are you sure you want to clear all data? This action cannot be undone.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            == QMessageBox.StandardButton.Yes
        ):
            self.data = {
                "time": np.array([], dtype=np.long),
                "timestamps": np.array([], dtype=np.float64),
                "thrust": np.array([], dtype=np.long),
                "torqueA": np.array([], dtype=np.long),
                "torqueB": np.array([], dtype=np.long),
                "torque": np.array([], dtype=np.float64),
                "current": np.array([], dtype=np.float64),
                "voltage": np.array([], dtype=np.float64),
                "power": np.array([], dtype=np.float64),
                "throttle": np.array([], dtype=np.int64),
            }
            self._pending = None
            self.notify_callbacks()

    def register_callback(self, callback: Callable):
        self.callbacks.append(callback)

    def notify_callbacks(self):
        for callback in self.callbacks:
            callback()
