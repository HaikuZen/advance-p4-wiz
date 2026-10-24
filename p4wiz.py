#!/usr/bin/env python3
"""p4wiz.py - scaffold a new ESP-IDF 6.x app for the Elecrow CrowPanel Advanced 7" / 10.1"
(ESP32-P4, hardware V1.2), from template/base plus the optional Wi-Fi, audio, AI and BME690 modules.

It applies exactly the wiring of tools/assemble_reference.sh (see CLAUDE.md and
docs/advance-p4-cookbook.md), plus the AI module (handwritten digits, ESP-DL).
Asks for whatever is not given on the command line.

  ./p4wiz.py                                    # fully interactive
  ./p4wiz.py ~/proj/my_app --wifi hosted2 --audio --ai --chip-rev v1 -y
  ./p4wiz.py ~/proj/my_app -y --idf-env tools/idf61.sh --build
  ./p4wiz.py ~/proj/my_app -y --no-claude-md    # without the project's CLAUDE.md (written by default)
  ./p4wiz.py --check ~/proj/my_app              # sdkconfig vs sdkconfig.defaults, after a build
"""
import argparse, datetime, os, re, shutil, string, subprocess, sys

W = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.join(W, "template", "base")
MODS = os.path.join(W, "template", "modules")
CLAUDE = os.path.join(W, "template", "claude")   # CLAUDE.md fragments, for --claude-md
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
BME690_FILES = ("bme690.c", "bme690.h", "bme69x.c", "bme69x.h", "bme69x_defs.h", "LICENSE.bme69x")


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


def assemble(dest, name, wifi, audio, ai, bme690, rev):
    shutil.copytree(BASE, dest)
    main = os.path.join(dest, "main")
    srcs, reqs, includes, calls, ui = [], [], [], [], []

    if wifi:
        n = wifi[-1]   # "hosted2" -> "2"
        for f in ("wifi.c", "wifi.h", "wifi_ui.c", "Kconfig.projbuild"):   # the last: the menuconfig network
            shutil.copy(os.path.join(MODS, "wifi", f), main)
        with open(os.path.join(MODS, "wifi", f"idf_component.hosted{n}.yml")) as f:
            dep = "".join(l for l in f if not l.startswith("#"))
        with open(os.path.join(main, "idf_component.yml"), "a") as f:
            f.write(dep)
        with open(os.path.join(MODS, "wifi", f"sdkconfig.hosted{n}")) as f:
            frag = f.read()
        with open(os.path.join(dest, "sdkconfig.defaults"), "a") as f:
            f.write("\n" + frag)
        srcs += ['"wifi.c"', '"wifi_ui.c"']
        reqs += ["esp_wifi", "esp_netif", "esp_event", "nvs_flash"]
        includes.append('#include "wifi.h"')
        ui.append("        wifi_ui_create(lv_screen_active());")

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

    if bme690:   # Bosch's BME69x Sensor API, vendored, on board.c's I2C bus
        for f in BME690_FILES:
            shutil.copy(os.path.join(MODS, "bme690", f), main)
        srcs += ['"bme690.c"', '"bme69x.c"']
        includes.append('#include "bme690.h"')
        ui.append("        bme690_ui_create(lv_screen_active());")
        calls.append("    bme690_start();")

    if wifi:
        calls.append("    wifi_start();")   # last: its scan blocks

    if srcs:
        edit(os.path.join(main, "CMakeLists.txt"), lambda s: replace_once(
            replace_once(s, 'SRCS "main.c" "board.c"', 'SRCS "main.c" "board.c" ' + " ".join(srcs), "SRCS"),
            "esp_hw_support)", " ".join(["esp_hw_support"] + reqs) + ")", "REQUIRES"))
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


def write_claude_md(dest, name, wifi, audio, ai, bme690, rev, idf_env, port):
    """CLAUDE.md for the new project: template/claude/base.md plus a part per module"""
    mods, files, parts = [], [], []
    if wifi:
        mods.append(f"Wi-Fi (esp_hosted {'2.12.x' if wifi == 'hosted2' else '3.x'})")
        files.append("| `main/wifi.c/.h`, `main/wifi_ui.c`, `main/Kconfig.projbuild` | Wi-Fi through the C6: see Wi-Fi below |")
        parts.append("wifi.md")
    if audio:
        mods.append("audio")
        files.append("| `main/audio.c/.h` | the speaker: see Audio below |")
        parts.append("audio.md")
    if ai:
        mods.append("the AI digit demo")
        files.append("| `main/digit*.c/.h`, `main/digit_model.cpp`, `main/models/` | the AI demo: see AI below |")
        files.append("| `partitions.csv` | the AI module's partition table (6 MB app) |")
        parts.append("ai.md")
    if bme690:
        mods.append("a BME690 sensor")
        files.append("| `main/bme690.c/.h`, `main/bme69x*` | the BME690 on the I2C connector: see BME690 below |")
        parts.append("bme690.md")
    rev_text = ("**rev v1.x** (the bench board is v1.3): `sdkconfig.defaults` builds for it." if rev == "v1" else
                "**rev v3.x**: `sdkconfig.defaults` keeps IDF 6.x's defaults (rev >= 3.1). "
                "**Untested on hardware**: only rev v1.3 boards have run these files.")
    idf = f"{os.path.abspath(idf_env)} " if idf_env else ""
    v = dict(name=name, date=datetime.date.today().isoformat(), wizard=W,
             modules=", ".join(mods) or "the base only (display, touch, backlight)",
             files="".join(f + "\n" for f in files), port=port or "/dev/ttyUSBx", idf=idf,
             idf_note=f" (here: through `{idf.strip()}`, a wrapper that runs a command in one)" if idf else
                      " (`export.sh`, or EIM's `activate_idf_*.sh`)",
             rev_text=rev_text, hosted="2.12.x" if wifi == "hosted2" else "3.x")
    def part(f):
        with open(os.path.join(CLAUDE, f)) as fh:
            return string.Template(fh.read()).substitute(v)
    v["sections"] = "".join(part(f) for f in parts)
    with open(os.path.join(dest, "CLAUDE.md"), "w") as f:
        f.write(part("base.md"))


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
    ap.add_argument("--bme690", action=argparse.BooleanOptionalAction,
                    help="a BME690 sensor (temperature, humidity, pressure, gas) on the I2C connector")
    ap.add_argument("--chip-rev", choices=["v1", "v3", "detect"],
                    help="the P4's revision: v1 (bench board: v1.3), v3, or detect with esptool")
    ap.add_argument("--port", help="the board's UART socket, for detect / backup / flash (e.g. /dev/ttyUSB3)")
    ap.add_argument("--backup", metavar="FILE", help="first read the whole 16 MB flash into FILE")
    ap.add_argument("--idf-env", metavar="SCRIPT", help="wrapper that runs a command in an IDF 6.x env (e.g. tools/idf61.sh)")
    ap.add_argument("--build", action=argparse.BooleanOptionalAction, help="set-target + build, then --check")
    ap.add_argument("--flash", action="store_true", help="after the build, flash and monitor on --port (replaces the firmware!)")
    ap.add_argument("--claude-md", action=argparse.BooleanOptionalAction,
                    help="write a CLAUDE.md into the project (the default): its files, build, rules and pitfalls, for Claude Code")
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

    if a.bme690 is None:
        a.bme690 = ask_yn("A BME690 sensor on the I2C connector (temperature, humidity, pressure, gas)?", False) if asking else False

    if a.claude_md is None:
        a.claude_md = ask_yn("A CLAUDE.md for further development with Claude Code?", True) if asking else True

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

    assemble(dest, name, wifi, a.audio, a.ai, a.bme690, rev)
    if a.claude_md:
        write_claude_md(dest, name, wifi, a.audio, a.ai, a.bme690, rev, a.idf_env, a.port)
    print(f"\ncreated {dest}")
    print(f"  project {name}; Wi-Fi: {wifi or 'none'}; audio: {'yes' if a.audio else 'no'}; AI: {'yes' if a.ai else 'no'}; BME690: {'yes' if a.bme690 else 'no'}; chip rev {rev}.x"
          f"{'; CLAUDE.md' if a.claude_md else ''}")

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
        print("Wi-Fi: set the network on screen (the button top left), or in idf.py menuconfig > CrowPanel Wi-Fi.")
    if a.ai:
        print("The digit model has never run on the board: try a few drawn digits (the log shows what it saw).")
    if a.bme690:
        print("BME690: CS to 3.3 V, SDO to GND (0x76) or 3.3 V (0x77); the boot's I2C scan should list it.")
    if rev == "v3":
        print("Chip rev v3.x: the sdkconfig for it is untested on hardware.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit("\naborted")
