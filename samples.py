"""Ready-made sketches for the three demo scenarios. Used in mock mode (no AI key) and as a fallback for tests."""

IRRIGATION = {
    "title": "Smart Irrigation",
    "explanation": "Sensor 1 reads a soil moisture module and relay 1 switches the water pump. The pump turns on when the soil is dry and off when it is wet enough. I assumed a common analog module where a higher voltage means drier soil.",
    "wiring": [
        {"port": "Sensor 1", "connect": "Soil moisture module: signal to the SIG terminal, plus its +5V and GND"},
        {"port": "Relay 1", "connect": "Water pump supply through the COM and NO terminals"},
    ],
    "sketch": '''#include "univox.h"
// Smart irrigation: sensor 1 = soil moisture, relay 1 = pump
const uint8_t SOIL_CH = 1;          // sensor input used
const uint8_t PUMP_RELAY = 1;       // relay used
const int DRY_ABOVE = 600;          // higher reading = drier soil: pump ON above this
const int WET_BELOW = 450;          // pump OFF below this (gap prevents chattering)
const unsigned long MAX_RUN_MS = 60000UL;   // safety: pump never runs longer than 60 s at a time
const unsigned long REST_MS = 30000UL;      // pause after a safety stop

unsigned long pumpStart = 0;
unsigned long restUntil = 0;

void setup() {
  univoxBegin();
  lcdPrint(0, "Smart Irrigation");
}

void loop() {
  int soil = sensorRaw(SOIL_CH);
  unsigned long now = millis();
  bool on = relayIsOn(PUMP_RELAY);
  if (!on && soil > DRY_ABOVE && (long)(now - restUntil) >= 0) {
    relay(PUMP_RELAY, true);
    pumpStart = now;
  } else if (on && (soil < WET_BELOW || now - pumpStart > MAX_RUN_MS)) {
    relay(PUMP_RELAY, false);
    if (now - pumpStart > MAX_RUN_MS) restUntil = now + REST_MS;
  }
  lcdPrintValue(1, relayIsOn(PUMP_RELAY) ? "ON soil" : "OFF soil", soil);
  delay(200);
}
''',
}

LIGHT = {
    "title": "Auto Room Light",
    "explanation": "Sensor 1 reads a light-dependent resistor (LDR) divider and relay 1 switches the room light. The light turns on in the dark between 6 PM and 6 AM only, using the real time clock. I assumed a higher voltage means brighter light.",
    "wiring": [
        {"port": "Sensor 1", "connect": "LDR divider output (LDR and a 10k resistor), plus +5V and GND"},
        {"port": "Relay 1", "connect": "Room light through the COM and NO terminals"},
    ],
    "sketch": '''#include "univox.h"
// Auto room light: sensor 1 = LDR, relay 1 = light, only active in the evening/night window
const uint8_t LDR_CH = 1;           // sensor input used
const uint8_t LIGHT_RELAY = 1;      // relay used
const int DARK_BELOW = 300;         // light ON when reading is below this
const int BRIGHT_ABOVE = 450;       // light OFF when reading is above this
const int NIGHT_START = 18 * 60;    // 18:00 in minutes
const int NIGHT_END = 6 * 60;       // 06:00 in minutes

bool isNight(int minutes) {
  return minutes >= NIGHT_START || minutes < NIGHT_END;
}

void setup() {
  univoxBegin();
  lcdPrint(0, "Auto Room Light");
}

void loop() {
  int ldr = sensorRaw(LDR_CH);
  int minutes = rtcMinutesOfDay();
  bool night = isNight(minutes);
  bool on = relayIsOn(LIGHT_RELAY);
  if (!on && night && ldr < DARK_BELOW) {
    relay(LIGHT_RELAY, true);
  } else if (on && (!night || ldr > BRIGHT_ABOVE)) {
    relay(LIGHT_RELAY, false);
  }
  char line[17];
  snprintf(line, sizeof(line), "%02d:%02d L%d %s", minutes / 60, minutes % 60, ldr / 10, relayIsOn(LIGHT_RELAY) ? "ON" : "OFF");
  lcdPrint(1, line);
  delay(200);
}
''',
}

FAN = {
    "title": "Overheat Protection Fan",
    "explanation": "Sensor 1 reads an LM35 temperature sensor and relay 1 switches a cooling fan. The fan turns on above 40 degrees C and off below 35 degrees C. I assumed the LM35 gives 10 millivolts per degree C.",
    "wiring": [
        {"port": "Sensor 1", "connect": "LM35 middle pin (output); its other pins to +5V and GND"},
        {"port": "Relay 1", "connect": "Fan supply through the COM and NO terminals"},
    ],
    "sketch": '''#include "univox.h"
// Overheat protection: sensor 1 = LM35 (10 mV per degree C), relay 1 = fan
const uint8_t TEMP_CH = 1;          // sensor input used
const uint8_t FAN_RELAY = 1;        // relay used
const int FAN_ON_C = 40;            // fan ON above this temperature (degrees C)
const int FAN_OFF_C = 35;           // fan OFF below this temperature (degrees C)

void setup() {
  univoxBegin();
  lcdPrint(0, "Overheat Fan");
}

void loop() {
  int tempC = sensorMilliVolts(TEMP_CH) / 10;   // LM35: 10 mV per degree C
  bool on = relayIsOn(FAN_RELAY);
  if (!on && tempC >= FAN_ON_C) {
    relay(FAN_RELAY, true);
  } else if (on && tempC <= FAN_OFF_C) {
    relay(FAN_RELAY, false);
  }
  lcdPrintValue(1, relayIsOn(FAN_RELAY) ? "Fan ON  C" : "Fan OFF C", tempC);
  delay(200);
}
''',
}


def pick_sample(text: str) -> dict:
    t = (text or "").lower()
    if any(w in t for w in ("fan", "temperature", "heat", "hot", "cool")):
        return FAN
    if any(w in t for w in ("light", "lamp", "dark", "night", "bulb", "ldr")):
        return LIGHT
    return IRRIGATION
