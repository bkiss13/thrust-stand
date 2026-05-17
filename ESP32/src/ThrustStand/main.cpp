#include <Adafruit_INA260.h>
#include <Arduino.h>
#include <ESP32Servo.h>
#include <HX711.h>

// Important: the HX711 variables loadcell1, loadcell2, and loadcell3
// must be declared AFTER the Servo motor variable. There seems to be
// some sort of conflict between the HX711 and ES32Servo libraries
// which causes the code to stall otherwise.

Servo motor;
int currentPercent = 0;

HX711 loadcell1;
HX711 loadcell2;
HX711 loadcell3;

Adafruit_INA260 ina260 = Adafruit_INA260();

#define LOADCELL_SCK_PIN D7
#define LOADCELL1_DOUT_PIN D8
#define LOADCELL2_DOUT_PIN D9
#define LOADCELL3_DOUT_PIN D10

#define ESC_SIGNAL_PIN D1

long loadcell1_value;
long loadcell2_value;
long loadcell3_value;

bool loadcell1_ready = false;
bool loadcell2_ready = false;
bool loadcell3_ready = false;

void setMotorPercentage(int percent) {
  currentPercent = percent;
  int us = map(percent, 0, 100, 1000, 2000);
  motor.writeMicroseconds(us);
}

void setup() {
  Serial.begin(115200);

  motor.attach(ESC_SIGNAL_PIN, 1000, 2000);
  setMotorPercentage(0);

  loadcell1.begin(LOADCELL1_DOUT_PIN, LOADCELL_SCK_PIN);
  loadcell2.begin(LOADCELL2_DOUT_PIN, LOADCELL_SCK_PIN);
  loadcell3.begin(LOADCELL3_DOUT_PIN, LOADCELL_SCK_PIN);

  if (!ina260.begin()) {
    Serial.println("Couldn't find INA260 chip");
    while (1)
      ;
  }
}

void send_long_over_serial(long value) {
  // cast for platfrom independance
  uint32_t uvalue = (uint32_t)value;
  Serial.write((uvalue >> 24) & 0xFF);
  Serial.write((uvalue >> 16) & 0xFF);
  Serial.write((uvalue >> 8) & 0xFF);
  Serial.write(uvalue & 0xFF);
}

void send_float_over_serial(float value) {
  uint32_t uvalue;
  memcpy(&uvalue, &value, sizeof(uvalue));
  Serial.write((uvalue >> 24) & 0xFF);
  Serial.write((uvalue >> 16) & 0xFF);
  Serial.write((uvalue >> 8) & 0xFF);
  Serial.write(uvalue & 0xFF);
}

void loop() {
  if (loadcell1.is_ready()) {
    loadcell1_value = loadcell1.read();
    loadcell1_ready = true;
  }
  if (loadcell2.is_ready()) {
    loadcell2_value = loadcell2.read();
    loadcell2_ready = true;
  }
  if (loadcell3.is_ready()) {
    loadcell3_value = loadcell3.read();
    loadcell3_ready = true;
  }

  if (Serial.available()) {
    String input = Serial.readStringUntil('\n');
    input.trim();
    int val = input.toInt();
    if (val < 0)
      val = 0;
    if (val > 100)
      val = 100;
    setMotorPercentage(val);
  }

  if (loadcell1_ready && loadcell2_ready && loadcell3_ready) {
    send_long_over_serial(loadcell1_value);
    send_long_over_serial(loadcell2_value);
    send_long_over_serial(loadcell3_value);
    send_float_over_serial(ina260.readCurrent());
    send_float_over_serial(ina260.readBusVoltage());
    Serial.write('\n');

    loadcell1_ready = false;
    loadcell2_ready = false;
    loadcell3_ready = false;
  }
}
