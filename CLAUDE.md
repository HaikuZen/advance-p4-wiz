# advance-p4-wiz

A setup wizard, `p4wiz.py`, that creates new ESP-IDF 6.x applications for
the **Elecrow CrowPanel Advanced 7" / 10.1"** (ESP32-P4, hardware **V1.2**),
plus the verified building blocks it assembles.

## What is here

| path | what |
|---|---|
| `p4wiz.py` | the wizard (Python 3, stdlib only). See below |
| `README.md` | for users of the public repo: running the wizard, building and flashing an app, what's tested. Keep its status table in step with the verification status below |
| `docs/advance-p4-cookbook.md` | the full manual recipe, step by step, with every pitfall. **Read it first**: the wizard automates it |
| `docs/guide_for_agent_advance-p4.md` | ArtShow's guide for agents (2026-10): what a full app on this board taught. Merged into the cookbook as step 14; keep the two in step |
| `template/base/` | a complete app: 1024x600 MIPI-DSI panel, GT911 touch, LVGL 9 without tearing, PWM backlight, and a demo screen (RGB bars, a touch dot, a brightness slider). Builds as is |
| `template/modules/wifi/` | Wi-Fi through the onboard ESP32-C6 (esp_hosted): `wifi.c/h` (one Wi-Fi task: a scan, then join the network saved on screen in NVS, else the menuconfig one, and keep rejoining), `wifi_ui.c` (on-screen setup: a status button, a scan list, a password field, Forget), `Kconfig.projbuild` (the menuconfig fallback network), with config and dependency fragments for esp_hosted **2.12.x** (`*hosted2*`, recommended) or **3.x** (`*hosted3*`) |
| `template/modules/audio/` | the speaker: plain I2S, no codec (`audio_init`, `audio_beep`) |
| `template/modules/ai/` | AI demo: a drawing pad, and an int8 CNN that ESP-DL runs on the P4 names the digit. `models/digit.espdl` is built by `tools/train_digit_model.py` |
| `template/modules/bme690/` | a BME690 on the I2C connector: `bme690.c/h` (finds it at 0x76/0x77 on `board_i2c_bus()`, a task reads it in forced mode every 3 s, a readings card), plus Bosch's BME69x Sensor API v1.1.0 vendored unchanged (`bme69x.c/h`, `bme69x_defs.h`, `LICENSE.bme69x`, BSD-3) |
| `template/claude/` | the generated project's `CLAUDE.md` (`--claude-md`): `base.md` plus `wifi.md`, `audio.md`, `ai.md`, `bme690.md` for the modules chosen, filled in with `string.Template` (`$name`, `$port`, `${idf}`, ...). Keep them true to the templates when those change |
| `tools/train_digit_model.py` | trains the digit CNN on MNIST (augmented toward finger strokes) and exports it with esp-ppq. Needs `tools/requirements-ai.txt` in a Python 3.12 venv; see its docstring |
| `tools/test_digit_prep.py` | compiles the board's `digit_prep.c` on the host and scores the model on MNIST digits redrawn as the pad sees them |
| `tools/assemble_reference.sh` | reference assembly, base + Wi-Fi + audio: exactly which lines a module adds where. The wizard must reproduce this wiring |
| `tools/idf61.sh` | runs a command in a clean IDF 6.1 environment. **This machine's paths only** |

### The wizard: `p4wiz.py`

```sh
./p4wiz.py                                  # interactive: asks for what isn't given
./p4wiz.py DIR --wifi hosted2|hosted3|none --audio|--no-audio --ai|--no-ai --bme690|--no-bme690 --chip-rev v1|v3|detect -y
./p4wiz.py DIR -y --idf-env tools/idf61.sh --build    # + set-target, build, --check
./p4wiz.py DIR -y --no-claude-md            # without the new project's CLAUDE.md
./p4wiz.py --check DIR                      # every sdkconfig.defaults line in sdkconfig?
```

- `-y`, or no terminal: defaults for anything not given (no Wi-Fi, no audio, no AI, no BME690, rev v1, a CLAUDE.md).
- `--name` sets the CMake project name (default: the directory name).
- `--port` is the board's UART socket, needed by `detect`, `--backup FILE` (a full
  16 MB read) and `--flash` (flash + monitor). All three run at 460800 baud.
- `--idf-env SCRIPT` runs IDF commands through a wrapper; `idf.py` isn't on PATH here.
- It writes a `.gitignore`. With `--build`, the log goes to `build-wizard.log`.
- It writes a `CLAUDE.md` for the new project by default (`--no-claude-md` to
  skip it; asked interactively, default yes): wizard-only, like the AI module.
- `--chip-rev v3` swaps the rev-v1 block of `sdkconfig.defaults` for IDF's
  defaults. **Untested on hardware.**
- It refuses paths with `[` / `]`, existing directories and invalid project names.
- The edits fail loudly if a template anchor moves. With Wi-Fi + audio, its
  output is byte-identical to `tools/assemble_reference.sh` (apart from `.gitignore` and `CLAUDE.md`).
  Keep the two in sync when changing the templates. The AI and BME690 modules are
  wizard-only: the reference script doesn't add them.

### How a module plugs into the base

The wizard must apply each of these steps. `tools/assemble_reference.sh` does
all of them.

- **Wi-Fi:**
  - copy `wifi.c/.h`, `wifi_ui.c` and `Kconfig.projbuild` into `main/`;
  - append the chosen `idf_component.hostedN.yml` under `dependencies:` in
    `main/idf_component.yml`;
  - append `sdkconfig.hostedN` to `sdkconfig.defaults`;
  - in `main/CMakeLists.txt`, add `"wifi.c" "wifi_ui.c"` to SRCS and
    `esp_wifi esp_netif esp_event nvs_flash` to REQUIRES;
  - call `wifi_ui_create(lv_screen_active())` right after `build_ui()`, inside
    the LVGL lock;
  - call `wifi_start()` at the end of `app_main`.
  - The network is set per project in `idf.py menuconfig` > CrowPanel Wi-Fi, so
    it lands in `sdkconfig` (gitignored). **Never** have the wizard write a
    password into `sdkconfig.defaults`: that file is committed. Either way
    (menuconfig into the firmware, or on screen into NVS) the password is in
    flash as plain text: the docs warn against sharing such builds or backups.
- **Audio:**
  - copy `audio.c/.h` into `main/`;
  - in `main/CMakeLists.txt`, add `"audio.c"` to SRCS and `esp_driver_i2s` to
    REQUIRES;
  - call `audio_init()` after `board_init()`.
- **AI (digits):**
  - copy `digit.c/.h`, `digit_prep.c/.h` and `digit_model.cpp` into `main/`, and
    `models/digit.espdl` into `main/models/`;
  - append `idf_component.ai.yml` under `dependencies:`;
  - in `main/CMakeLists.txt`, add `"digit.c" "digit_prep.c" "digit_model.cpp"` to
    SRCS and `esp-dl esp_timer` to REQUIRES, then append `CMakeLists.ai.cmake`
    (after `idf_component_register`: it embeds the model 16-byte aligned, which
    ESP-DL needs and `EMBED_FILES` doesn't guarantee);
  - call `digit_ui_create(lv_screen_active())` right after `build_ui()`, inside
    the LVGL lock. It loads the model too.
- **BME690:**
  - copy `bme690.c/.h`, `bme69x.c/.h`, `bme69x_defs.h` and `LICENSE.bme69x`
    into `main/`;
  - in `main/CMakeLists.txt`, add `"bme690.c" "bme69x.c"` to SRCS (no new
    REQUIRES: the base has `esp_driver_i2c`);
  - call `bme690_ui_create(lv_screen_active())` right after `build_ui()`,
    inside the LVGL lock, and `bme690_start()` at the end of `app_main`,
    before `wifi_start()`.
  - Wiring: the I2C connector (SDA 45, SCL 46, 3.3 V), CS to 3.3 V, SDO to
    GND (0x76) or 3.3 V (0x77). Never a second bus on 45/46.
- **Project name:** set it in the root `CMakeLists.txt`, `project(my_p4_app)`.

## Verification status (2026-10-18)

**Built** on ESP-IDF **v6.1**, with no warnings:
- the base alone;
- base + Wi-Fi with esp_hosted 2.12.13;
- base + Wi-Fi with esp_hosted 3.0.9;
- base + audio;
- base + Wi-Fi + audio, both esp_hosted options, assembled from these exact
  files.
- generated by `p4wiz.py --build`, each passing `--check`: Wi-Fi 3.x + audio,
  Wi-Fi 2.12.x alone, audio alone with `--chip-rev v3` (sdkconfig: rev min 3.1,
  400 MHz). The interactive prompts were also tried. `--chip-rev detect`,
  `--backup` and `--flash` have never been run against a board.
- the AI module, generated by `p4wiz.py --build`: alone, and with Wi-Fi 2.12.x +
  audio (esp-dl 3.3.13; the app is ~2.6 MB in the module's 6 MB partition). The
  digit model: 99.0% float / 98.35% int8 on MNIST test digits, and 98.7% for
  digits redrawn finger-wide through the board's `digit_prep.c` on the host
  (`tools/test_digit_prep.py`). **Never run on the board**: neither ESP-DL on
  this chip nor real finger drawings.

- the BME690 module (2026-10-24), generated by `p4wiz.py --build`, each passing
  `--check` with no warnings, Bosch's BME69x API included: alone, and with
  Wi-Fi 2.12.x + audio + AI (app 3.0 MB of 6 MB). On the bench board, a BME690
  breakout wired with 4 wires (VCC GND SCL SDA, CS and SDO left to the breakout)
  to the I2C connector **answers at 0x77** in the boot scan (2026-10-24), with
  touch unaffected. Not yet run: the module itself (callbacks, readings).

**Flashed once from an IDF 6.x build (2026-10-18)**, AI-only (base + AI module),
on the bench 10.1":
- boots (chip rev v1.3 settings right), 32 MB PSRAM at 200 MHz, I2C scan
  0x2f 0x5d, GT911 ready, the panel up;
- the first boot found a base bug: `abort()` in `esp_lcd_new_dsi_bus`. IDF 6.1's
  `MIPI_DSI_PHY_PLLREF_CLK_SRC_DEFAULT` is XTAL, rev >= 3.0 only. `board.c` now
  uses `..._DEFAULT_LEGACY` (PLL_F20M) under `CONFIG_ESP32P4_SELECTS_REV_LESS_V3`;
- the AI demo ran: model loaded, two drawn digits (6 at 88%, 0 at 100%) right,
  ~3 ms per inference at 360 MHz;
- two log lines left to look at: `W gpio: conflict found for GPIO[42]` (the GT911
  INT) and `E lcd_panel: swap_xy is not supported by this panel` (esp_lvgl_port
  asking the EK79007); neither stopped anything;
- checked by eye: colours right (RGB bars in order), touch lands under the
  finger, drawn digits recognized. Not reported yet: tearing while dragging the
  slider, and the backlight dimming (cookbook step 9).

**Flashed: Wi-Fi 2.12.x + audio (2026-10-18)**, generated by the wizard
(`../Ideas/ArtShow`), on the bench 10.1":
- **Wi-Fi scan works**, the first time on this board under any IDF: esp_hosted
  2.12.13 brought up 4-bit SDIO (CLK 18, CMD 19, D0..D3 17..14, reset 32),
  identified the esp32c6, and the scan listed 8 networks ~7.5 s after boot.
  The UI was up before it. No reset in 40 s;
- esp_hosted warns `CONFIG_FREERTOS_HZ is 100, ESP-Hosted recommended 1000`;
- **joining works** (ArtShow updated with the join code): set on screen with
  `wifi_ui.c`, it joined a WPA2 network ~6 s after Connect, got an IP by DHCP
  and saved the network in NVS. **Rejoins after a power-on** (2026-10-24): the
  saved network, joined ~1.3 s after the boot scan. Not yet seen: a dropped link, a wrong password, the menuconfig network. The join code also
  builds clean in Wi-Fi 2.12.x + audio + AI and Wi-Fi 3.x + audio;
- audio: no errors in the log; the boot beep not yet confirmed by ear.

The board values (pins, panel timings,
DSI lane rate, the LDO, the backlight, the GT911 settings, the I2S audio) are
proven on the bench board by a working port on IDF 5.4.1: the pocket-tank
firmware, `../pocket-tank`, branch `advance-p4-support`. See
`docs/board-crowpanel-p4.md` and `firmware/main/display_port_dsi.c` there.

**Wi-Fi joins a network** with esp_hosted 2.12.x (on screen, 2026-10-18).
esp_hosted 3.x has not run on the board.

## Things the wizard must get right

- **Chip revision:** the bench board's P4 is **rev v1.3**. IDF 6.x targets rev
  ≥ 3.1 by default, and such an image builds fine but **won't boot**. The base
  `sdkconfig.defaults` sets `CONFIG_ESP32P4_SELECTS_REV_LESS_V3=y` and
  `CONFIG_ESP32P4_REV_MIN_100=y` (with a 360 MHz CPU). A rev v3.x board needs
  the opposite. The wizard should ask, or read it with
  `esptool.py --baud 460800 chip_id`.
- **esp_hosted versions:**
  - Elecrow ships the C6 with esp_hosted **2.12.3**. Option 2 (2.12.x) matches it.
  - Option 3 (3.x) is documented as back-compatible with a 2.x C6, but
    recommends upgrading the C6.
  - **3.x renamed every option.** Given 2.x names, it still builds but uses the
    wrong SDIO pins (D0..D3 reversed) and the wrong C6 reset pin (54 instead of
    32). The only sign is "unknown kconfig symbol" in the build log. Never mix
    the two fragments.
  - After configuring, the wizard should check that `sdkconfig` has the pin
    values: D0 = 17, reset = 32.
- **Codec:** there is no ES8311 on the bench 10.1", even though the schematic
  shows one. The I2C scan finds only 0x5d (GT911) and 0x2f (STC8). Audio is
  plain I2S.
- **USB socket:** flash through the **UART** socket (CH340) at **460800**.
  921600 corrupted a full flash read on this board.
- **Factory backup:** flashing replaces Elecrow's factory firmware. A full
  backup of the bench board is at
  `/root/.cache/pocket-tank/backups/crowp4-factory-full.bin` (16 MB). The
  wizard could offer to take one.
- **Component manifest location:** it must be `main/idf_component.yml`. A
  manifest at the project root is silently ignored.
- **Project path:** no `[` or `]` in it, because LVGL's source glob breaks.
- **Version pins:** the base pins esp_lcd_ek79007 ^2.0.2, esp_lcd_touch_gt911
  ^1.2.1, esp_lvgl_port ^2.9.0 and lvgl ^9.6.0. `main.c` uses LVGL 9.6's
  per-flag setters (`lv_obj_set_hidden`, ...), which older 9.x lacks.

## The bench hardware

- A CrowPanel Advanced **10.1"** V1.2 (SKU DHE04310D) on **/dev/ttyUSB3**.
- `/dev/ttyUSB0-2` are a Huawei modem, not boards.
- That board currently runs **ArtShow** (Wi-Fi 2.12.x + audio, 2026-10-18). Its pocket-tank
  firmware, with the tank's saved state, is backed up in
  `/root/.cache/pocket-tank/backups/crowp4-pocket-tank-2026-10-18.bin` (restore:
  `esptool.py -p /dev/ttyUSB3 -b 460800 write_flash 0 <that file>`). Ask before
  flashing anything else to it.
