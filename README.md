# advance-p4-wiz

A wizard that creates new **ESP-IDF 6.x** applications for the **Elecrow CrowPanel
Advanced 7" / 10.1"** (ESP32-P4, hardware **V1.2**).

Each generated app starts with:
- the 1024 x 600 MIPI-DSI panel;
- GT911 touch;
- LVGL 9, without tearing;
- a PWM backlight;
- a demo screen: colour bars, a dot that follows your finger, a brightness slider.

Optional modules add:
- **Wi-Fi**, through the onboard ESP32-C6;
- **the speaker**;
- **an AI demo:** draw a digit on the screen, and a small neural network running
  on the P4 (Espressif's ESP-DL) names it;
- **a BME690 sensor** (temperature, humidity, pressure, gas) on the I2C connector.

```sh
./p4wiz.py ~/projects/my_app --wifi hosted2 --audio --ai -y
```

## Requirements

- **ESP-IDF 6.x**, built and tested against **v6.1**: [install guide](https://docs.espressif.com/projects/esp-idf/en/latest/esp32p4/get-started/).
- **Python 3**, to run the wizard. It uses only the standard library.
- A CrowPanel Advanced 7" or 10.1", **hardware V1.2**, and a USB-C data cable.

## 1. Create an app

Run the wizard with no arguments, and it asks for everything:

```sh
./p4wiz.py
```

Or give everything on the command line:

```sh
./p4wiz.py ~/projects/my_app --wifi hosted2 --audio --ai --chip-rev v1 -y
```

| option | what it does |
|---|---|
| `DIR` | the new project's directory. It must not exist yet, and its path must not contain `[` or `]` (LVGL's build breaks on them) |
| `--name NAME` | the CMake project name. Default: the directory's name |
| `--wifi hosted2\|hosted3\|none` | Wi-Fi through the onboard ESP32-C6. **`hosted2`** (esp_hosted 2.12.x) matches the firmware Elecrow ships on the C6 and is recommended. `hosted3` (esp_hosted 3.x) is documented as working with it too |
| `--audio` / `--no-audio` | the speaker: plain I2S, and a beep at boot |
| `--ai` / `--no-ai` | the handwritten-digit demo (ESP-DL). The app grows to about 2.6 MB, so the module brings its own partition table (a 6 MB app partition) |
| `--bme690` / `--no-bme690` | a BME690 sensor on the board's I2C connector, read every 3 s, shown on a card and in the log. Wiring: VCC 3.3 V, GND, SDA, SCL, **CS to 3.3 V** (I2C mode), SDO to GND (address 0x76) or 3.3 V (0x77). See cookbook step 15 |
| `--chip-rev v1\|v3\|detect` | the P4's chip revision (see below). Default: `v1` |
| `--claude-md` / `--no-claude-md` | also write a `CLAUDE.md` into the project, for further work on it with [Claude Code](https://claude.com/claude-code): its files, how to build and flash it, the board's rules and pitfalls, and a section per module chosen. Default: yes |
| `--port PORT` | the board's serial port, needed by `detect`, `--backup` and `--flash` |
| `--backup FILE` | first read the board's whole 16 MB flash into FILE |
| `--build` | also build the app, then run `--check`. Needs `idf.py` on your PATH (run the wizard from an ESP-IDF terminal, step 2) or `--idf-env` |
| `--flash` | also build, flash and open the monitor |
| `--idf-env SCRIPT` | run the IDF commands through a wrapper script, if `idf.py` isn't on your PATH |
| `-y` | ask nothing: anything not given takes its default (no Wi-Fi, no audio, no AI, no BME690, rev v1, a CLAUDE.md) |
| `--check DIR` | check a built project (see step 3) |

### The chip revision matters

ESP-IDF 6.x builds for P4 **rev v3.1 and later** by default. Such an image
builds fine but **won't boot** on an older chip. The boards tested so far have
a **rev v1.3** P4, which is what `--chip-rev v1` (the default) is for. To read
your board's revision:

```sh
esptool.py --port PORT --baud 460800 chip_id     # look for "revision v1.3"
```

Or let the wizard read it: `--chip-rev detect --port PORT`. `v3` is for a
rev v3.x chip. **It has not been tried on one.**

## 2. Open an ESP-IDF terminal

Every command from here on runs in a shell with ESP-IDF 6.x loaded. With a
manual install, for example:

```sh
. ~/esp/esp-idf/export.sh          # Linux / macOS
```

On Windows, use the "ESP-IDF 6.x PowerShell" or "CMD" shortcut that the
installer created. With the EIM installer, use the environment it sets up.
Check that it worked with `idf.py --version`.

## 3. Build

```sh
cd ~/projects/my_app
idf.py set-target esp32p4      # only the first time
idf.py build
```

The first build downloads the components (the panel and touch drivers, LVGL,
and esp_hosted / ESP-DL if chosen) into `managed_components/`. It takes a few
minutes. Later builds are incremental.

Then check that ESP-IDF applied every setting the wizard wrote into
`sdkconfig.defaults`:

```sh
/path/to/advance-p4-wiz/p4wiz.py --check .
```

Silent failures are possible here, most of all with Wi-Fi. esp_hosted 3.x
renamed all its options: given the old names, the build still succeeds but
uses the wrong pins. `--check` catches that.

**After you edit `sdkconfig.defaults`**, delete the generated `sdkconfig` and
rebuild: `sdkconfig.defaults` only applies to a fresh `sdkconfig`.

### Wi-Fi: set the network to join

With `--wifi`, the app scans at boot, then joins a network. There are two
ways to set it:

- **On screen** (no rebuild): tap the Wi-Fi button in the top-left corner,
  pick a network from the list, type the password, and press Connect. The
  network is saved on the board once it has connected, and kept across
  reboots until you press **Forget**.
- **In menuconfig**, as a fallback when nothing is saved on screen:

  ```sh
  idf.py menuconfig        # CrowPanel Wi-Fi > Network name (SSID) / Password, then save
  idf.py build
  ```

  The values go in the generated `sdkconfig`, which the project's
  `.gitignore` keeps out of git. Don't put them in `sdkconfig.defaults`,
  which is committed.

The log shows `connected to "...", IP ...` once it has joined, or the reason
it couldn't.

> **The password is stored in plain text** either way: one from menuconfig is
> compiled into `build/*.bin`, and one typed on screen is saved in the board's
> flash. Anyone with those `.bin` files, or a flash backup, can read it.
> **Don't share or upload builds or backups made with your real password**
> (for example as release files in a public repo); build those with the
> password empty.

## 4. Flash

**Flashing replaces the firmware on the board, Elecrow's factory demo
included.** To keep a copy, back up the whole flash first (16 MB, about 7
minutes):

```sh
esptool.py --port PORT --baud 460800 read_flash 0 0x1000000 crowpanel-backup.bin
```

(or `./p4wiz.py ... --backup crowpanel-backup.bin --port PORT`). To restore it
later: `esptool.py --port PORT --baud 460800 write_flash 0 crowpanel-backup.bin`.

### Which USB socket, which port

Plug into the socket labelled **UART**. It goes through a CH340 USB-serial chip
to the P4's console, and handles both flashing and the log. The P4's own USB
socket isn't used. The serial port shows up as:

| system | port |
|---|---|
| Linux | `/dev/ttyUSB0`, `/dev/ttyUSB1`, ... (`ls /dev/ttyUSB*` before and after plugging in). Your user needs the `dialout` group |
| macOS | `/dev/cu.wchusbserial...` or `/dev/cu.usbserial-...` |
| Windows | `COM3`, `COM4`, ... (Device Manager, "Ports"). Install the CH340 driver if none appears |

### Flash and watch the log

```sh
idf.py -p PORT -b 460800 flash monitor
```

- **Use 460800 baud.** At 921600 this board's CH340 has dropped bytes.
- Flashing starts by itself: the tools reset the board into its bootloader. If
  it can't connect, hold **BOOT**, press **RESET**, release **BOOT**, and
  retry.
- The monitor shows the board's log. Press **Ctrl+]** to leave it. It also
  turns crash addresses into source lines.

To watch the log again later without flashing: `idf.py -p PORT monitor`.

## 5. Check it on the board

A good boot log shows:

```
I (...) boot: chip revision: v1.3
I (...) esp_psram: Found 32MB PSRAM device
I (...) esp_psram: Speed: 200MHz
I (...) board: I2C scan: 0x2f 0x5d
I (...) board: GT911 ready
I (...) board: CrowPanel P4 up: 1024x600, 2 lanes x 900 Mbps, 51 MHz dpi
I (...) digit: model loaded: ...          (with --ai)
I (...) bme690: BME690 at 0x76, ...      (with --bme690; the I2C scan also lists 0x76)
```

On the screen:
1. The three bars read **red, green, blue**, left to right.
2. The dot lands **under your finger**, in the corners and the centre.
3. The **slider** dims the backlight, without flicker.
4. With `--ai`, **draw a digit** in the box on the right. After a short pause
   it shows the digit and how sure it is. The log also prints the 28 x 28
   image the model saw, which is the first thing to look at when it guesses
   wrong.

[`docs/advance-p4-cookbook.md`](docs/advance-p4-cookbook.md) step 9 says what
to change when one of these is off.

## What has been tested

Tested on a CrowPanel Advanced **10.1" V1.2** with a rev v1.3 P4, on ESP-IDF
**v6.1**:

| | status |
|---|---|
| base app: panel, touch, backlight, colours | built, **flashed, works** |
| AI digit demo | built, **flashed, works** (~3 ms per digit) |
| Wi-Fi, esp_hosted 2.12.x (`hosted2`) | built, **flashed, works**: the scan, and joining a WPA2 network set on screen (IP by DHCP), and rejoining it after a power-on. The menuconfig network and reconnecting after a drop: not tried yet |
| Wi-Fi, esp_hosted 3.x (`hosted3`) | built only |
| speaker | built only on IDF 6. Works on the same board under IDF 5.4 |
| BME690 sensor | built; a 4-wire breakout answers at 0x77 on the board's I2C scan. The module itself not run yet |
| `--chip-rev v3` | built only. No rev v3 board tried |
| 7" panel | not tried |

**Wi-Fi beyond the first join (reconnects, other networks, esp_hosted 3.x) is
the part most likely to need fixes.**

## What's in this repository

| path | what |
|---|---|
| `p4wiz.py` | the wizard |
| `template/base/` | the base app the wizard starts from |
| `template/modules/` | the Wi-Fi, audio, AI and BME690 modules |
| `template/claude/` | the parts of the CLAUDE.md that `--claude-md` writes: `base.md`, then one per module |
| `docs/advance-p4-cookbook.md` | the same thing by hand, step by step, with every pitfall found so far. Step 14: growing the skeleton into a real app (memory, tasks, LVGL, HTTPS, microSD, JPEG, testing) |
| `docs/guide_for_agent_advance-p4.md` | the same lessons as one guide for coding agents, from building ArtShow |
| `tools/assemble_reference.sh` | a reference assembly of base + Wi-Fi + audio, for checking the wizard |
| `tools/train_digit_model.py` | retrains the AI demo's model (PyTorch + esp-ppq; see its docstring) |
| `tools/test_digit_prep.py` | tests the AI demo's image preprocessing on a PC |

## Things that bite

- **The image builds but won't boot:** wrong chip revision (step 1).
- **The build fails mysteriously, or LVGL has no sources:** `[` or `]` in the
  project's path.
- **A setting seems ignored:** delete `sdkconfig` and rebuild, then run
  `p4wiz.py --check`.
- **Added a component and the build ignores it:** the manifest must be
  `main/idf_component.yml`, not one at the project root.
- **Expecting an audio codec:** the schematic shows an ES8311, but the boards
  have none. Audio is plain I2S into the amplifiers.

The cookbook's last section lists all the pitfalls found so far.
