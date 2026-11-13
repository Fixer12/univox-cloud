import re

# Things a generated sketch must never contain (see the rules in prompts.py)
FORBIDDEN = [
    (r"\bSerial\d?\b", "Serial is not allowed (pins D0/D1 are the Wi-Fi link)"),
    (r"\bWire\b", "Wire is not allowed (the helper handles the I2C bus)"),
    (r"\b(pinMode|digitalWrite|digitalRead|analogRead|analogWrite|attachInterrupt|tone|noTone|shiftOut|pulseIn)\s*\(",
     "Direct pin functions are not allowed, use the univox.h helpers"),
    (r"\bString\b", "The String class is not allowed (uses too much RAM)"),
    (r"\bA[0-7]\b", "Analog pin names are not allowed, use sensorRaw()"),
    (r"\bwdt_|\bavr/wdt|\bboot_|\bSPM|\basm\b|\b__asm__\b", "Low-level chip access is not allowed"),
    (r"\bEEPROM\b", "EEPROM is not allowed"),
]
ALLOWED_INCLUDES = {"univox.h", "Arduino.h"}


def check_sketch(sketch: str) -> list:
    problems = []
    if not sketch or len(sketch) < 40:
        return ["The sketch is empty"]
    if len(sketch) > 12000:
        problems.append("The sketch is too long (max 12000 characters)")
    code = re.sub(r"//.*", "", sketch)
    code = re.sub(r"/\*.*?\*/", "", code, flags=re.S)
    code_nostr = re.sub(r'"(\\.|[^"\\])*"', '""', code)
    for pattern, message in FORBIDDEN:
        if re.search(pattern, code_nostr):
            problems.append(message)
    for inc in re.findall(r'#\s*include\s*[<"]([^>"]+)[>"]', code):
        if inc not in ALLOWED_INCLUDES:
            problems.append(f"Only univox.h may be included, found {inc}")
    if '#include "univox.h"' not in code:
        problems.append('The first line must be #include "univox.h"')
    if not re.search(r"\bvoid\s+setup\s*\(", code) or not re.search(r"\bvoid\s+loop\s*\(", code):
        problems.append("setup() and loop() are both required")
    if "univoxBegin" not in code:
        problems.append("univoxBegin() must be called in setup()")
    for m in re.finditer(r"\bdelay\s*\(\s*(\d+)\s*\)", code):
        if int(m.group(1)) > 200:
            problems.append(f"delay({m.group(1)}) is too long, use millis() timing")
            break
    return problems
