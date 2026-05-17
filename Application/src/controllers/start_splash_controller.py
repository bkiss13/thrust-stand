class StartSplashController:
    def __init__(
        self, view, on_manual_test, on_run_test, on_sensor_calibration, on_quit
    ):
        self._view = view
        self._view.btn_manualTest.clicked.connect(on_manual_test)
        self._view.btn_runTestProgram.clicked.connect(on_run_test)
        self._view.btn_sensorCalibration.clicked.connect(on_sensor_calibration)
        self._view.btn_Quit.clicked.connect(on_quit)
