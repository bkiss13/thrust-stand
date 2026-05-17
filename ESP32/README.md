# Microcontroller Code
## Thrust Bench

The ESP32 software reads data from the HX711 and INA260 modules. This *raw* data is then written to the serial port, which the application software reads.

All relevant ESP32 code is in the ThrustStand/main.cpp file.

To use, compile and upload this program to a microcontroller. Ensure that the wiring matches the code. To use the code without changes, wire according to the diagram given in the associated paper.
