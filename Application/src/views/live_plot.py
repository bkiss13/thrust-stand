import time
from typing import Optional

import numpy as np
import pyqtgraph as pg
from PyQt6 import QtWidgets

from services.data_service import DataService
from services.thrust_service import ThrustService
from views.ui_MultiPlot import Ui_Form as MultiPlotUi

WINDOW = 15.0

_FS = {"font-size": "18pt"}
_FS_SM = {"font-size": "14pt"}


def _add_secondary_axis(
    plot: pg.PlotWidget,
    label: str,
    units: str,
    color: str,
    font_kw: dict,
    y_range: Optional[tuple] = None,
) -> tuple[pg.PlotCurveItem, pg.ViewBox]:
    """
    Attach a second ViewBox + PlotCurveItem to the right Y-axis of `plot`.
    Returns (curve, viewbox).
    """
    vb = pg.ViewBox()
    plot.scene().addItem(vb)
    plot.showAxis("right")
    ax = plot.getAxis("right")
    ax.linkToView(vb)
    ax.setLabel(label, units=units, **font_kw)
    vb.setXLink(plot)
    if y_range is not None:
        vb.setYRange(*y_range)
    else:
        vb.enableAutoRange(axis="y")
    curve = pg.PlotCurveItem(pen=pg.mkPen(color=color, width=2))
    vb.addItem(curve)

    def _sync():
        vb.setGeometry(plot.getViewBox().sceneBoundingRect())

    plot.getViewBox().sigResized.connect(_sync)
    return curve, vb


class LivePlot:
    """
    Manages all live sensor plots for a test-bench page.

    Args:
        mono_widget:     The pg.PlotWidget used for single-sensor display.
        multi_container: Optional QWidget with an existing layout. When provided,
                         a 2×2 MultiPlot widget is added to it and "All Sensors"
                         mode becomes available.
    """

    def __init__(
        self,
        mono_widget: pg.PlotWidget,
        multi_container: Optional[QtWidgets.QWidget] = None,
    ):
        self._data = DataService()
        self._thrust_svc = ThrustService()
        self._cmd_ts: list[float] = []
        self._cmd_vals: list[float] = []

        self._setup_mono(mono_widget)

        self._has_multi = multi_container is not None
        if self._has_multi:
            self._setup_multi(multi_container)

        # Set initial visibility to match the default "All Sensors" checked state
        default = "All Sensors" if self._has_multi else "Thrust"
        self._mode = default
        self._apply_visibility(default)

    def _setup_mono(self, widget: pg.PlotWidget):
        self._mono = widget
        widget.setLabel("bottom", "Time", units="s", **_FS)
        widget.setContentsMargins(10, 10, 10, 10)
        self._mono_curve = widget.plot(pen=pg.mkPen(color="b", width=2))

        self._mono_cmd_curve, self._mono_cmd_vb = _add_secondary_axis(
            widget, "Throttle Command", "%", "r", _FS, y_range=(0, 100)
        )
        widget.getAxis("right").hide()
        self._mono_cmd_curve.hide()

    def _setup_multi(self, container: QtWidgets.QWidget):
        self._multi_widget = QtWidgets.QWidget()
        multi_ui = MultiPlotUi()
        multi_ui.setupUi(self._multi_widget)
        container.layout().addWidget(self._multi_widget)

        # plotA - Thrust (g, blue) + Throttle command (%, red)
        multi_ui.plotA.setLabel("left", "Thrust", units="g", **_FS_SM)
        multi_ui.plotA.setLabel("bottom", "Time", units="s", **_FS_SM)
        multi_ui.plotA.enableAutoRange(axis="y")
        self._mA_thrust = multi_ui.plotA.plot(pen=pg.mkPen(color="b", width=2))
        self._mA_cmd, _ = _add_secondary_axis(
            multi_ui.plotA, "Throttle", "%", "r", _FS_SM, y_range=(0, 100)
        )
        self._plot_A = multi_ui.plotA

        # plotB - Torque (N·cm, green) + Throttle command (%, red)
        multi_ui.plotB.setLabel("left", "Torque", units="N·cm", **_FS_SM)
        multi_ui.plotB.setLabel("bottom", "Time", units="s", **_FS_SM)
        multi_ui.plotB.enableAutoRange(axis="y")
        self._mB_torque = multi_ui.plotB.plot(pen=pg.mkPen(color="g", width=2))
        self._mB_cmd, _ = _add_secondary_axis(
            multi_ui.plotB, "Throttle", "%", "r", _FS_SM, y_range=(0, 100)
        )
        self._plot_B = multi_ui.plotB

        # plotC - Current (A, blue) + Voltage (V, red)
        multi_ui.plotC.setLabel("left", "Current", units="A", **_FS_SM)
        multi_ui.plotC.setLabel("bottom", "Time", units="s", **_FS_SM)
        multi_ui.plotC.enableAutoRange(axis="y")
        self._mC_current = multi_ui.plotC.plot(pen=pg.mkPen(color="b", width=2))
        self._mC_voltage, _ = _add_secondary_axis(
            multi_ui.plotC, "Voltage", "V", "r", _FS_SM
        )
        self._plot_C = multi_ui.plotC

        # plotD - Power (W, blue) + Throttle command (%, red)
        multi_ui.plotD.setLabel("left", "Power", units="W", **_FS_SM)
        multi_ui.plotD.setLabel("bottom", "Time", units="s", **_FS_SM)
        multi_ui.plotD.enableAutoRange(axis="y")
        self._mD_power = multi_ui.plotD.plot(pen=pg.mkPen(color="b", width=2))
        self._mD_cmd, _ = _add_secondary_axis(
            multi_ui.plotD, "Throttle", "%", "r", _FS_SM, y_range=(0, 100)
        )
        self._plot_D = multi_ui.plotD

    def set_mode(self, mode: str):
        self._mode = mode
        self._apply_visibility(mode)

        if mode == "Thrust":
            self._mono.setLabel("left", "Thrust", units="g", **_FS)
            self._mono.enableAutoRange(axis="y")
            self._mono.getAxis("right").show()
            self._mono_cmd_curve.show()
            self._mono_curve.setPen(pg.mkPen(color="b", width=2))
        elif mode == "Torque":
            self._mono.setLabel("left", "Torque", units="N·cm", **_FS)
            self._mono.enableAutoRange(axis="y")
            self._mono.getAxis("right").show()
            self._mono_cmd_curve.show()
            self._mono_curve.setPen(pg.mkPen(color="g", width=2))
        elif mode == "Power, Efficiency":
            self._mono.setLabel("left", "Power", units="W", **_FS)
            self._mono.enableAutoRange(axis="y")
            self._mono.getAxis("right").show()
            self._mono_cmd_curve.show()
            self._mono_curve.setPen(pg.mkPen(color="b", width=2))

    def update(self):
        """Call from the controller's timer tick (~60 Hz)."""
        self._cmd_ts.append(time.time())
        self._cmd_vals.append(self._thrust_svc.get_throttle())

        if self._mode == "Thrust":
            self._update_mono_calibrated("thrust")
        elif self._mode == "Torque":
            self._update_mono_torque()
        elif self._mode == "Power, Efficiency":
            self._update_mono_raw("power")
        elif self._mode == "All Sensors" and self._has_multi:
            self._update_multi()

    def _apply_visibility(self, mode: str):
        is_multi = mode == "All Sensors"
        self._mono.setVisible(not is_multi)
        if self._has_multi:
            self._multi_widget.setVisible(is_multi)

    def _window_mask(self, ts: np.ndarray):
        """Return (mask, t0) for the last WINDOW seconds, or (None, None) if empty."""
        if ts.size == 0:
            return None, None
        return ts >= ts[-1] - WINDOW, ts[0]

    def _cmd_in_window(self, now: float, t0: float):
        """Return (t_rel, values) for throttle command in the last WINDOW seconds."""
        if not self._cmd_ts:
            return None, None
        cmd_ts = np.asarray(self._cmd_ts)
        cmd_vals = np.asarray(self._cmd_vals)
        mask = cmd_ts >= now - WINDOW
        if not mask.any():
            return None, None
        return cmd_ts[mask] - t0, cmd_vals[mask]

    def _set_xrange(self, plot: pg.PlotWidget, t_rel: np.ndarray):
        x_end = float(t_rel[-1]) if t_rel.size > 0 else 0.0
        plot.setXRange(max(0.0, x_end - WINDOW), x_end, padding=0.0)

    def _update_mono_calibrated(self, sensor: str):
        ts = self._data.data["timestamps"]
        mask, t0 = self._window_mask(ts)
        if mask is None:
            return
        t_rel = ts[mask] - t0
        values = self._data.get_calibrated_series(sensor)[mask]
        self._mono_curve.setData(t_rel, values)
        self._set_xrange(self._mono, t_rel)
        cmd_t, cmd_v = self._cmd_in_window(float(ts[-1]), t0)
        if cmd_t is not None:
            self._mono_cmd_curve.setData(cmd_t, cmd_v)

    def _update_mono_torque(self):
        ts = self._data.data["timestamps"]
        mask, t0 = self._window_mask(ts)
        if mask is None:
            return
        t_rel = ts[mask] - t0
        values = self._data.data["torque"][mask] * 100  # N·m → N·cm
        self._mono_curve.setData(t_rel, values)
        self._set_xrange(self._mono, t_rel)
        cmd_t, cmd_v = self._cmd_in_window(float(ts[-1]), float(t0))
        if cmd_t is not None:
            self._mono_cmd_curve.setData(cmd_t, cmd_v)

    def _update_mono_raw(self, key: str):
        ts = self._data.data["timestamps"]
        mask, t0 = self._window_mask(ts)
        if mask is None:
            return
        t_rel = ts[mask] - t0
        values = self._data.data[key][mask]
        self._mono_curve.setData(t_rel, values)
        self._set_xrange(self._mono, t_rel)
        cmd_t, cmd_v = self._cmd_in_window(float(ts[-1]), t0)
        if cmd_t is not None:
            self._mono_cmd_curve.setData(cmd_t, cmd_v)

    def _update_multi(self):
        ts = self._data.data["timestamps"]
        mask, t0 = self._window_mask(ts)
        if mask is None:
            return
        t_rel = ts[mask] - t0
        now = float(ts[-1])
        cmd_t, cmd_v = self._cmd_in_window(now, t0)

        # plotA: Thrust + throttle command
        thrust = self._data.get_calibrated_series("thrust")[mask]
        self._mA_thrust.setData(t_rel, thrust)
        self._set_xrange(self._plot_A, t_rel)
        if cmd_t is not None:
            self._mA_cmd.setData(cmd_t, cmd_v)

        # plotB: Torque (N·m → N·cm) + throttle command
        torque = self._data.data["torque"][mask] * 100
        self._mB_torque.setData(t_rel, torque)
        self._set_xrange(self._plot_B, t_rel)
        if cmd_t is not None:
            self._mB_cmd.setData(cmd_t, cmd_v)

        # plotC: Current + Voltage
        self._mC_current.setData(t_rel, self._data.data["current"][mask])
        self._mC_voltage.setData(t_rel, self._data.data["voltage"][mask])
        self._set_xrange(self._plot_C, t_rel)

        # plotD: Power + throttle command
        self._mD_power.setData(t_rel, self._data.data["power"][mask])
        self._set_xrange(self._plot_D, t_rel)
        if cmd_t is not None:
            self._mD_cmd.setData(cmd_t, cmd_v)
