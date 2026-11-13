"""Compile an Arduino sketch for the Uno with plain avr-gcc and the Arduino core.

No arduino-cli is needed: the Docker image installs gcc-avr, avr-libc and
arduino-core-avr from Debian. The Arduino core is compiled once and cached.
"""
import glob
import os
import re
import subprocess
import tempfile
import threading
import uuid
from dataclasses import dataclass, field

CORE_DIR = os.getenv("ARDUINO_AVR_DIR", "/usr/share/arduino/hardware/arduino/avr")
HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.getenv("UNIVOX_BUILD_CACHE", os.path.join(tempfile.gettempdir(), "univox_build"))
MCU = "atmega328p"
FLASH_MAX = 32256   # Uno with Optiboot
RAM_MAX = 2048

COMMON = [
    f"-mmcu={MCU}", "-DF_CPU=16000000L", "-DARDUINO=10806", "-DARDUINO_AVR_UNO",
    "-DARDUINO_ARCH_AVR", "-Os", "-w", "-ffunction-sections", "-fdata-sections",
    f"-I{CORE_DIR}/cores/arduino", f"-I{CORE_DIR}/variants/standard",
    f"-I{CORE_DIR}/libraries/Wire/src", f"-I{CORE_DIR}/libraries/Wire/src/utility",
]
CXXFLAGS = ["-std=gnu++11", "-fno-exceptions", "-fno-threadsafe-statics", "-fpermissive"]
CFLAGS = ["-std=gnu11"]

_core_lock = threading.Lock()
_compile_lock = threading.Semaphore(1)   # free hosting is small: one compile at a time


@dataclass
class CompileResult:
    ok: bool
    log: str = ""
    flash_bytes: int = 0
    ram_bytes: int = 0
    hex_text: str = ""
    flash_pct: float = 0.0
    ram_pct: float = 0.0
    problems: list = field(default_factory=list)


def toolchain_ready() -> bool:
    return (subprocess.run(["which", "avr-g++"], capture_output=True).returncode == 0
            and os.path.isdir(CORE_DIR))


def _run(cmd, cwd=None, timeout=90):
    return subprocess.run(cmd, capture_output=True, text=True, cwd=cwd, timeout=timeout)


def _build_core() -> str:
    """Build libcore.a once; return its path."""
    os.makedirs(CACHE, exist_ok=True)
    lib = os.path.join(CACHE, "libcore.a")
    if os.path.exists(lib):
        return lib
    with _core_lock:
        if os.path.exists(lib):
            return lib
        objdir = os.path.join(CACHE, "coreobj")
        os.makedirs(objdir, exist_ok=True)
        srcs = []
        srcs += glob.glob(f"{CORE_DIR}/cores/arduino/*.c")
        srcs += glob.glob(f"{CORE_DIR}/cores/arduino/*.cpp")
        srcs += glob.glob(f"{CORE_DIR}/cores/arduino/*.S")
        srcs += [f"{CORE_DIR}/libraries/Wire/src/Wire.cpp",
                 f"{CORE_DIR}/libraries/Wire/src/utility/twi.c"]
        objs = []
        for i, src in enumerate(srcs):
            base = os.path.basename(src)
            if base == "main.cpp":
                continue   # linked separately so the sketch can use it
            obj = os.path.join(objdir, f"{i}_{base}.o")
            if src.endswith(".cpp"):
                cmd = ["avr-g++", "-c"] + COMMON + CXXFLAGS + [src, "-o", obj]
            elif src.endswith(".S"):
                cmd = ["avr-gcc", "-c", "-x", "assembler-with-cpp"] + COMMON + [src, "-o", obj]
            else:
                cmd = ["avr-gcc", "-c"] + COMMON + CFLAGS + [src, "-o", obj]
            r = _run(cmd)
            if r.returncode != 0:
                raise RuntimeError("core build failed: " + r.stderr[-800:])
            objs.append(obj)
        tmp = lib + ".tmp"
        if os.path.exists(tmp):
            os.remove(tmp)
        r = _run(["avr-ar", "rcs", tmp] + objs)
        if r.returncode != 0:
            raise RuntimeError("ar failed: " + r.stderr)
        os.replace(tmp, lib)
        return lib


def _clean_log(text: str, workdir: str) -> str:
    text = text.replace(workdir + "/", "")
    return text.strip()[-1800:]


def _size(elf: str):
    r = _run(["avr-size", "-A", elf])
    flash = ram = 0
    for line in r.stdout.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[0] in (".text", ".data"):
            flash += int(parts[1])
        if len(parts) >= 2 and parts[0] in (".data", ".bss", ".noinit"):
            ram += int(parts[1])
    return flash, ram


def compile_sketch(sketch: str) -> CompileResult:
    if not toolchain_ready():
        return CompileResult(False, "The AVR compiler is not installed on this server.")
    with _compile_lock:
        try:
            core = _build_core()
        except Exception as e:  # noqa
            return CompileResult(False, f"Server setup problem: {e}")
        with tempfile.TemporaryDirectory(prefix="sk_") as wd:
            # the sketch is plain C++; univox.h comes from this folder
            src = os.path.join(wd, "sketch.cpp")
            with open(src, "w") as f:
                f.write("#include <Arduino.h>\n" + sketch)
            obj = os.path.join(wd, "sketch.o")
            r = _run(["avr-g++", "-c"] + COMMON + CXXFLAGS + [f"-I{HERE}", src, "-o", obj], cwd=wd)
            if r.returncode != 0:
                return CompileResult(False, _clean_log(r.stderr or r.stdout, wd))
            main_obj = os.path.join(CACHE, "main.o")
            if not os.path.exists(main_obj):
                r = _run(["avr-g++", "-c"] + COMMON + CXXFLAGS +
                         [f"{CORE_DIR}/cores/arduino/main.cpp", "-o", main_obj])
                if r.returncode != 0:
                    return CompileResult(False, "Server setup problem: " + r.stderr[-500:])
            elf = os.path.join(wd, "sketch.elf")
            r = _run(["avr-gcc", f"-mmcu={MCU}", "-Os", "-Wl,--gc-sections", "-o", elf,
                      obj, main_obj, core, "-lm"], cwd=wd)
            if r.returncode != 0:
                return CompileResult(False, _clean_log(r.stderr or r.stdout, wd))
            flash, ram = _size(elf)
            if flash > FLASH_MAX:
                return CompileResult(False, f"Program too big: {flash} of {FLASH_MAX} bytes of flash.",
                                     flash_bytes=flash, ram_bytes=ram)
            hex_path = os.path.join(wd, "sketch.hex")
            r = _run(["avr-objcopy", "-O", "ihex", "-R", ".eeprom", elf, hex_path])
            if r.returncode != 0:
                return CompileResult(False, "objcopy failed: " + r.stderr[-300:])
            with open(hex_path) as f:
                hex_text = f.read()
            return CompileResult(True, "Compiled OK", flash, ram, hex_text,
                                 round(100 * flash / FLASH_MAX, 1), round(100 * ram / RAM_MAX, 1))
