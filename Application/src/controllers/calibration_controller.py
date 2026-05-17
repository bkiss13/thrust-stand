import numpy as np
from typing import Callable, Optional

from PyQt6.QtWidgets import QFileDialog, QInputDialog, QMessageBox, QWidget
from services.data_service import DataService
from views.ui_CalibrationPage import Ui_Form as CalibrationView
from views.ui_ThrustCalibrationPane import Ui_Form as ThrustCalibrationPaneView
from views.ui_TorqueSensitivityPane import Ui_Form as TorqueSensitivityPaneView
from views.ui_TorqueMassPane import Ui_Form as TorqueMassPaneView
from views.ui_LoadOrSavePane import Ui_Form as LoadOrSavePaneView
import pyqtgraph as pg


# TODO: put this in a config file / settings menu
ARM_LENGTH = 62.6 * 1e-3  # meters, distance from center of torque to calibration mass
GRAVITY = 9.81  # m/s^2, standard gravity for torque mass calculations


class CalibrationController:
    def __init__(self, view: CalibrationView, on_return: Callable):
        self.dataService = DataService()
        self.dataService.register_callback(self._on_new_data)

        self._view: CalibrationView = view
        self._view.sensorSelectGroup.buttonClicked.connect(self._on_sensor_select)

        self.plot = self._view.plotWidget
        self.plot.setLabel("left", "Sensor Value", units="g", **{"font-size": "18pt"})
        self.plot.setLabel("bottom", "Time", units="?s?", **{"font-size": "18pt"})
        self.curve = self.plot.plot(pen=pg.mkPen(color="b", width=2))

        self._thrust_pane_widget = QWidget()
        self._thrust_pane = ThrustCalibrationPaneView()
        self._thrust_pane.setupUi(self._thrust_pane_widget)
        self._view.horizontalLayout_2.addWidget(self._thrust_pane_widget)

        self._thrust_pane.btnReturn.clicked.connect(on_return)
        self._thrust_pane.btnProcedure.clicked.connect(
            self._on_calibrate_thrust_sensitivity
        )
        self._thrust_pane.btnSetZero.clicked.connect(self._on_zero_thrust)

        self._torque_sensitivity_pane_widget = QWidget()
        self._torque_sensitivity_pane = TorqueSensitivityPaneView()
        self._torque_sensitivity_pane.setupUi(self._torque_sensitivity_pane_widget)
        self._view.horizontalLayout_2.addWidget(self._torque_sensitivity_pane_widget)

        self._torque_sensitivity_pane.btnReturn.clicked.connect(on_return)
        self._torque_sensitivity_pane.btnProcedure.clicked.connect(
            self._on_calibrate_torque_sensitivity
        )
        self._torque_sensitivity_pane_widget.setVisible(False)

        self._torque_mass_pane_widget = QWidget()
        self._torque_mass_pane = TorqueMassPaneView()
        self._torque_mass_pane.setupUi(self._torque_mass_pane_widget)
        self._view.horizontalLayout_2.addWidget(self._torque_mass_pane_widget)

        self._torque_mass_pane.btnReturn.clicked.connect(on_return)
        self._torque_mass_pane.btnZeroTorque.clicked.connect(self._on_zero_torque)
        self._torque_mass_pane.btnProcedure.clicked.connect(
            self._on_calibrate_torque_mass
        )
        self._torque_mass_pane_widget.setVisible(False)

        self._load_save_pane_widget = QWidget()
        self._load_save_pane = LoadOrSavePaneView()
        self._load_save_pane.setupUi(self._load_save_pane_widget)
        self._view.horizontalLayout_2.addWidget(self._load_save_pane_widget)

        self._load_save_pane.btnReturn.clicked.connect(on_return)
        self._load_save_pane.btnSave.clicked.connect(self._save_calibration)
        self._load_save_pane.btnLoad.clicked.connect(self._load_calibration)
        self._load_save_pane.btnViewData.clicked.connect(self._on_view_data)

        # Load/Save pane shown by default
        self._load_save_pane_widget.setVisible(True)
        self._thrust_pane_widget.setVisible(False)
        self._display = "thrust"

    def _on_sensor_select(self, button):
        label = button.text()
        self._thrust_pane_widget.setVisible(label == "Thrust Sensor")
        self._torque_sensitivity_pane_widget.setVisible(label == "Torque Sensitivity")
        self._torque_mass_pane_widget.setVisible(label == "Torque Mass")
        self._load_save_pane_widget.setVisible(label == "Load or Save Calibrations")
        if label in ("Torque Sensitivity", "Torque Mass"):
            self._display = "torque"
            self.plot.setLabel("left", "Torque", units="N·cm", **{"font-size": "18pt"})
        else:
            self._display = "thrust"
            self.plot.setLabel(
                "left", "Sensor Value", units="g", **{"font-size": "18pt"}
            )

    def _on_new_data(self):
        if self._display == "torque":
            torque_data = self.dataService.data["torque"]
            if torque_data.size > 0:
                latest_ncm = float(torque_data[-1]) * 100
                self._view.currentValue.setText(
                    f"{latest_ncm:.2f} N-cm" if not np.isnan(latest_ncm) else "??"
                )
            self.curve.setData(
                self.dataService.data["time"], self.dataService.data["torque"] * 100
            )
        else:
            value = self.dataService.get_calibrated_value("thrust")
            if value is not None:
                self._view.currentValue.setText(f"{value:.0f} g")
            self.curve.setData(
                self.dataService.data["time"], self.dataService.data["thrust"]
            )

    def _mean_recent(self, sensor: str, n: int = 10) -> Optional[float]:
        data = self.dataService.data[sensor]
        if data.size == 0:
            return None
        return float(np.mean(data[-n:] if data.size >= n else data))

    def _on_calibrate_thrust_sensitivity(self):
        # Step 1: record unloaded reading
        QMessageBox.information(
            None,
            "Calibrate Sensitivity (1/2)",
            "Remove all weight from the sensor, then press OK to record the unloaded reading.",
        )
        zero_reading = self._mean_recent("thrust")
        if zero_reading is None:
            QMessageBox.warning(
                None, "No Data", "No sensor data available. Connect the device first."
            )
            return

        # Step 2: place known weight, enter mass, record loaded reading
        mass, ok = QInputDialog.getDouble(
            None,
            "Calibrate Sensitivity (2/2)",
            "Place the known weight on the sensor.\nEnter its mass in grams, then press OK to record.",
            decimals=1,
            min=0.1,
        )
        if not ok:
            return

        known_reading = self._mean_recent("thrust")
        if known_reading is None or known_reading == zero_reading:
            QMessageBox.warning(
                None,
                "Calibration Failed",
                "Readings are identical - ensure the weight is on the sensor.",
            )
            return

        sensitivity = mass / (known_reading - zero_reading)
        self.dataService.set_sensitivity("thrust", sensitivity)
        QMessageBox.information(
            None,
            "Sensitivity Calibrated",
            f"Sensitivity set to {sensitivity:.6f} g/count.",
        )

    def _on_calibrate_torque_sensitivity(self):
        # Step 1: record zero point for both sensors
        QMessageBox.information(
            None,
            "Torque Sensitivity (1/4)",
            "Remove all weight from the fixture, then press OK to record the zero point.",
        )
        zero_A = self._mean_recent("torqueA")
        zero_B = self._mean_recent("torqueB")
        if zero_A is None or zero_B is None:
            QMessageBox.warning(
                None, "No Data", "No sensor data available. Connect the device first."
            )
            return

        # Step 2: first known weight
        mass1, ok = QInputDialog.getDouble(
            None,
            "Torque Sensitivity (2/4)",
            "Place the first known weight on the fixture.\nEnter its mass in grams, then press OK to record.",
            decimals=1,
            min=0.1,
        )
        if not ok:
            return
        reading_A1 = self._mean_recent("torqueA")
        reading_B1 = self._mean_recent("torqueB")
        if reading_A1 is None or reading_B1 is None:
            QMessageBox.warning(None, "No Data", "No sensor data available.")
            return
        if reading_A1 == zero_A or reading_B1 == zero_B:
            QMessageBox.warning(
                None,
                "Calibration Failed",
                "Readings are identical to zero - ensure the weight is on the fixture.",
            )
            return

        # Step 3: second known weight
        mass2, ok = QInputDialog.getDouble(
            None,
            "Torque Sensitivity (3/4)",
            "Place the second known weight on the fixture.\nEnter its mass in grams, then press OK to record.",
            decimals=1,
            min=0.1,
        )
        if not ok:
            return
        reading_A2 = self._mean_recent("torqueA")
        reading_B2 = self._mean_recent("torqueB")
        if reading_A2 is None or reading_B2 is None:
            QMessageBox.warning(None, "No Data", "No sensor data available.")
            return
        if reading_A2 == zero_A or reading_B2 == zero_B:
            QMessageBox.warning(
                None,
                "Calibration Failed",
                "Readings are identical to zero - ensure the weight is on the fixture.",
            )
            return

        # Step 4: average per-point sensitivities and save
        sensitivity_A = (
            mass1 / (reading_A1 - zero_A) + mass2 / (reading_A2 - zero_A)
        ) / 2.0
        sensitivity_B = (
            mass1 / (reading_B1 - zero_B) + mass2 / (reading_B2 - zero_B)
        ) / 2.0

        self.dataService.set_zero("torqueA", zero_A)
        self.dataService.set_zero("torqueB", zero_B)
        self.dataService.set_sensitivity("torqueA", sensitivity_A)
        self.dataService.set_sensitivity("torqueB", sensitivity_B)

        QMessageBox.information(
            None,
            "Torque Sensitivity Calibrated (4/4)",
            f"torqueA: zero={zero_A:.1f}, sensitivity={sensitivity_A:.6f} g/count\n"
            f"torqueB: zero={zero_B:.1f}, sensitivity={sensitivity_B:.6f} g/count",
        )

    def _on_calibrate_torque_mass(self):
        for s in ("torqueA", "torqueB"):
            cp = self.dataService.calibrationPoints[s]
            if cp["sensitivity"] is None or cp["zero"] is None:
                QMessageBox.warning(
                    None,
                    "Not Ready",
                    f"{s} must be calibrated first (run Torque Sensitivity).",
                )
                return

        QMessageBox.information(
            None,
            "Torque Mass (1/3)",
            "Attach the torque calibration arm without any weight, then press OK to record the zero point.",
        )
        forceZeroA = self.dataService.get_calibrated_value("torqueA")
        forceZeroB = self.dataService.get_calibrated_value("torqueB")
        if forceZeroA is None or forceZeroB is None:
            QMessageBox.warning(None, "No Data", "No sensor data available.")
            return

        mass1, ok = QInputDialog.getDouble(
            None,
            "Torque Mass (2/3)",
            "Place the first known weight on the calibration arm.\nEnter its mass in grams, then press OK to record.",
            decimals=1,
            min=0.1,
        )
        if not ok:
            return
        force1A = self.dataService.get_calibrated_value("torqueA")
        force1B = self.dataService.get_calibrated_value("torqueB")
        if force1A is None or force1B is None:
            QMessageBox.warning(None, "No Data", "No sensor data available.")
            return

        newtons1 = mass1 / 1000 * GRAVITY
        torque1 = ARM_LENGTH * newtons1

        zero_diff = forceZeroA - forceZeroB
        denom1 = (force1A - force1B) - zero_diff
        if abs(denom1) < 1e-9:
            QMessageBox.warning(
                None,
                "Calibration Error",
                "No torque detected for weight 1. Check load cell attachment.",
            )
            return
        sensitivity1 = torque1 / denom1

        mass2, ok = QInputDialog.getDouble(
            None,
            "Torque Mass (3/3)",
            "Place the second known weight on the calibration arm.\nEnter its mass in grams, then press OK to record.",
            decimals=1,
            min=0.1,
        )
        if not ok:
            return
        force2A = self.dataService.get_calibrated_value("torqueA")
        force2B = self.dataService.get_calibrated_value("torqueB")
        if force2A is None or force2B is None:
            QMessageBox.warning(None, "No Data", "No sensor data available.")
            return

        torque2 = ARM_LENGTH * (mass2 / 1000 * GRAVITY)
        denom2 = (force2A - force2B) - zero_diff
        if abs(denom2) < 1e-9:
            QMessageBox.warning(
                None,
                "Calibration Error",
                "No torque detected for weight 2. Check load cell attachment.",
            )
            return
        sensitivity2 = torque2 / denom2

        sensitivity = (sensitivity1 + sensitivity2) / 2.0
        self.dataService.set_zero("torque", zero_diff)
        self.dataService.set_sensitivity("torque", sensitivity)

        QMessageBox.information(
            None,
            "Torque Mass Calibrated",
            f"Sensitivity: {sensitivity:.6f} N·m/g\n"
            f"  point 1: {sensitivity1:.6f}  point 2: {sensitivity2:.6f}",
        )

    def _on_zero_thrust(self):
        zero = self._mean_recent("thrust")
        if zero is None:
            QMessageBox.warning(None, "No Data", "No sensor data available.")
            return
        self.dataService.set_zero("thrust", zero)
        QMessageBox.information(None, "Zero Set", "Zero point recorded.")

    def _on_zero_torque(self):
        torque_A = self.dataService.get_calibrated_value("torqueA")
        torque_B = self.dataService.get_calibrated_value("torqueB")
        if torque_A is None or torque_B is None:
            QMessageBox.warning(
                None,
                "No Data",
                "No sensor data available. Ensure torqueA/B are calibrated first.",
            )
            return
        self.dataService.set_zero("torque", torque_A - torque_B)
        QMessageBox.information(None, "Zero Set", "Torque zero point recorded.")

    def _on_view_data(self):
        points = self.dataService.calibrationPoints
        lines = []
        for sensor, cal in points.items():
            lines.append(
                f"{sensor}: zero={cal['zero']}, sensitivity={cal['sensitivity']}"
            )
        QMessageBox.information(None, "Calibration Data", "\n".join(lines))

    _SENSORS = ["thrust", "torqueA", "torqueB", "torque"]

    def _save_calibration(self):
        path, _ = QFileDialog.getSaveFileName(
            None, "Save Calibration", "", "Calibration File (*.tcalib)"
        )
        if not path:
            return
        with open(path, "w") as f:
            for sensor in self._SENSORS:
                cal = self.dataService.calibrationPoints[sensor]
                sensitivity = (
                    "" if cal["sensitivity"] is None else str(cal["sensitivity"])
                )
                zero = "" if cal["zero"] is None else str(cal["zero"])
                f.write(f"{sensor},{sensitivity},{zero}\n")

    def _load_calibration(self):
        path, _ = QFileDialog.getOpenFileName(
            None, "Load Calibration", "", "Calibration File (*.tcalib)"
        )
        if not path:
            return
        try:
            with open(path, "r") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    parts = line.split(",")
                    if len(parts) != 3:
                        continue
                    sensor, sensitivity, zero = parts
                    if sensor not in self.dataService.calibrationPoints:
                        continue
                    self.dataService.calibrationPoints[sensor]["sensitivity"] = (
                        float(sensitivity) if sensitivity else None
                    )
                    self.dataService.calibrationPoints[sensor]["zero"] = (
                        float(zero) if zero else None
                    )
        except (ValueError, IndexError, OSError) as e:
            QMessageBox.warning(
                None, "Load Failed", f"Could not read calibration file:\n{e}"
            )
            return
        self.dataService.notify_callbacks()
