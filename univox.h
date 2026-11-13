// univox.h - helper library for the AI Command Based Switching Automation Device
// Hardware: Arduino UNO R3 (ATmega328P). Every generated sketch includes this file.
// It hides the pin map, the I2C LCD module and the DS1307 clock so the AI only
// has to write the logic.
#pragma once
#include <Arduino.h>
#include <Wire.h>
#include <stdio.h>

// ------------------------------------------------------------------ pin map
#define UV_RELAYS 5
#define UV_SENSORS 5
static const uint8_t UV_RELAY_PIN[UV_RELAYS] = {5, 6, 7, 8, 9};     // ULN2803A IN1..IN5 (HIGH = relay on)
static const uint8_t UV_SENSOR_PIN[UV_SENSORS] = {A0, A1, A2, A3, 4}; // CH1..CH4 analog+digital, CH5 digital only
#define UV_BTN_MODE 2   // Mode button  (INT0)
#define UV_BTN_TEST 3   // Test button  (INT1)

// ------------------------------------------------------------------ relays
// relay(1..5, true/false). Relay numbers are 1 to 5.
static void relay(uint8_t ch, bool on) {
  if (ch < 1 || ch > UV_RELAYS) return;
  digitalWrite(UV_RELAY_PIN[ch - 1], on ? HIGH : LOW);
}
static bool relayIsOn(uint8_t ch) {
  if (ch < 1 || ch > UV_RELAYS) return false;
  return digitalRead(UV_RELAY_PIN[ch - 1]) == HIGH;
}

// ------------------------------------------------------------------ sensors
// sensorRaw(1..5): 0..1023 for CH1-CH4 (10-bit ADC, 0-5 V). CH5 is digital only: returns 0 or 1023.
static int sensorRaw(uint8_t ch) {
  if (ch < 1 || ch > UV_SENSORS) return 0;
  if (ch == 5) return digitalRead(UV_SENSOR_PIN[4]) ? 1023 : 0;
  return analogRead(UV_SENSOR_PIN[ch - 1]);
}
// sensorMilliVolts(1..5): input voltage in millivolts, 0..5000.
static int sensorMilliVolts(uint8_t ch) {
  return (int)((long)sensorRaw(ch) * 5000L / 1023L);
}
// sensorHigh(1..5): true when the input is above about 2.5 V (digital view of any channel).
static bool sensorHigh(uint8_t ch) {
  return sensorRaw(ch) > 511;
}

// ------------------------------------------------------------------ buttons
// Active-low buttons (button pulls the pin to GND). Returns true while pressed.
static bool buttonMode() { return digitalRead(UV_BTN_MODE) == LOW; }
static bool buttonTest() { return digitalRead(UV_BTN_TEST) == LOW; }

// ------------------------------------------------------------------ I2C LCD (PCF8574 backpack)
static uint8_t uvLcdAddr = 0;
static const uint8_t UV_LCD_BL = 0x08;
static void uvLcdNibble(uint8_t nib, uint8_t rs) {
  uint8_t d = (uint8_t)((nib << 4) | UV_LCD_BL | (rs ? 1 : 0));
  Wire.beginTransmission(uvLcdAddr); Wire.write((uint8_t)(d | 0x04)); Wire.endTransmission();
  delayMicroseconds(2);
  Wire.beginTransmission(uvLcdAddr); Wire.write((uint8_t)(d & ~0x04)); Wire.endTransmission();
  delayMicroseconds(60);
}
static void uvLcdSend(uint8_t v, uint8_t rs) { uvLcdNibble(v >> 4, rs); uvLcdNibble(v & 0x0F, rs); }
static bool uvLcdFind() {
  const uint8_t tryAddr[2] = {0x27, 0x3F};
  for (uint8_t i = 0; i < 2; i++) {
    Wire.beginTransmission(tryAddr[i]);
    if (Wire.endTransmission() == 0) { uvLcdAddr = tryAddr[i]; return true; }
  }
  return false;
}
static void uvLcdInit() {
  if (!uvLcdFind()) return;
  delay(50);
  uvLcdNibble(0x03, 0); delay(5);
  uvLcdNibble(0x03, 0); delay(5);
  uvLcdNibble(0x03, 0); delayMicroseconds(200);
  uvLcdNibble(0x02, 0);
  uvLcdSend(0x28, 0);   // 4-bit, 2 lines
  uvLcdSend(0x0C, 0);   // display on, no cursor
  uvLcdSend(0x06, 0);   // entry mode
  uvLcdSend(0x01, 0); delay(3);
}
// lcdClear()
static void lcdClear() { if (!uvLcdAddr) return; uvLcdSend(0x01, 0); delay(3); }
// lcdPrint(row 0 or 1, "text") - the row is cleared first, text is cut at 16 characters.
static void lcdPrint(uint8_t row, const char *text) {
  if (!uvLcdAddr) return;
  uvLcdSend((uint8_t)(0x80 | (row ? 0x40 : 0x00)), 0);
  uint8_t n = 0;
  while (text[n] && n < 16) { uvLcdSend((uint8_t)text[n], 1); n++; }
  while (n < 16) { uvLcdSend(' ', 1); n++; }
}
// lcdPrintValue(row, "Soil", 512) shows "Soil: 512"
static void lcdPrintValue(uint8_t row, const char *label, long value) {
  char buf[17];
  snprintf(buf, sizeof(buf), "%s: %ld", label, value);
  lcdPrint(row, buf);
}

// ------------------------------------------------------------------ DS1307 real time clock (address 0x68)
#define UV_RTC_ADDR 0x68
static uint8_t uvBcd2Dec(uint8_t v) { return (uint8_t)(v - 6 * (v >> 4)); }
static uint8_t uvDec2Bcd(uint8_t v) { return (uint8_t)(v + 6 * (v / 10)); }
static bool uvRtcRead(uint8_t *h, uint8_t *m, uint8_t *s) {
  Wire.beginTransmission(UV_RTC_ADDR); Wire.write((uint8_t)0);
  if (Wire.endTransmission() != 0) return false;
  if (Wire.requestFrom((uint8_t)UV_RTC_ADDR, (uint8_t)3) != 3) return false;
  *s = uvBcd2Dec(Wire.read() & 0x7F);
  *m = uvBcd2Dec(Wire.read() & 0x7F);
  *h = uvBcd2Dec(Wire.read() & 0x3F);
  return true;
}
// rtcSet(hour, minute, second) sets the clock and starts it.
static void rtcSet(uint8_t h, uint8_t m, uint8_t s) {
  Wire.beginTransmission(UV_RTC_ADDR); Wire.write((uint8_t)0);
  Wire.write(uvDec2Bcd(s)); Wire.write(uvDec2Bcd(m)); Wire.write(uvDec2Bcd(h));
  Wire.endTransmission();
}
// rtcHour() 0-23, rtcMinute() 0-59, rtcSecond() 0-59 (all return 0 if the clock does not answer)
static uint8_t rtcHour()   { uint8_t h, m, s; return uvRtcRead(&h, &m, &s) ? h : 0; }
static uint8_t rtcMinute() { uint8_t h, m, s; return uvRtcRead(&h, &m, &s) ? m : 0; }
static uint8_t rtcSecond() { uint8_t h, m, s; return uvRtcRead(&h, &m, &s) ? s : 0; }
// rtcMinutesOfDay() 0..1439, handy for time-window checks
static int rtcMinutesOfDay() { uint8_t h, m, s; return uvRtcRead(&h, &m, &s) ? (int)h * 60 + m : 0; }
static void uvRtcStart() {
  Wire.beginTransmission(UV_RTC_ADDR); Wire.write((uint8_t)0);
  if (Wire.endTransmission() != 0) return;                 // no clock chip found
  if (Wire.requestFrom((uint8_t)UV_RTC_ADDR, (uint8_t)1) != 1) return;
  uint8_t sec = Wire.read();
  if (sec & 0x80) {                                         // clock was halted (battery new or removed)
    // set to the time this program was built, so the clock starts running
    const char *t = __TIME__;                               // "HH:MM:SS"
    uint8_t hh = (uint8_t)((t[0] - '0') * 10 + (t[1] - '0'));
    uint8_t mm = (uint8_t)((t[3] - '0') * 10 + (t[4] - '0'));
    uint8_t ss = (uint8_t)((t[6] - '0') * 10 + (t[7] - '0'));
    rtcSet(hh, mm, ss);
  }
}

// ------------------------------------------------------------------ start-up
// Call univoxBegin() first thing in setup(). Relays start OFF.
static void univoxBegin() {
  for (uint8_t i = 0; i < UV_RELAYS; i++) { pinMode(UV_RELAY_PIN[i], OUTPUT); digitalWrite(UV_RELAY_PIN[i], LOW); }
  pinMode(UV_SENSOR_PIN[4], INPUT);
  pinMode(UV_BTN_MODE, INPUT_PULLUP);
  pinMode(UV_BTN_TEST, INPUT_PULLUP);
  Wire.begin();
  uvRtcStart();
  uvLcdInit();
}
