import sys
import signal
from PyQt6 import QtGui, QtWidgets
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer

from views.ui_StartSplash import Ui_Form as StartSplashView
from views.ui_ManualControl import Ui_Form as ManualControlView
from views.ui_CalibrationPage import Ui_Form as CalibrationView
from views.ui_ProgramControl import Ui_Form as AutomatedProgramView
from controllers.start_splash_controller import StartSplashController
from controllers.manual_control_controller import ManualControlController
from controllers.calibration_controller import CalibrationController
from controllers.automated_program_controller import AutomatedProgramController

from services.serial_service import SerialService

import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def main():
    app = QApplication(sys.argv)
    app.setWindowIcon(QtGui.QIcon(os.path.join(BASE_DIR, "assets", "icon.png")))

    splash_widget = QtWidgets.QWidget()
    splash_view = StartSplashView()
    splash_view.setupUi(splash_widget)
    splash_widget.setWindowTitle("Thrust Test-Bench - Start Splash")

    manual_widget = QtWidgets.QWidget()
    manual_control_view = ManualControlView()
    manual_control_view.setupUi(manual_widget)
    manual_widget.setWindowTitle("Thrust Test-Bench - Manual Control")

    calibration_widget = QtWidgets.QWidget()
    calibration_view = CalibrationView()
    calibration_view.setupUi(calibration_widget)
    calibration_widget.setWindowTitle("Thrust Test-Bench - Sensor Calibration")

    automated_program_widget = QtWidgets.QWidget()
    automated_program_view = AutomatedProgramView()
    automated_program_view.setupUi(automated_program_widget)
    automated_program_widget.setWindowTitle("Thrust Test-Bench - Automated Program")

    def show_manual():
        splash_widget.hide()
        manual_widget.show()

    def show_splash():
        manual_widget.hide()
        calibration_widget.hide()
        automated_program_widget.hide()
        splash_widget.show()

    def show_calibration():
        splash_widget.hide()
        calibration_widget.show()

    def show_automated_program():
        splash_widget.hide()
        automated_program_widget.show()

    controllers = [
        StartSplashController(
            splash_view,
            on_manual_test=show_manual,
            on_run_test=show_automated_program,
            on_sensor_calibration=show_calibration,
            on_quit=app.quit,
        ),
        ManualControlController(
            manual_control_view,
            on_return=show_splash,
        ),
        CalibrationController(
            calibration_view,
            on_return=show_splash,
        ),
        AutomatedProgramController(
            automated_program_view,
            on_return=show_splash,
        ),
    ]
    print(f"Started program with {len(controllers)} controllers")

    # serial port handling
    serialService = SerialService()
    serialTimer = QTimer()
    serialTimer.start(10)
    serialTimer.timeout.connect(serialService.spin)

    # this allows the app to quit on Ctrl+C in the terminal
    signal.signal(signal.SIGINT, lambda *_: app.quit())
    timer = QTimer()
    timer.start(100)
    timer.timeout.connect(lambda: None)

    # get baud rate and port, then start!
    serialService.getPortAndBaudRateFromUser(
        on_success=splash_widget.show,
        on_quit=app.quit,
    )

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
