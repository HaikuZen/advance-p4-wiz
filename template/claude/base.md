# $name

An ESP-IDF 6.x app for the **Elecrow CrowPanel Advanced 7" / 10.1"** (ESP32-P4,
hardware V1.2), scaffolded by p4wiz on $date with: $modules.

The wizard and its full recipe live in the advance-p4-wiz repo
(https://github.com/HaikuZen/advance-p4-wiz; here: `$wizard`). Its
`docs/advance-p4-cookbook.md` explains every board value and pitfall below.

## Files

| path | what |
|---|---|
| `main/main.c` | `app_main`: `board_init()`, then the UI built under the LVGL lock. `build_ui()` is the demo screen (RGB bars, a touch dot, a brightness slider): replace it with the app's own |
| `main/board.c/.h` | the board: power (LDO3 for the D-PHY), I2C, PWM backlight, the EK79007 MIPI-DSI panel (1024x600), GT911 touch, LVGL through esp_lvgl_port. `board_set_brightness(0..100)`, `board_i2c_bus()` |
| `main/board_pins.h` | every pin and panel value, proven on the bench board. Don't change them without a reason from the hardware |
| `main/idf_component.yml` | the component dependencies. It must stay in `main/`: a manifest at the project root is silently ignored |
| `sdkconfig.defaults` | the committed config. `sdkconfig` is generated and gitignored |
$files
## Build and flash

```sh
${idf}idf.py set-target esp32p4 build     # once; after that, build alone
$wizard/p4wiz.py --check .                # every sdkconfig.defaults line made it into sdkconfig?
${idf}idf.py -p $port -b 460800 flash monitor
```

- Run `idf.py` from an ESP-IDF 6.x terminal$idf_note.
- After editing `sdkconfig.defaults`, delete `sdkconfig` and rebuild, or the
  change is not applied. Then run `--check` again.
- Flash through the **UART** USB socket (CH340), at **460800** baud: 921600
  corrupted reads on this board. If it won't enter the bootloader, hold BOOT,
  press RESET, let go of BOOT.
- Flashing replaces whatever the board runs. Ask before flashing a board, and
  offer a backup first: `${idf}esptool.py -p $port -b 460800 read_flash 0 0x1000000 backup.bin`.

## Rules for working on this app

- **Chip revision:** $rev_text A rev v1.x P4 needs
  `CONFIG_ESP32P4_SELECTS_REV_LESS_V3=y` and `CONFIG_ESP32P4_REV_MIN_100=y`;
  an image built for rev >= 3 (IDF 6.x's default) builds fine but won't boot on
  it. Check a board with `${idf}esptool.py -p $port -b 460800 chip_id`.
- **The DSI clock:** on rev v1.x, `board.c` uses
  `MIPI_DSI_PHY_PLLREF_CLK_SRC_DEFAULT_LEGACY`. IDF 6.1's plain `_DEFAULT` is
  XTAL, which only rev >= 3 has: `esp_lcd_new_dsi_bus` aborts at boot.
- **LVGL 9.6:** any LVGL call from outside the LVGL task holds
  `lvgl_port_lock(0)` (it waits forever; the lock is recursive). Use 9.6's API:
  the per-flag setters (`lv_obj_set_hidden`, `lv_obj_set_clickable`, ...),
  `LV_LABEL_LONG_MODE_*`; `lv_list` is deprecated, so build lists as a flex
  column. Fonts: Montserrat 14, 24 and 32 are enabled in `sdkconfig.defaults`;
  add a `CONFIG_LV_FONT_MONTSERRAT_<n>=y` line for others.
- The screen is 1024x600, landscape. The panel can't swap x/y.
- **No `[` or `]` in the project path:** LVGL's source glob breaks.
- **No codec:** the schematic shows an ES8311, but the board has none. The I2C
  bus holds only the GT911 (0x5d) and the STC8 helper (0x2f).
- Keep the build free of warnings, and grep the build log for "unknown kconfig
  symbol": it means a `sdkconfig.defaults` line was silently dropped.
- Don't write secrets into committed files (`sdkconfig.defaults`, sources).

## Harmless log lines

- `W gpio: conflict found for GPIO[42]`: the GT911 INT pin; touch works.
- `E lcd_panel: swap_xy is not supported by this panel`: esp_lvgl_port asks
  the EK79007; nothing breaks.
$sections