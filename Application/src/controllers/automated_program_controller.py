import math
import time
from typing import Callable, Union
from PyQt6.QtGui import QSyntaxHighlighter, QTextCharFormat, QFont, QColor
from PyQt6.QtWidgets import QFileDialog, QFrame, QHBoxLayout, QButtonGroup, QMessageBox
from PyQt6.QtCore import QRegularExpression, QObject, QTimer, Qt
from views.ui_ProgramControl import Ui_Form as ProgramControlView
from utils.program_parser import ProgramParser
from services.thrust_service import ThrustService
from services.data_service import DataService
from views.live_plot import LivePlot

# language commands
# delay number numberType sec|ms : delay for number seconds or milliseconds. example: `delay 5 sec` or `delay 500 ms`
# throttle number : set throttle to number percent. example: `throttle 50` sets throttle to 50%. must be between 0 and 100.
# ramp number number sec|ms : ramp throttle from current value to number percent over number seconds or milliseconds. example: `ramp 100 5 sec` ramps throttle to 100% over 5 seconds.


class ProgramHighlighter(QSyntaxHighlighter):
    def __init__(self, document, error_map_ref=None):
        super().__init__(document)
        self._error_map_ref = error_map_ref

        keyword_format = QTextCharFormat()
        keyword_format.setForeground(QColor("lightblue"))
        keyword_format.setFontWeight(QFont.Weight.Bold)

        time_unit_format = QTextCharFormat()
        time_unit_format.setForeground(QColor("#ff6b6b"))  # light red

        number_format = QTextCharFormat()
        number_format.setForeground(QColor("yellow"))

        comment_format = QTextCharFormat()
        comment_format.setForeground(QColor("gray"))
        comment_format.setFontItalic(True)

        self._rules = [
            (
                QRegularExpression(r"\b(delay|throttle|ramp)\b"),
                keyword_format,
            ),  # keywords
            (QRegularExpression(r"\b(sec|ms)\b"), time_unit_format),  # time units
            (QRegularExpression(r"\b\d+(\.\d+)?\b"), number_format),  # numbers
            (QRegularExpression(r"#[^\n]*"), comment_format),  # comments (must be last)
        ]

    def highlightBlock(self, text: Union[str, None]):
        if not text:
            return

        for pattern, fmt in self._rules:
            it = pattern.globalMatch(text)
            while it.hasNext():
                match = it.next()
                self.setFormat(match.capturedStart(), match.capturedLength(), fmt)

        # Check if this line has an error using the error map
        line_num = self.currentBlock().blockNumber() + 1
        if self._error_map_ref and line_num in self._error_map_ref:
            underline = QTextCharFormat()
            underline.setUnderlineStyle(QTextCharFormat.UnderlineStyle.SingleUnderline)
            underline.setUnderlineColor(QColor("red"))
            self.setFormat(0, len(text), underline)


class AutomatedProgramController(QObject):
    def __init__(self, view: ProgramControlView, on_return: Callable):
        super().__init__()
        self._view = view
        self.thrustService = ThrustService()
        self.dataService = DataService()

        # Execution state
        self._state = "IDLE"  # "IDLE" | "RUNNING"
        self._instructions = []
        self._current_idx = 0
        self._instruction_start_ms = 0.0
        self._ramp_start_throttle = 0
        self._run_start_idx = 0
        self._run_end_idx = 0

        def _safe_return():
            if self._state == "RUNNING":
                self._stop_execution()
            on_return()

        self._view.btnReturn.clicked.connect(_safe_return)

        # Wrap widget_3 in a container so LivePlot can place the multiplot alongside it
        plot_container = QFrame(parent=view.frame_10)
        plot_container.setSizePolicy(view.widget_3.sizePolicy())
        plot_container.setMinimumSize(view.widget_3.minimumSize())
        container_layout = QHBoxLayout(plot_container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        hl = view.frame_10.layout()
        idx = hl.indexOf(view.widget_3)
        hl.removeWidget(view.widget_3)
        container_layout.addWidget(view.widget_3)
        hl.insertWidget(idx, plot_container)

        self._live_plot = LivePlot(view.widget_3, plot_container)

        self._display_group = QButtonGroup()
        self._display_group.addButton(view.radioButton_3)  # All Sensors
        self._display_group.addButton(view.radioButton)  # Thrust
        self._display_group.addButton(view.radioButton_2)  # Torque
        self._display_group.addButton(view.radioButton_4)  # Power, Efficiency
        self._display_group.buttonClicked.connect(
            lambda btn: self._live_plot.set_mode(btn.text())
        )

        self._plot_timer = QTimer()
        self._plot_timer.timeout.connect(self._live_plot.update)
        self._plot_timer.start(16)  # ~60 Hz

        font = QFont("Courier New", 16)
        font.setWeight(QFont.Weight.Normal)
        self._view.programText.setFont(font)

        self._error_map = {}  # line_num -> error_msg
        self._highlighter = ProgramHighlighter(
            self._view.programText.document(), self._error_map
        )
        self._view.programText.textChanged.connect(self._update_program_info)

        self._view.codeValidLabel.setStyleSheet("color: lightgreen;")
        self._view.lineCounter.setText("Lines: 0")
        # self._view.errorText.setReadOnly(True)
        self._view.errorText.hide()

        # disable throttle slider here
        self._view.currentThrottleSlider.mousePressEvent = lambda ev: None
        self._view.currentThrottleSlider.mouseMoveEvent = lambda ev: None
        self._view.currentThrottleSlider.mouseReleaseEvent = lambda ev: None
        self._view.currentThrottleSlider.keyPressEvent = lambda ev: None
        self._view.currentThrottleSlider.wheelEvent = lambda e: None
        self._view.currentThrottleSlider.setValue(50)

        self._view.btnSave.clicked.connect(self._save)
        self._view.btnLoad.clicked.connect(self._load)
        self._view.btnRun.clicked.connect(self._on_run_stop)
        self._view.btnExport.clicked.connect(self._export)

        self._exec_timer = QTimer()
        self._exec_timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._exec_timer.timeout.connect(self._execution_tick)

        self.dataService.register_callback(self._update_metrics)

    def _update_program_info(self):
        text = self._view.programText.toPlainText()
        lines = text.strip().splitlines()
        self._view.lineCounter.setText(f"Lines: {len(lines)}")

        success, data = ProgramParser(text)
        self._error_map.clear()

        if success:
            self._view.codeValidLabel.setText("Valid Code")
            self._view.codeValidLabel.setStyleSheet("color: lightgreen;")
            self._view.errorText.hide()
        else:
            # data is a list of (line_num, error_msg) tuples
            for line_num, error_msg in data:
                self._error_map[line_num] = error_msg
            error_count = len(data)
            error_lines = ", ".join(str(line_num) for line_num, _ in data)
            self._view.codeValidLabel.setText(
                f"Invalid Code ({error_count} error{'s' if error_count != 1 else ''} on line{'s' if error_count != 1 else ''} {error_lines})"
            )
            self._view.codeValidLabel.setStyleSheet("color: #ff6b6b;")

            # Populate error text box with errors line by line
            error_text_content = "\n".join(
                f"Line {line_num}: {error_msg}" for line_num, error_msg in data
            )
            self._view.errorText.setPlainText(error_text_content)
            self._view.errorText.show()

        QTimer.singleShot(0, self._highlighter.rehighlight)

    def _save(self):
        path, _ = QFileDialog.getSaveFileName(
            None, "Save Program", "", "Thrust Program (*.tprog)"
        )
        if path:
            with open(path, "w") as f:
                f.write(self._view.programText.toPlainText())

    def _load(self):
        path, _ = QFileDialog.getOpenFileName(
            None, "Load Program", "", "Thrust Program (*.tprog)"
        )
        if path:
            with open(path, "r") as f:
                self._view.programText.setPlainText(f.read())

    def _on_run_stop(self):
        if self._state == "RUNNING":
            self._stop_execution()
            return

        success, data = ProgramParser(self._view.programText.toPlainText())
        if not success:
            QMessageBox.warning(
                None, "Invalid Program", "Fix all errors before running."
            )
            return

        self._instructions = data
        self._state = "RUNNING"
        self._current_idx = 0
        self._instruction_start_ms = time.monotonic() * 1000
        self._ramp_start_throttle = self.thrustService.get_throttle()

        self._run_start_idx = len(self.dataService.data["timestamps"])
        self._view.programText.setReadOnly(True)
        self._view.btnRun.setText("Stop")
        self._view.btnSave.setEnabled(False)
        self._view.btnLoad.setEnabled(False)
        self._view.btnExport.setEnabled(False)
        self._exec_timer.start(8)

    def _stop_execution(self, complete=False):
        self._exec_timer.stop()
        self._state = "IDLE"
        self.thrustService.set_throttle(0)
        self._view.currentThrottleSlider.setValue(0)
        self._view.programText.setReadOnly(False)
        self._view.btnRun.setText("Run Program")
        self._view.btnSave.setEnabled(True)
        self._view.btnLoad.setEnabled(True)

        if complete:
            self._run_end_idx = len(self.dataService.data["timestamps"])
            if self._run_end_idx > self._run_start_idx:
                self._view.btnExport.setEnabled(True)

    def _execution_tick(self):
        if self._current_idx >= len(self._instructions):
            self._stop_execution(complete=True)
            return

        inst = self._instructions[self._current_idx]
        elapsed_ms = time.monotonic() * 1000 - self._instruction_start_ms

        if inst["instruction"] == "throttle":
            self.thrustService.set_throttle(inst["command"])
            self._view.currentThrottleSlider.setValue(inst["command"])
            self._advance()

        elif inst["instruction"] == "delay":
            if elapsed_ms >= inst["delayMs"]:
                self._advance()

        elif inst["instruction"] == "ramp":
            progress = min(elapsed_ms / inst["durationMs"], 1.0)
            throttle = int(
                self._ramp_start_throttle
                + progress * (inst["targetThrottle"] - self._ramp_start_throttle)
            )
            self.thrustService.set_throttle(throttle)
            self._view.currentThrottleSlider.setValue(throttle)
            if progress >= 1.0:
                self._advance()

    def _advance(self):
        self._current_idx += 1
        self._instruction_start_ms = time.monotonic() * 1000
        self._ramp_start_throttle = self.thrustService.get_throttle()

    def _update_metrics(self):
        d = self.dataService.data
        if d["timestamps"].size == 0:
            return

        thrust_cal = self.dataService.calibrationPoints["thrust"]
        if thrust_cal["sensitivity"] is None or thrust_cal["zero"] is None:
            self._view.lblThrust.setText("Uncalibrated")
        else:
            thrust_g = self.dataService.get_calibrated_value("thrust")
            if thrust_g is not None:
                self._view.lblThrust.setText(f"{thrust_g:.1f} gf")

        self._view.lblVoltage.setText(f"{d['voltage'][-1] / 1000.0:.3f} V")
        self._view.lblCurrent.setText(f"{d['current'][-1]:.3f} A")
        power_w = d["power"][-1]
        self._view.lblPower.setText(f"{power_w:.3f} W")
        thrust_cal = self.dataService.calibrationPoints["thrust"]
        if (
            thrust_cal["sensitivity"] is not None
            and thrust_cal["zero"] is not None
            and power_w > 0
        ):
            thrust_g = self.dataService.get_calibrated_value("thrust")
            if thrust_g is not None:
                self._view.lblEfficiency.setText(f"{thrust_g / power_w:.2f} g/W")
        else:
            self._view.lblEfficiency.setText("Uncalibrated")

        torque_nm = d["torque"][-1] if d["torque"].size > 0 else float("nan")
        self._view.lblTorque.setText(
            f"{torque_nm * 100:.2f} N-cm"
            if not math.isnan(torque_nm)
            else "Uncalibrated"
        )

        self._view.lblThrustCell.setText(str(int(d["thrust"][-1])))
        self._view.lblTorqueCellA.setText(str(int(d["torqueA"][-1])))
        self._view.lblTorqueCellB.setText(str(int(d["torqueB"][-1])))

    def _export(self):
        self.dataService.export_to_csv(self._run_start_idx, self._run_end_idx)
