#!/usr/bin/env python3
"""p4wiz.py - scaffold a new ESP-IDF 6.x app for the Elecrow CrowPanel Advanced 7" / 10.1"
(ESP32-P4, hardware V1.2), from template/base plus the optional Wi-Fi and audio modules.

It applies exactly the wiring of tools/assemble_reference.sh (see CLAUDE.md and
docs/advance-p4-cookbook.md), plus the AI module (handwritten digits, ESP-DL).
Asks for whatever is not given on the command line.

  ./p4wiz.py                                    # fully interactive
  ./p4wiz.py ~/proj/my_app --wifi hosted2 --audio --ai --chip-rev v1 -y
  ./p4wiz.py ~/proj/my_app -y --idf-env tools/idf61.sh --build
  ./p4wiz.py --check ~/proj/my_app              # sdkconfig vs sdkconfig.defaults, after a build
"""
import argparse, os, re, shutil, subprocess, sys

W = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.join(W, "template", "base")
MODS = os.path.join(W, "template", "modules")
BAUD = 460800   # 921600 corrupted a full flash read on this board's CH340

REV_V1_BLOCK = """\
# The board's P4 is rev v1.x. IDF 6.x builds for rev >= 3.1 by default, and
# such an image REFUSES TO BOOT on a v1.x chip. Rev <3 and >=3 are exclusive.
CONFIG_ESP32P4_SELECTS_REV_LESS_V3=y
CONFIG_ESP32P4_REV_MIN_100=y
CONFIG_ESP_DEFAULT_CPU_FREQ_MHZ_360=y
"""
REV_V3_BLOCK = """\
# The board's P4 is rev v3.x: IDF 6.x's own defaults (rev >= 3.1) apply.
# NOT VERIFIED on hardware: only rev v1.3 boards have been tested.
"""
APP_END = "        lvgl_port_unlock();\n    }\n}"
AI_FILES = ("digit.c", "digit.h", "digit_prep.c", "digit_prep.h", "digit_model.cpp")


def die(msg):
    sys.exit(f"p4wiz: {msg}")


def interactive():
    return sys.stdin.isatty()


def ask(question, choices, default):
    """choices: list of (value, label). Returns a value."""
    print(f"\n{question}")
    for i, (v, label) in enumerate(choices, 1):
        print(f"  {i}) {label}{'  [default]' if v == default else ''}")
    while True:
        a = input("> ").strip()
        if not a:
            return default
        if a.isdigit() and 1 <= int(a) <= len(choices):
            return choices[int(a) - 1][0]
        for v, _ in choices:
            if a == v:
                return v
        print("  pick a number from the list")


def ask_yn(question, default):
    a = input(f"\n{question} [{'Y/n' if default else 'y/N'}] ").strip().lower()
    return default if not a else a.startswith("y")


def ask_text(question, default):
    a = input(f"\n{question} [{default}] ").strip()
    return a or default


def idf_py():
    """how to run idf.py from here, or None: on PATH (export.sh), else through
    $IDF_PATH with the IDF venv's python. EIM's activate script makes idf.py a
    shell function, which a child process like this one can't see"""
    if shutil.which("idf.py"):
        return ["idf.py"]
    idf_path, venv = os.environ.get("IDF_PATH"), os.environ.get("IDF_PYTHON_ENV_PATH", "")
    tool = os.path.join(idf_path or "", "tools", "idf.py")
    if not idf_path or not os.path.isfile(tool):
        return None
    py = next((p for p in (os.path.join(venv, "bin", "python"), os.path.join(venv, "Scripts", "python.exe"))
               if venv and os.path.isfile(p)), None) or shutil.which("python") or shutil.which("python3")
    return [py, tool] if py else None


def run_idf(idf_env, args, cwd, capture=False):
    """run an IDF command, through the wrapper script if one is given"""
    if idf_env:
        cmd = [os.path.abspath(idf_env)] + args
    else:
        cmd = (idf_py() + args[1:]) if args[0] == "idf.py" else args
    print(f"$ (cd {cwd} && {' '.join(args)})")
    return subprocess.run(cmd, cwd=cwd, text=True, capture_output=capture)


def esptool(idf_env, args, cwd):
    if idf_env:
        return run_idf(idf_env, ["esptool.py"] + args, cwd, capture=True)
    exe = shutil.which("esptool.py") or shutil.which("esptool")
    if not exe:
        die("esptool not found: put it on PATH, or pass --idf-env")
    print(f"$ {os.path.basename(exe)} {' '.join(args)}")
    return subprocess.run([exe] + args, cwd=cwd, text=True, capture_output=True)


def detect_rev(port, idf_env):
    r = esptool(idf_env, ["--port", port, "--baud", str(BAUD), "chip_id"], os.getcwd())
    out = r.stdout + r.stderr
    m = re.search(r"ESP32-P4.*?revision v(\d+)\.(\d+)", out)
    if r.returncode or not m:
        print(out)
        die(f"could not read the chip revision on {port}")
    major, minor = int(m.group(1)), int(m.group(2))
    print(f"  chip: ESP32-P4 rev v{major}.{minor}")
    return "v3" if major >= 3 else "v1"


def backup(port, idf_env, out):
    if os.path.exists(out):
        die(f"{out} exists, not overwriting a backup")
    print(f"  reading all 16 MB at {BAUD} baud: this takes a few minutes")
    r = esptool(idf_env, ["--port", port, "--baud", str(BAUD), "read_flash", "0", "0x1000000",
                          os.path.abspath(out)], os.getcwd())
    if r.returncode:
        print(r.stdout + r.stderr)
        die("backup failed")
    print(f"  backup: {out}  (restore: esptool.py -p {port} -b {BAUD} write_flash 0 {out})")


# --- assembly: the same edits as tools/assemble_reference.sh ---

def edit(path, fn):
    with open(path) as f:
        s = f.read()
    s = fn(s)
    with open(path, "w") as f:
        f.write(s)


def replace_once(s, old, new, what):
    if s.count(old) != 1:
        die(f"template changed: can't find the {what} anchor")
    return s.replace(old, new, 1)


def assemble(dest, name, wifi, audio, ai, rev):
    shutil.copytree(BASE, dest)
    main = os.path.join(dest, "main")
    srcs, reqs, includes, calls, ui = [], [], [], [], []

    if wifi:
        n = wifi[-1]   # "hosted2" -> "2"
        for f in ("wifi.c", "wifi.h"):
            shutil.copy(os.path.join(MODS, "wifi", f), main)
        with open(os.path.join(MODS, "wifi", f"idf_component.hosted{n}.yml")) as f:
            dep = "".join(l for l in f if not l.startswith("#"))
        with open(os.path.join(main, "idf_component.yml"), "a") as f:
            f.write(dep)
        with open(os.path.join(MODS, "wifi", f"sdkconfig.hosted{n}")) as f:
            frag = f.read()
        with open(os.path.join(dest, "sdkconfig.defaults"), "a") as f:
            f.write("\n" + frag)
        srcs.append('"wifi.c"')
        reqs += ["esp_wifi", "esp_netif", "esp_event", "nvs_flash"]
        includes.append('#include "wifi.h"')

    if audio:
        for f in ("audio.c", "audio.h"):
            shutil.copy(os.path.join(MODS, "audio", f), main)
        srcs.append('"audio.c"')
        reqs.append("esp_driver_i2s")
        includes.append('#include "audio.h"')
        calls += ["    audio_init();", "    audio_beep(880, 150);"]

    if ai:
        for f in AI_FILES:
            shutil.copy(os.path.join(MODS, "ai", f), main)
        os.makedirs(os.path.join(main, "models"))
        shutil.copy(os.path.join(MODS, "ai", "models", "digit.espdl"), os.path.join(main, "models"))
        with open(os.path.join(MODS, "ai", "idf_component.ai.yml")) as f:
            dep = "".join(l for l in f if not l.startswith("#"))
        with open(os.path.join(main, "idf_component.yml"), "a") as f:
            f.write(dep)
        shutil.copy(os.path.join(MODS, "ai", "partitions.csv"), dest)
        with open(os.path.join(MODS, "ai", "sdkconfig.ai")) as f:
            frag = f.read()
        edit(os.path.join(dest, "sdkconfig.defaults"), lambda s: replace_once(
            s, "CONFIG_PARTITION_TABLE_SINGLE_APP_LARGE=y\n", frag, "partition table"))
        srcs += ['"digit.c"', '"digit_prep.c"', '"digit_model.cpp"']
        reqs += ["esp-dl", "esp_timer"]
        includes.append('#include "digit.h"')
        ui.append("        digit_ui_create(lv_screen_active());")

    if wifi:
        calls.append("    wifi_scan_once();")   # last: the scan blocks

    if srcs:
        edit(os.path.join(main, "CMakeLists.txt"), lambda s: replace_once(
            replace_once(s, 'SRCS "main.c" "board.c"', 'SRCS "main.c" "board.c" ' + " ".join(srcs), "SRCS"),
            "esp_hw_support)", "esp_hw_support " + " ".join(reqs) + ")", "REQUIRES"))
        edit(os.path.join(main, "main.c"), lambda s: replace_once(
            replace_once(s, '#include "esp_log.h"', '#include "esp_log.h"\n' + "\n".join(includes), "include"),
            APP_END, "        lvgl_port_unlock();\n    }\n" + "".join(c + "\n" for c in calls) + "}", "app_main end"))
    if ui:
        edit(os.path.join(main, "main.c"), lambda s: replace_once(
            s, "        build_ui();\n", "        build_ui();\n" + "".join(u + "\n" for u in ui), "build_ui()"))
    if ai:   # after idf_component_register: it needs ${COMPONENT_LIB}
        with open(os.path.join(MODS, "ai", "CMakeLists.ai.cmake")) as f:
            frag = f.read()
        with open(os.path.join(main, "CMakeLists.txt"), "a") as f:
            f.write(frag)

    if rev == "v3":
        edit(os.path.join(dest, "sdkconfig.defaults"), lambda s: replace_once(s, REV_V1_BLOCK, REV_V3_BLOCK, "chip revision"))

    edit(os.path.join(dest, "CMakeLists.txt"), lambda s: replace_once(s, "project(my_p4_app)", f"project({name})", "project()"))

    with open(os.path.join(dest, ".gitignore"), "w") as f:
        f.write("build/\nmanaged_components/\nsdkconfig\nsdkconfig.old\n")


# --- check: every sdkconfig.defaults line must survive into sdkconfig ---

def check(dest):
    sdk = os.path.join(dest, "sdkconfig")
    if not os.path.exists(sdk):
        die(f"no {sdk}: run idf.py set-target esp32p4 (or a build) first")
    with open(sdk) as f:
        have = set(l.strip() for l in f)
    with open(os.path.join(dest, "sdkconfig.defaults")) as f:
        want = [l.strip() for l in f if l.startswith("CONFIG_")]
    bad = [l for l in want if l not in have]
    for l in bad:
        key = l.split("=")[0]
        got = next((h for h in have if h.startswith(key + "=") or h == f"# {key} is not set"), "missing: unknown symbol?")
        print(f"  MISMATCH {l}   sdkconfig has: {got}")
    # the two values a mixed-up esp_hosted config gets wrong
    for key in ("SDIO_PIN_D0", "RESET"):
        for h in sorted(have):
            if h.startswith("CONFIG_ESP_HOSTED") and key in h and "=" in h and not h.endswith("=y"):
                print(f"  {h}")
    if bad:
        die(f"{len(bad)} sdkconfig.defaults line(s) not applied. Delete sdkconfig and rebuild; "
            "if it persists, a fragment uses option names this component version doesn't know")
    print(f"  sdkconfig OK: all {len(want)} sdkconfig.defaults lines applied")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter,
                                 epilog=__doc__.split("\n\n", 2)[2])
    ap.add_argument("dir", nargs="?", help="new project directory (must not exist)")
    ap.add_argument("--name", help="CMake project name (default: the directory name)")
    ap.add_argument("--wifi", choices=["none", "hosted2", "hosted3"],
                    help="Wi-Fi via the C6: esp_hosted 2.12.x (matches Elecrow's C6, recommended) or 3.x")
    ap.add_argument("--audio", action=argparse.BooleanOptionalAction, help="the speaker (plain I2S)")
    ap.add_argument("--ai", action=argparse.BooleanOptionalAction,
                    help="the AI demo: draw a digit, an int8 CNN on the P4 (ESP-DL) names it")
    ap.add_argument("--chip-rev", choices=["v1", "v3", "detect"],
                    help="the P4's revision: v1 (bench board: v1.3), v3, or detect with esptool")
    ap.add_argument("--port", help="the board's UART socket, for detect / backup / flash (e.g. /dev/ttyUSB3)")
    ap.add_argument("--backup", metavar="FILE", help="first read the whole 16 MB flash into FILE")
    ap.add_argument("--idf-env", metavar="SCRIPT", help="wrapper that runs a command in an IDF 6.x env (e.g. tools/idf61.sh)")
    ap.add_argument("--build", action=argparse.BooleanOptionalAction, help="set-target + build, then --check")
    ap.add_argument("--flash", action="store_true", help="after the build, flash and monitor on --port (replaces the firmware!)")
    ap.add_argument("-y", "--yes", action="store_true", help="take the defaults for anything not given, ask nothing")
    ap.add_argument("--check", metavar="DIR", help="only verify DIR's generated sdkconfig")
    a = ap.parse_args()

    if a.check:
        check(a.check)
        return

    asking = interactive() and not a.yes
    if not a.dir:
        if not asking:
            die("give the project directory")
        a.dir = ask_text("Project directory?", "./my_p4_app")
    dest = os.path.abspath(os.path.expanduser(a.dir))
    if os.path.exists(dest):
        die(f"{dest} already exists")
    if "[" in dest or "]" in dest:
        die(f"{dest}: '[' or ']' in the path breaks LVGL's source glob; pick another place")

    name = a.name or re.sub(r"\W", "_", os.path.basename(dest))
    if not re.fullmatch(r"[A-Za-z_]\w*", name):
        die(f"bad project name {name!r}: letters, digits and _ only, not starting with a digit")

    if a.wifi is None:
        a.wifi = ask("Wi-Fi through the onboard ESP32-C6?", [
            ("hosted2", "yes, esp_hosted 2.12.x - same major as Elecrow's C6 firmware (2.12.3), recommended"),
            ("hosted3", "yes, esp_hosted 3.x - back-compatible with a 2.x C6, upgrading the C6 recommended"),
            ("none", "no Wi-Fi")], "hosted2") if asking else "none"
    wifi = None if a.wifi == "none" else a.wifi

    if a.audio is None:
        a.audio = ask_yn("The speaker (plain I2S, a beep at boot)?", True) if asking else False

    if a.ai is None:
        a.ai = ask_yn("The AI demo (draw a digit, ESP-DL recognizes it)?", False) if asking else False

    if a.chip_rev is None:
        a.chip_rev = ask("The P4's chip revision? (IDF 6.x images for the wrong one won't boot)", [
            ("v1", "rev v1.x - the bench board is v1.3"),
            ("v3", "rev v3.x - not verified on hardware"),
            ("detect", "detect it with esptool chip_id (needs the board on the UART socket)")], "v1") if asking else "v1"

    if (a.chip_rev == "detect" or a.backup or a.flash) and not a.port:
        if not asking:
            die("--port is needed for detect / --backup / --flash")
        a.port = ask_text("Serial port of the board's UART socket?", "/dev/ttyUSB0")

    if a.backup is None and asking and a.port:
        if ask_yn("Back up the factory firmware first (16 MB read, read-only)?", False):
            a.backup = ask_text("Backup file?", "crowp4-factory-full.bin")

    if a.flash:
        a.build = True
    if a.build is None:
        a.build = ask_yn("Build it now?", True) if asking else False

    # before touching the board or the disk: a build needs an IDF environment
    if a.build and not a.idf_env and not idf_py():
        die("idf.py not found, neither on PATH nor through $IDF_PATH: run the wizard from an ESP-IDF 6.x "
            "terminal (export.sh, or EIM's activate_idf_*.sh), pass --idf-env SCRIPT (a wrapper that runs "
            "a command in one), or drop --build / --flash")

    if a.backup:
        backup(a.port, a.idf_env, a.backup)
    rev = detect_rev(a.port, a.idf_env) if a.chip_rev == "detect" else a.chip_rev

    assemble(dest, name, wifi, a.audio, a.ai, rev)
    print(f"\ncreated {dest}")
    print(f"  project {name}; Wi-Fi: {wifi or 'none'}; audio: {'yes' if a.audio else 'no'}; AI: {'yes' if a.ai else 'no'}; chip rev {rev}.x")

    if a.build:
        r = run_idf(a.idf_env, ["idf.py", "set-target", "esp32p4", "build"], dest, capture=True)
        log = r.stdout + r.stderr
        with open(os.path.join(dest, "build-wizard.log"), "w") as f:
            f.write(log)
        if r.returncode:
            print(log[-4000:])
            die(f"build failed: full log in {dest}/build-wizard.log")
        warns = sorted(set(re.findall(r".*(?:warning:|unknown kconfig symbol).*", log, re.I)))
        for w in warns:
            print(f"  {w.strip()}")
        print(f"  build OK{f', {len(warns)} warning line(s)' if warns else ', no warnings'}")
        check(dest)
        if a.flash:
            print(f"  flashing {a.port}: this replaces the board's current firmware")
            run_idf(a.idf_env, ["idf.py", "-p", a.port, "-b", str(BAUD), "flash", "monitor"], dest)
            return

    env = f"{os.path.abspath(a.idf_env)} " if a.idf_env else ""
    print(f"""
next:
  cd {dest}""" + ("" if a.build else f"""
  {env}idf.py set-target esp32p4 build
  {W}/p4wiz.py --check .        # every sdkconfig.defaults line applied?""") + f"""
  {env}idf.py -p {a.port or '/dev/ttyUSBx'} -b {BAUD} flash monitor   # the UART socket; replaces the firmware
then go through docs/advance-p4-cookbook.md step 9 on the board.""")
    if wifi:
        print("Wi-Fi has never joined a network from these files: expect it to need work.")
    if a.ai:
        print("The digit model has never run on the board: try a few drawn digits (the log shows what it saw).")
    if rev == "v3":
        print("Chip rev v3.x: the sdkconfig for it is untested on hardware.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit("\naborted")
