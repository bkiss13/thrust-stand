from typing import Callable
from PyQt6 import QtWidgets
import serial
import struct
import sys

from serial.tools import list_ports

from services.data_service import DataService
from services.thrust_service import ThrustService
from utils.decorators import singleton
from views.ui_SerialSetup import Ui_Form as SerialSetupView


@singleton
class SerialService:
    def __init__(self):
        self.thrustService = ThrustService()

    def attempt_connection(self):
        try:
            self.ser = serial.Serial(self.port, self.baud_rate, timeout=1)
            print(f"Successfully connected to {self.port} at {self.baud_rate} baud.")
            self.setup_widget.destroy()
            self.on_success()
        except Exception as e:
            print(f"Failed to connect to {self.port} at {self.baud_rate} baud: {e}")
            QtWidgets.QMessageBox.critical(
                None, None, "Connection Error: Please try again, or check the output"
            )

    def getPortAndBaudRateFromUser(self, on_success: Callable, on_quit: Callable):
        self.dataService = DataService()

        self.ser = None
        self.setup_widget = QtWidgets.QWidget()
        setup_view = SerialSetupView()
        setup_view.setupUi(self.setup_widget)
        self.setup_widget.setWindowTitle("Thrust Test-Bench - Serial Setup")
        self.setup_widget.show()
        self.on_success = on_success

        usb_ports = [
            port.device
            for port in list_ports.comports()
            if "usb" in port.description.lower()
        ]
        non_usb_ports = [
            port.device
            for port in list_ports.comports()
            if "usb" not in port.description.lower()
        ]
        ports = usb_ports + non_usb_ports
        baud_rates = ["115200"]

        setup_view.serialPortSelect.addItems(ports)
        setup_view.baudRate.addItems(baud_rates)

        self.port = setup_view.serialPortSelect.currentText()
        self.baud_rate = int(setup_view.baudRate.currentText())

        setup_view.serialPortSelect.currentTextChanged.connect(
            lambda text: setattr(self, "port", text)
        )
        setup_view.baudRate.currentTextChanged.connect(
            lambda text: setattr(self, "baud_rate", int(text))
        )

        setup_view.btnQuit.clicked.connect(on_quit)
        setup_view.btnConnect.clicked.connect(self.attempt_connection)

    def read_frame(self) -> tuple[int, int, int, float, float]:
        if self.ser is None:
            raise Exception("Serial port not initialized")

        data = self.ser.read(20)
        _ = self.ser.read(1)  # consume null terminator
        lc1, lc2, lc3, current, voltage = struct.unpack(">iiiff", data)
        return lc1, lc2, lc3, current, voltage

    def spin(self):
        if self.ser is not None and self.ser.is_open:
            # Read incoming sensor data
            if self.ser.in_waiting >= 21:
                try:
                    lc1, lc2, lc3, current_ma, voltage_mv = self.read_frame()
                    self.dataService.add_data(lc3, lc1, lc2, current_ma, voltage_mv)
                except Exception as e:
                    print(f"Error reading from serial port: {e}")

            # Write current throttle output
            throttle_str = str(self.thrustService.get_throttle())

            try:
                self.ser.write(throttle_str.encode() + b"\n")
            except serial.SerialException as e:
                print(f"Serial write error: {e}")
                QtWidgets.QMessageBox.critical(
                    None, "Connection Lost", f"Serial port disconnected:\n{e}"
                )
