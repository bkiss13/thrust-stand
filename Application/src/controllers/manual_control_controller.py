import math
from typing import Callable
from PyQt6.QtCore import QTimer

from views.ui_ManualControl import Ui_Form as ManualControlView
from services.thrust_service import ThrustService
from services.data_service import DataService
from views.live_plot import LivePlot


class ManualControlController:
    def __init__(self, view: ManualControlView, on_return: Callable):
        self.view = view
        self.thrustService = ThrustService()
        self.dataService = DataService()

        self._recording = False
        self._rec_start_idx = 0
        self._rec_end_idx = 0

        self._live_plot = LivePlot(view.plotArea, view.plotContainer)
        self._connect_signals(on_return)
        self.dataService.register_callback(self._update_metrics)

        self._timer = QTimer()
        self._timer.timeout.connect(self._live_plot.update)
        self._timer.start(16)  # ~60 Hz

    def _connect_signals(self, on_return: Callable):
        def on_return_with_safety():
            self.thrustService.set_throttle(0)
            on_return()

        self.view.returnButton.clicked.connect(on_return_with_safety)
        self.view.btnSnapshot.hide()  # TODO: implement snapshot export
        self.view.btnClearData.clicked.connect(DataService().user_request_clear_data)
        self.view.btnRecording.clicked.connect(self._on_recording_toggle)
        self.view.btnExport.clicked.connect(self._export)
        self.view.displaySelectGroup.buttonClicked.connect(
            lambda btn: self._live_plot.set_mode(btn.text())
        )
        self.view.throttleSlider.valueChanged.connect(self._on_throttle_slider)
        self.view.throttleSpinBox.valueChanged.connect(self._on_throttle_spinbox)

    def _on_throttle_slider(self, value: int):
        self.view.throttleSpinBox.blockSignals(True)
        self.view.throttleSpinBox.setValue(value)
        self.view.throttleSpinBox.blockSignals(False)
        self.thrustService.set_throttle(value)

    def _on_throttle_spinbox(self, value: int):
        self.view.throttleSlider.blockSignals(True)
        self.view.throttleSlider.setValue(value)
        self.view.throttleSlider.blockSignals(False)
        self.thrustService.set_throttle(value)

    def _on_recording_toggle(self):
        if not self._recording:
            self._recording = True
            self._rec_start_idx = len(self.dataService.data["timestamps"])
            self.view.btnRecording.setText("Stop Recording")
            self.view.btnExport.setEnabled(False)
        else:
            self._recording = False
            self._rec_end_idx = len(self.dataService.data["timestamps"])
            self.view.btnRecording.setText("Begin Recording")
            if self._rec_end_idx > self._rec_start_idx:
                self.view.btnExport.setEnabled(True)

    def _export(self):
        self.dataService.export_to_csv(self._rec_start_idx, self._rec_end_idx)

    def _update_metrics(self):
        d = self.dataService.data
        if d["timestamps"].size == 0:
            return

        # Current Data panel
        thrust_cal = self.dataService.calibrationPoints["thrust"]
        if thrust_cal["sensitivity"] is None or thrust_cal["zero"] is None:
            self.view.lblThrust.setText("Uncalibrated")
        else:
            thrust_g = self.dataService.get_calibrated_value("thrust")
            if thrust_g is not None:
                self.view.lblThrust.setText(f"{thrust_g:.1f} gf")

        self.view.lblVoltage.setText(f"{d['voltage'][-1] / 1000.0:.3f} V")
        self.view.lblCurrent.setText(f"{d['current'][-1]:.3f} A")
        power_w = d["power"][-1]
        self.view.lblPower.setText(f"{power_w:.3f} W")
        thrust_cal = self.dataService.calibrationPoints["thrust"]
        if thrust_cal["sensitivity"] is not None and thrust_cal["zero"] is not None and power_w > 0:
            thrust_g = self.dataService.get_calibrated_value("thrust")
            if thrust_g is not None:
                self.view.lblEfficiency.setText(f"{thrust_g / power_w:.2f} g/W")
        else:
            self.view.lblEfficiency.setText("Uncalibrated")

        torque_nm = d["torque"][-1] if d["torque"].size > 0 else float("nan")
        self.view.lblTorque.setText(
            f"{torque_nm * 100:.2f} N-cm" if not math.isnan(torque_nm) else "Uncalibrated"
        )

        # Debug Data panel (raw load-cell counts)
        self.view.lblThrustCell.setText(str(int(d["thrust"][-1])))
        self.view.lblTorqueCellA.setText(str(int(d["torqueA"][-1])))
        self.view.lblTorqueCellB.setText(str(int(d["torqueB"][-1])))
