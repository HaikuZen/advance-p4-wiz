# Cookbook: a new ESP-IDF 6.x application for the Elecrow CrowPanel Advanced P4

Step-by-step instructions for scaffolding a **brand-new** ESP-IDF 6.x project
for the Elecrow **CrowPanel Advanced 7" / 10.1"** (ESP32-P4, hardware
**V1.2**). The result is a minimal, complete skeleton with:

- the panel up: 1024 x 600, EK79007 over 2-lane MIPI-DSI, no tearing;
- GT911 touch;
- LVGL 9 running in its own task;
- a PWM backlight with brightness control;
- a demo screen that checks colours and touch.

Optional sections add **Wi-Fi** through the onboard ESP32-C6, the
**speaker**, an **AI** demo (handwritten digits with ESP-DL) and, in step 15, a
**BME690** environment sensor on the I2C connector, and in step 16 the **PDM
microphone**. Step 14
covers growing the skeleton into a real app: memory, tasks, LVGL, HTTPS, the
microSD card, JPEG, testing. It comes from building ArtShow on this board.

**Status (2026-10-18):**
- **Built on ESP-IDF v6.1:** every file in this cookbook, including both Wi-Fi
  options and the audio snippet, compiles with no warnings.
- **Flashed once** from a 6.x build (2026-10-18, base + the AI module): it boots,
  the panel, touch and AI demo run. That first boot found the DSI clock bug in
  step 13's table. Colours and touch alignment checked right by eye; tearing
  and backlight dimming not yet reported.
- **Where the board values come from:** this repository's working port of the
  same board (`firmware/main/display_port_dsi.c`, `docs/board-crowpanel-p4.md`).
  That port runs on the bench 10.1" on IDF 5.4.1. The pins, panel timings, DSI
  lane rate, LDO, backlight and GT911 settings are proven there, including the
  colours and touch orientation on the screen. The IDF 6.x parts (the
  chip-revision options, renamed driver fields, component versions) are verified
  by build only.
- **Before calling it done:** go through step 9 on the real board.

## 0. Before you start

- **ESP-IDF 6.x** (built against v6.1). Target `esp32p4`.
- **Which USB socket:** use the one labelled **UART**. It goes through a CH340
  to the P4's UART0 (GPIO 37 / 38) and carries flashing and the console. The
  P4's own USB socket is not used here; under Elecrow's factory firmware it
  shows up as an HID device (303a:4004).
- **Query the chip** rather than trusting this page:
  ```sh
  esptool.py --port /dev/ttyUSBx --baud 460800 flash_id
  ```
  The bench board reports ESP32-P4 **rev v1.3**, 16 MB flash and 32 MB PSRAM.
  The chip revision matters a lot on IDF 6.x (step 3).
- **Back up the factory firmware first** if you may want Elecrow's demo back:
  ```sh
  esptool.py --port /dev/ttyUSBx --baud 460800 read_flash 0 0x1000000 crowp4-factory.bin
  ```
  Use **460800 baud**. At 921600 this board's CH340 dropped bytes during a full
  read. To restore: `esptool.py write_flash 0 crowp4-factory.bin`.
- **Avoid project paths containing `[` or `]`.** CMake's `file(GLOB_RECURSE)`,
  which the LVGL component uses, returns nothing under such paths. The build
  then fails with an error that doesn't point at the real cause.

### The board at a glance

| | |
|---|---|
| chip | ESP32-P4 rev v1.x, 360 MHz max, 32 MB hex PSRAM at 200 MHz, 16 MB flash |
| panel | 1024 x 600 IPS, EK79007, MIPI-DSI 2 lanes x 900 Mbps, DPI 51 MHz (~56 Hz) |
| D-PHY supply | the P4's internal LDO3 at 2.5 V (Elecrow's code also takes LDO4 at 3.3 V) |
| backlight | GPIO 31 into an MT9201, LEDC PWM 30 kHz, 11-bit, lit from duty ~200 / 2047; flickers below ~25 % (step 14.4) |
| touch | GT911 at 0x5d: SDA 45, SCL 46, INT 42, RST 40 |
| other I2C | 0x2f: an STC8 battery helper. **No ES8311**, despite the schematic (see step 11) |
| audio | plain I2S, no codec: BCLK 22, WS 21, DOUT 23, no MCLK; amps enable GPIO 30 **active low**. On I2S0; on I2S1 with the mic (step 16) |
| microphone | PDM, clock GPIO 24, data GPIO 26, the left slot; on I2S0, the only PDM RX port (step 16) |
| Wi-Fi | ESP32-C6 over 4-bit SDIO: CLK 18, CMD 19, D0..D3 17 / 16 / 15 / 14, C6 enable GPIO 32 |
| microSD | SDMMC **slot 0**, 1-bit: CLK 43, CMD 44, D0 39; IO from LDO4 at 3.3 V. Shares the SDMMC host with the C6 (step 14.6) |
| USB | J16 is the P4's high-speed USB OTG. **VBUS is an input only** (diodes): no 5 V out, so a device must be self-powered or on a powered hub |
| memory | ~500 KB internal RAM, the scarce one (step 14.2); 32 MB PSRAM |
| keys | BOOT is **GPIO 35** (GPIO 0 / 1 are the 32 kHz crystal); RESET |
| panel reset | GPIO 41 is wired, but leave it alone (Elecrow's driver does) |

## 1. Project skeleton

```sh
idf.py create-project my_p4_app
cd my_p4_app
idf.py set-target esp32p4
rm main/my_p4_app.c          # replaced by main.c + board.c below
```

The generated root `CMakeLists.txt` needs no change:

```cmake
cmake_minimum_required(VERSION 3.22)
include($ENV{IDF_PATH}/tools/cmake/project.cmake)
project(my_p4_app)
```

## 2. Dependencies: `main/idf_component.yml`

This file goes in `main/`, not the project root. A manifest at the root is never
read by the build, and nothing warns you.

```yaml
dependencies:
  idf: ">=6.0"
  espressif/esp_lcd_ek79007: "^2.0.2"       # EK79007 MIPI-DSI panel controller
  espressif/esp_lcd_touch_gt911: "^1.2.1"   # GT911 touch
  espressif/esp_lvgl_port: "^2.9.0"
  lvgl/lvgl: "^9.6.0"
```

These are the versions the IDF 6.1 resolver picked and this cookbook was built
against. The tank's IDF 5.4 build uses `esp_lcd_ek79007` 1.0.4; 2.x is the
line for IDF 6.

## 3. `sdkconfig.defaults`

```
# Elecrow CrowPanel Advanced 7" / 10.1" (V1.2), ESP32-P4 - IDF 6.x
CONFIG_IDF_TARGET="esp32p4"

# The board's P4 is rev v1.x. IDF 6.x builds for rev >= 3.1 by default, and
# such an image REFUSES TO BOOT on a v1.x chip. Rev <3 and >=3 are exclusive.
CONFIG_ESP32P4_SELECTS_REV_LESS_V3=y
CONFIG_ESP32P4_REV_MIN_100=y
CONFIG_ESP_DEFAULT_CPU_FREQ_MHZ_360=y

# 16 MB flash, 32 MB hex PSRAM at 200 MHz (confirm with esptool flash_id)
CONFIG_ESPTOOLPY_FLASHSIZE_16MB=y
CONFIG_SPIRAM=y
CONFIG_SPIRAM_SPEED_200M=y
CONFIG_PARTITION_TABLE_SINGLE_APP_LARGE=y

# console on UART0 (GPIO 37/38) = the board's CH340, the "UART" USB socket
CONFIG_ESP_CONSOLE_UART_DEFAULT=y
CONFIG_ESP_CONSOLE_SECONDARY_NONE=y

# LVGL 9
CONFIG_LV_COLOR_DEPTH_16=y
CONFIG_LV_FONT_MONTSERRAT_14=y
CONFIG_LV_FONT_MONTSERRAT_24=y
CONFIG_LV_FONT_MONTSERRAT_32=y
```

Notes:
- **The chip revision is the main IDF 6.x pitfall.** Without the first two
  `ESP32P4_*` lines, the build succeeds, but the bootloader refuses to start the
  app on this board's rev v1.3 chip. On a future board with a rev v3.x P4, do the
  opposite: drop those lines. That chip can then run at 400 MHz and its PSRAM at
  250 MHz.
- **PSRAM at 200 MHz** is the default on 6.x. On IDF 5.4 it was behind
  `CONFIG_IDF_EXPERIMENTAL_FEATURES`, with 20 MHz otherwise. The panel streams
  ~69 MB/s out of PSRAM (1024 x 600 x 2 bytes, 56 times a second), so a slow
  PSRAM shows on the screen.
- LVGL only compiles in the fonts enabled here. The built-in Montserrat fonts
  are ASCII only (step 14.4).
- A bigger app needs more lines (TLS buffers in PSRAM, the PPA, FAT names, a
  bigger partition): step 14.1.
- After editing this file, delete the generated `sdkconfig` and rebuild. Don't
  hand-edit the generated file.

## 4. Pins: `main/board_pins.h`

```c
#pragma once
/* Elecrow CrowPanel Advanced 7" / 10.1", hardware V1.2 (ESP32-P4) */
#define LCD_H_RES        1024
#define LCD_V_RES        600
#define PIN_LCD_BL       31     /* LCD_BK_EN -> MT9201 backlight driver, PWM */
#define PIN_LCD_RST      41     /* wired, but leave it alone (reset_gpio_num = -1) */
#define PIN_TP_SDA       45
#define PIN_TP_SCL       46
#define PIN_TP_RST       40
#define PIN_TP_INT       42
#define PIN_AMP_SD       30     /* speaker amps enable, ACTIVE LOW, 10k pull-up */
#define PIN_I2S_BCLK     22
#define PIN_I2S_WS       21
#define PIN_I2S_DOUT     23
#define PIN_MIC_CLK      24     /* PDM microphone, left slot (seen on the bench board) */
#define PIN_MIC_DATA     26
#define PIN_BOOT_KEY     35     /* BOOT button (GPIO 0/1 are the 32 kHz crystal) */
#define PIN_C6_EN        32     /* ESP32-C6 (Wi-Fi) enable */
#define LDO_CHAN_DSI_PHY 3      /* P4 internal LDO3 at 2.5 V feeds the MIPI D-PHY */
#define LDO_MV_DSI_PHY   2500
```

Elecrow's V1.0 / V1.1 / V1.2 boards differ only in the pins of the plug-in
radio modules (LoRa, nRF24), which this scaffold does not use.

## 5. Board bring-up: `main/board.h` and `main/board.c`

### `main/board.h`

```c
#pragma once
#include "driver/i2c_master.h"

/* power, I2C, backlight, panel, touch and the LVGL task; call once from app_main */
void board_init(void);
/* backlight 0..100 % (0 = off) */
void board_set_brightness(int pct);
/* the shared I2C bus (GT911 at 0x5d, the STC8 helper at 0x2f) */
i2c_master_bus_handle_t board_i2c_bus(void);
```

### `main/board.c`

The bring-up order matters:
1. Turn the amps off and start I2C.
2. Start the backlight PWM at duty 0, so the screen stays dark until the first
   frame.
3. Turn on the **LDO3 2.5 V D-PHY supply before creating the DSI bus**.
4. Set up the panel, then touch, then LVGL.

```c
/* board.c - Elecrow CrowPanel Advanced 7" / 10.1" (V1.2, ESP32-P4), IDF 6.x:
 * power, I2C, backlight, the EK79007 MIPI-DSI panel, the GT911 touch, LVGL. */
#include "board.h"
#include "board_pins.h"
#include "driver/gpio.h"
#include "driver/i2c_master.h"
#include "driver/ledc.h"
#include "esp_ldo_regulator.h"
#include "esp_lcd_mipi_dsi.h"
#include "esp_lcd_panel_ops.h"
#include "esp_lcd_panel_io.h"
#include "esp_lcd_ek79007.h"
#include "esp_lcd_touch_gt911.h"
#include "esp_lvgl_port.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include <stdio.h>

static const char *TAG = "board";

#define DSI_LANES      2
#define DSI_LANE_MBPS  900    /* Elecrow's verified values (Lesson07, V1.2) */
#define DPI_CLK_MHZ    51     /* 1414 x 645 per frame with porches: ~56 Hz */
/* the D-PHY PLL reference: IDF 6's _DEFAULT is XTAL, which only rev >= 3.0 has;
   a rev v1.x chip abort()s on it inside esp_lcd_new_dsi_bus. PLL_F20M for v1.x */
#if CONFIG_ESP32P4_SELECTS_REV_LESS_V3
#define DSI_PHY_CLK    MIPI_DSI_PHY_PLLREF_CLK_SRC_DEFAULT_LEGACY
#else
#define DSI_PHY_CLK    MIPI_DSI_PHY_PLLREF_CLK_SRC_DEFAULT
#endif
#define BL_PWM_HZ      30000
#define BL_DUTY_BITS   LEDC_TIMER_11_BIT
#define BL_DUTY_FLOOR  200    /* of 2047: below it the MT9201 barely lights */

static i2c_master_bus_handle_t s_i2c;
static esp_lcd_panel_handle_t s_panel;
static esp_lcd_touch_handle_t s_touch;

i2c_master_bus_handle_t board_i2c_bus(void) { return s_i2c; }

static void ldo_up(int chan, int mv) {
    esp_ldo_channel_handle_t h;
    const esp_ldo_channel_config_t c = { .chan_id = chan, .voltage_mv = mv };
    ESP_ERROR_CHECK(esp_ldo_acquire_channel(&c, &h));   /* kept for the app's lifetime */
}

static void i2c_init(void) {
    const i2c_master_bus_config_t bus = {
        .i2c_port = I2C_NUM_0, .sda_io_num = PIN_TP_SDA, .scl_io_num = PIN_TP_SCL,
        .clk_source = I2C_CLK_SRC_DEFAULT, .glitch_ignore_cnt = 7,
        .flags.enable_internal_pullup = 1,
    };
    ESP_ERROR_CHECK(i2c_new_master_bus(&bus, &s_i2c));
    /* who answers - the first bring-up question. A V1.2 10.1" shows 0x5d (GT911)
       and 0x2f (STC8 battery helper); no ES8311 despite the schematic */
    char seen[96] = ""; int n = 0;
    for (int a = 0x08; a < 0x78 && n < (int)sizeof seen - 6; a++)
        if (i2c_master_probe(s_i2c, a, 20) == ESP_OK) n += snprintf(seen + n, sizeof seen - n, " 0x%02x", a);
    ESP_LOGI(TAG, "I2C scan:%s", n ? seen : " nothing answered");
}

static void backlight_init(void) {
    const ledc_timer_config_t tc = { .speed_mode = LEDC_LOW_SPEED_MODE, .duty_resolution = BL_DUTY_BITS,
                                     .timer_num = LEDC_TIMER_0, .freq_hz = BL_PWM_HZ, .clk_cfg = LEDC_AUTO_CLK };
    const ledc_channel_config_t cc = { .gpio_num = PIN_LCD_BL, .speed_mode = LEDC_LOW_SPEED_MODE,
                                       .channel = LEDC_CHANNEL_0, .timer_sel = LEDC_TIMER_0, .duty = 0 };
    ESP_ERROR_CHECK(ledc_timer_config(&tc));
    ESP_ERROR_CHECK(ledc_channel_config(&cc));   /* dark until the first frame is in */
}

void board_set_brightness(int pct) {
    uint32_t duty = pct <= 0 ? 0 : BL_DUTY_FLOOR + (uint32_t)(pct > 100 ? 100 : pct) * (2047 - BL_DUTY_FLOOR) / 100;
    ledc_set_duty(LEDC_LOW_SPEED_MODE, LEDC_CHANNEL_0, duty);
    ledc_update_duty(LEDC_LOW_SPEED_MODE, LEDC_CHANNEL_0);
}

/* the speaker amps off from the start: active LOW enable, pulled up on the board */
static void amp_off(void) {
    const gpio_config_t g = { .pin_bit_mask = 1ULL << PIN_AMP_SD, .mode = GPIO_MODE_OUTPUT };
    gpio_config(&g);
    gpio_set_level(PIN_AMP_SD, 1);
}

static void panel_init(void) {
    ldo_up(LDO_CHAN_DSI_PHY, LDO_MV_DSI_PHY);   /* the D-PHY's supply, before the bus */
    ldo_up(4, 3300);                            /* Elecrow's examples take LDO4 too */

    esp_lcd_dsi_bus_handle_t bus;
    const esp_lcd_dsi_bus_config_t bc = { .bus_id = 0, .num_data_lanes = DSI_LANES,
                                          .phy_clk_src = DSI_PHY_CLK,
                                          .lane_bit_rate_mbps = DSI_LANE_MBPS };
    ESP_ERROR_CHECK(esp_lcd_new_dsi_bus(&bc, &bus));

    esp_lcd_panel_io_handle_t dbi;
    const esp_lcd_dbi_io_config_t dc = { .virtual_channel = 0, .lcd_cmd_bits = 8, .lcd_param_bits = 8 };
    ESP_ERROR_CHECK(esp_lcd_new_panel_io_dbi(bus, &dc, &dbi));

    const esp_lcd_dpi_panel_config_t dpi = {
        .virtual_channel = 0,
        .dpi_clk_src = MIPI_DSI_DPI_CLK_SRC_DEFAULT,
        .dpi_clock_freq_mhz = DPI_CLK_MHZ,
        .in_color_format = LCD_COLOR_FMT_RGB565,   /* IDF 6.x; 5.x called it .pixel_format */
        .num_fbs = 2,                              /* LVGL draws into these (avoid_tearing) */
        .video_timing = {
            .h_size = LCD_H_RES, .v_size = LCD_V_RES,
            .hsync_back_porch = 160, .hsync_pulse_width = 70, .hsync_front_porch = 160,
            .vsync_back_porch = 23, .vsync_pulse_width = 10, .vsync_front_porch = 12,
        },
    };
    const ek79007_vendor_config_t vendor = {
        .mipi_config = { .dsi_bus = bus, .dpi_config = &dpi, .lane_num = DSI_LANES },
    };
    const esp_lcd_panel_dev_config_t pc = {
        .reset_gpio_num = -1,                      /* GPIO 41 is wired; Elecrow's driver leaves it alone */
        .rgb_ele_order = LCD_RGB_ELEMENT_ORDER_RGB,
        .bits_per_pixel = 16,
        .vendor_config = (void *)&vendor,
    };
    ESP_ERROR_CHECK(esp_lcd_new_panel_ek79007(dbi, &pc, &s_panel));
    ESP_ERROR_CHECK(esp_lcd_panel_reset(s_panel));
    ESP_ERROR_CHECK(esp_lcd_panel_init(s_panel));   /* the video stream starts here */
}

static void touch_init(void) {
    esp_lcd_panel_io_handle_t io;
    esp_lcd_panel_io_i2c_config_t io_cfg = ESP_LCD_TOUCH_IO_I2C_GT911_CONFIG();
    io_cfg.scl_speed_hz = 400000;
    ESP_ERROR_CHECK(esp_lcd_new_panel_io_i2c(s_i2c, &io_cfg, &io));
    /* driver_data naming the address makes the driver run the GT911's address
       latch (INT driven during reset); without it the reads can fail every boot */
    static esp_lcd_touch_io_gt911_config_t addr = { .dev_addr = ESP_LCD_TOUCH_IO_I2C_GT911_ADDRESS };
    const esp_lcd_touch_config_t tp = {
        .x_max = LCD_H_RES, .y_max = LCD_V_RES,
        .rst_gpio_num = PIN_TP_RST, .int_gpio_num = PIN_TP_INT,
        .levels = { .reset = 0, .interrupt = 0 },
        .flags = { .swap_xy = 0, .mirror_x = 0, .mirror_y = 0 },   /* right on the bench board */
        .driver_data = &addr,
    };
    esp_err_t err = ESP_FAIL;
    for (int i = 1; i <= 5 && err != ESP_OK; i++) {
        err = esp_lcd_touch_new_i2c_gt911(io, &tp, &s_touch);
        if (err != ESP_OK) { ESP_LOGW(TAG, "GT911 attempt %d: %s", i, esp_err_to_name(err)); s_touch = NULL; vTaskDelay(pdMS_TO_TICKS(250)); }
    }
    if (err != ESP_OK) ESP_LOGE(TAG, "no GT911: running without touch");
    else ESP_LOGI(TAG, "GT911 ready");
}

static void lvgl_init(void) {
    const lvgl_port_cfg_t lc = ESP_LVGL_PORT_INIT_CONFIG();
    ESP_ERROR_CHECK(lvgl_port_init(&lc));
    const lvgl_port_display_cfg_t dc = {
        .panel_handle = s_panel,
        .buffer_size = LCD_H_RES * LCD_V_RES,      /* full screen: the panel's own buffers */
        .double_buffer = true,
        .hres = LCD_H_RES, .vres = LCD_V_RES,
        .color_format = LV_COLOR_FORMAT_RGB565,
        .flags = { .buff_spiram = true, .direct_mode = true },
    };
    const lvgl_port_display_dsi_cfg_t dsi = { .flags = { .avoid_tearing = true } };
    lv_display_t *disp = lvgl_port_add_disp_dsi(&dc, &dsi);
    if (!disp) { ESP_LOGE(TAG, "lvgl_port_add_disp_dsi failed"); abort(); }
    if (s_touch) {
        const lvgl_port_touch_cfg_t tc = { .disp = disp, .handle = s_touch };
        if (!lvgl_port_add_touch(&tc)) ESP_LOGE(TAG, "lvgl_port_add_touch failed");
    }
}

void board_init(void) {
    amp_off();
    i2c_init();
    backlight_init();
    panel_init();
    touch_init();
    lvgl_init();
    board_set_brightness(80);
    ESP_LOGI(TAG, "CrowPanel P4 up: %dx%d, %d lanes x %d Mbps, %d MHz dpi", LCD_H_RES, LCD_V_RES, DSI_LANES, DSI_LANE_MBPS, DPI_CLK_MHZ);
}
```

Why it's written this way:
- **No tearing:** `avoid_tearing` + `direct_mode` + `num_fbs = 2`. LVGL draws
  straight into the panel driver's two PSRAM frame buffers, and esp_lvgl_port
  swaps them at the end of a frame (`on_frame_buf_complete` on IDF ≥ 5.5). With
  `avoid_tearing`, `direct_mode` (or `full_refresh`) is required. Without it,
  the two buffers drift apart on partial redraws, and the screen flips between
  old and new content.
- **Timings:** Elecrow's V1.2 Lesson07 values: HSYNC 70 / 160 / 160 and VSYNC
  10 / 23 / 12 at 51 MHz. They differ from `EK79007_1024_600_PANEL_60HZ_CONFIG`
  in the component, which gives 52 MHz with a 10 / 1 sync pulse. Stick with the
  board's values.
- **Touch orientation:** with `swap_xy` / `mirror_*` all 0, taps land under the
  finger on the bench 10.1". Confirm on yours (step 9).

## 6. Demo app: `main/main.c`

The demo has:
- a title;
- red / green / blue bars, to check the colour order;
- a dot that follows the finger, with live coordinates;
- a brightness slider.

```c
/* main.c - CrowPanel P4 scaffold: a title, a dot that follows the finger,
 * live coordinates, and a brightness slider. */
#include "board.h"
#include "esp_lvgl_port.h"
#include "esp_log.h"

static const char *TAG = "app";
static lv_obj_t *s_coords, *s_dot;

static void touch_cb(lv_event_t *e) {
    lv_indev_t *indev = lv_indev_active();
    if (!indev) return;
    lv_point_t p;
    lv_indev_get_point(indev, &p);
    lv_label_set_text_fmt(s_coords, "Touch: %d, %d", (int)p.x, (int)p.y);
    lv_obj_set_pos(s_dot, p.x - 12, p.y - 12);
    lv_obj_set_hidden(s_dot, false);
}

static void slider_cb(lv_event_t *e) {
    board_set_brightness(lv_slider_get_value(lv_event_get_target(e)));
}

static void build_ui(void) {
    lv_obj_t *scr = lv_screen_active();
    lv_obj_set_style_bg_color(scr, lv_color_hex(0x0D1B2A), 0);
    lv_obj_set_scrollable(scr, false);

    lv_obj_t *title = lv_label_create(scr);
    lv_label_set_text(title, "CrowPanel P4 - IDF 6 + LVGL 9");
    lv_obj_set_style_text_color(title, lv_color_hex(0x00C8FF), 0);
    lv_obj_set_style_text_font(title, &lv_font_montserrat_32, 0);
    lv_obj_align(title, LV_ALIGN_TOP_MID, 0, 30);

    /* three bars: red, green, blue - if red and blue swap, the color order is wrong */
    static const uint32_t rgb[3] = { 0xFF0000, 0x00FF00, 0x0000FF };
    for (int i = 0; i < 3; i++) {
        lv_obj_t *bar = lv_obj_create(scr);
        lv_obj_set_size(bar, 160, 60);
        lv_obj_set_style_bg_color(bar, lv_color_hex(rgb[i]), 0);
        lv_obj_set_style_border_width(bar, 0, 0);
        lv_obj_align(bar, LV_ALIGN_TOP_MID, (i - 1) * 180, 100);
    }

    s_coords = lv_label_create(scr);
    lv_label_set_text(s_coords, "Touch: --, --");
    lv_obj_set_style_text_color(s_coords, lv_color_hex(0xE0F0FF), 0);
    lv_obj_set_style_text_font(s_coords, &lv_font_montserrat_24, 0);
    lv_obj_align(s_coords, LV_ALIGN_CENTER, 0, 0);

    lv_obj_t *slider = lv_slider_create(scr);
    lv_obj_set_width(slider, 600);
    lv_slider_set_range(slider, 5, 100);
    lv_slider_set_value(slider, 80, LV_ANIM_OFF);
    lv_obj_align(slider, LV_ALIGN_BOTTOM_MID, 0, -60);
    lv_obj_add_event_cb(slider, slider_cb, LV_EVENT_VALUE_CHANGED, NULL);

    s_dot = lv_obj_create(scr);
    lv_obj_remove_style_all(s_dot);
    lv_obj_set_size(s_dot, 24, 24);
    lv_obj_set_style_radius(s_dot, LV_RADIUS_CIRCLE, 0);
    lv_obj_set_style_bg_color(s_dot, lv_color_hex(0xFF6B35), 0);
    lv_obj_set_style_bg_opa(s_dot, LV_OPA_COVER, 0);
    lv_obj_set_hidden(s_dot, true);
    lv_obj_set_ignore_layout(s_dot, true);

    lv_obj_add_event_cb(scr, touch_cb, LV_EVENT_PRESSED, NULL);
    lv_obj_add_event_cb(scr, touch_cb, LV_EVENT_PRESSING, NULL);
}

void app_main(void) {
    ESP_LOGI(TAG, "CrowPanel P4 scaffold");
    board_init();
    if (lvgl_port_lock(0)) {   /* every LVGL call from outside the LVGL task holds the lock */
        build_ui();
        lvgl_port_unlock();
    }
}
```

LVGL 9.6 deprecates `lv_obj_add_flag` / `lv_obj_remove_flag` in favour of one
setter per flag (`lv_obj_set_hidden`, `lv_obj_set_scrollable`,
`lv_obj_set_ignore_layout`, ...). Older LVGL 9.x has only the flag calls. If
the resolver picks an older LVGL, switch back to those.

## 7. `main/CMakeLists.txt`

```cmake
idf_component_register(SRCS "main.c" "board.c"
                       INCLUDE_DIRS "."
                       REQUIRES esp_lcd esp_driver_i2c esp_driver_ledc esp_driver_gpio esp_hw_support)
```

IDF 6.x splits the old `driver` component into `esp_driver_*` components.
Listing them makes the build fail clearly if one goes missing.
`esp_ldo_regulator.h` comes from `esp_hw_support`.

## 8. Build, flash, monitor

```sh
idf.py build
idf.py -p /dev/ttyUSBx -b 460800 flash monitor
```

Use the board's **UART** socket. Flashing **replaces Elecrow's factory
firmware**; restore it from the step 0 backup if needed. The app, partition
table and bootloader all change. Exit the monitor with `Ctrl+]`.

**Check that the build succeeded before flashing**: after a failed build,
`flash` writes the previous binary, and the test runs on old code. The same
goes for scripts that chain `build flash` (step 14.10).

## 9. Verify on the board

1. **Boot log:**
   - the bootloader accepts the image. If it complains about the chip revision,
     you're missing step 3's `ESP32P4_SELECTS_REV_LESS_V3`.
   - PSRAM shows 32 MB at 200 MHz;
   - `I2C scan: 0x2f 0x5d`;
   - `GT911 ready`;
   - `CrowPanel P4 up`;
   - no panic or reset loop.
2. **Colours:** the three bars read red, green, blue, left to right. If red and
   blue are swapped, change `rgb_ele_order` to `LCD_RGB_ELEMENT_ORDER_BGR`.
3. **A steady picture:** no flicker or page-flipping while you drag the slider.
   If it flips between old and new content, check `direct_mode` and
   `avoid_tearing` (step 5). If it rolls or shifts, check the timings, the DPI
   clock and the PSRAM speed.
4. **Touch:** touch all four corners and the centre. The dot must land under the
   finger. If an axis is mirrored or swapped, change `mirror_x` / `mirror_y` /
   `swap_xy` in `touch_init`.
5. **Backlight:** the slider dims the panel smoothly, and it stays lit at the
   low end. ArtShow saw flicker below ~25 % (step 14.4): look for it on a
   white screen.
6. **Harmless lines** in the log: `W gpio: conflict found for GPIO[42]` (the
   GT911 INT pin; touch works) and `E lcd_panel: swap_xy is not supported by
   this panel` (esp_lvgl_port asks the EK79007). With Wi-Fi, also
   `CONFIG_FREERTOS_HZ is 100, ESP-Hosted recommended 1000`: Wi-Fi works at 100.

## 10. Optional: Wi-Fi through the ESP32-C6

The P4 has no radio. The board's **ESP32-C6** runs Espressif's **esp_hosted**
co-processor firmware and talks to the P4 over 4-bit SDIO. On the P4,
`esp_wifi_remote` provides the normal `esp_wifi_*` API and forwards it to the
C6, so application code looks the same as on an S3.

**Decide the esp_hosted version first.** Elecrow ships the C6 with esp_hosted
**2.12.3** firmware. Espressif's guidance is to run the **same** version on
host and co-processor. On IDF 6.1 the resolver offers both lines:

| | host on the P4 | works with the C6 as shipped? | settings |
|---|---|---|---|
| **A (recommended)** | esp_hosted **2.12.x** (2.12.13) + esp_wifi_remote **1.6.3** | same major version as the C6. This pair is what the IDF 5.4 tank port uses. | 2.x option names (below) |
| **B** | esp_hosted **3.x** (3.0.9) + esp_wifi_remote 1.6.5 | esp_hosted 3.x's migration guide says a 3.x host is **back-compatible** with a 2.x co-processor, but recommends upgrading the C6 to 3.x | **renamed** 3.x option names |

Both build cleanly on IDF 6.1 with the pins below. **Option A's scan works on
the bench board from a 6.x build** (2026-10-18: the C6 identified, 8 networks
listed); neither option has joined a network yet. The tank's IDF 5.4 port boots esp_hosted
2.12 against the C6 but hasn't joined a network either. Wi-Fi is the most
likely place for this cookbook to need corrections.

Upgrading the C6 to 3.x is possible: the host can OTA it over the existing link
with `esp_hosted_slave_ota_*`. Elecrow's 2.12.3 image can't be restored from
anything in this repository, so take that step only on purpose.

**Pitfall: esp_hosted 3.x renamed all its options.** A 3.x build given
the 2.x names (from the tank's `sdkconfig.crowp4` or from Elecrow's examples)
**still builds successfully**. It silently falls back to defaults:
- data lines D0..D3 on 14..17, reversed from this board's 17..14;
- the C6 reset on GPIO 54 instead of 32.

Only "unknown kconfig symbol" notes in the build log show that anything is
wrong. After configuring, check `sdkconfig` for the pin values.

### Dependencies (add to `main/idf_component.yml`)

Option A:

```yaml
  espressif/esp_hosted:
    version: "~2.12.3"
    rules:
      - if: "target == esp32p4"
  espressif/esp_wifi_remote:
    version: "1.6.3"            # the last esp_wifi_remote that keeps esp_hosted < 3.0
    rules:
      - if: "target == esp32p4"
```

(Option B: `version: "^3.0"` for esp_hosted and leave esp_wifi_remote unpinned.)

### `sdkconfig.defaults`, option A (esp_hosted 2.12.x)

```
CONFIG_ESP_WIFI_REMOTE_LIBRARY_HOSTED=y
CONFIG_SLAVE_IDF_TARGET_ESP32C6=y
CONFIG_ESP_HOSTED_SDIO_HOST_INTERFACE=y
CONFIG_ESP_HOSTED_SDIO_4_BIT_BUS=y
# slot 1, GPIO-matrixed: the pins go in the PRIV_..._SLOT_1 symbols
# (the plain ESP_HOSTED_SDIO_PIN_* follow them). The P4 default has D0..D3 reversed.
CONFIG_ESP_HOSTED_SDIO_SLOT_1=y
CONFIG_ESP_HOSTED_PRIV_SDIO_PIN_CLK_SLOT_1=18
CONFIG_ESP_HOSTED_PRIV_SDIO_PIN_CMD_SLOT_1=19
CONFIG_ESP_HOSTED_PRIV_SDIO_PIN_D0_SLOT_1=17
CONFIG_ESP_HOSTED_PRIV_SDIO_PIN_D1_4BIT_BUS_SLOT_1=16
CONFIG_ESP_HOSTED_PRIV_SDIO_PIN_D2_4BIT_BUS_SLOT_1=15
CONFIG_ESP_HOSTED_PRIV_SDIO_PIN_D3_4BIT_BUS_SLOT_1=14
CONFIG_ESP_HOSTED_SDIO_GPIO_RESET_SLAVE=32
# esp_hosted starts from a C constructor, before most of internal RAM is in the
# heap; with its buffers and stacks in internal RAM the tank's boot aborted
# ("Not enough memory to create timer task"). Put them in PSRAM:
CONFIG_ESP_HOSTED_MEMPOOL_PREFER_SPIRAM=y
CONFIG_ESP_HOSTED_DFLT_TASK_FROM_SPIRAM=y
```

### `sdkconfig.defaults`, option B (esp_hosted 3.x names)

```
CONFIG_ESP_WIFI_REMOTE_LIBRARY_HOSTED=y
CONFIG_SLAVE_IDF_TARGET_ESP32C6=y
CONFIG_ESP_HOSTED_SDIO_SLOT_1=y
CONFIG_ESP_HOSTED_HOST_SDIO_BUS_WIDTH_4=y
CONFIG_ESP_HOSTED_HOST_SDIO_PIN_CLK=18
CONFIG_ESP_HOSTED_HOST_SDIO_PIN_CMD=19
CONFIG_ESP_HOSTED_HOST_SDIO_PIN_D0=17
CONFIG_ESP_HOSTED_HOST_SDIO_PIN_D1=16
CONFIG_ESP_HOSTED_HOST_SDIO_PIN_D2=15
CONFIG_ESP_HOSTED_HOST_SDIO_PIN_D3=14
CONFIG_ESP_HOSTED_HOST_RESET_GPIO=32
# its transport buffers and task stacks in PSRAM (2.x: MEMPOOL_PREFER_SPIRAM)
CONFIG_EH_HOST_PORT_DMA_PREFER_SPIRAM=y
CONFIG_ESP_HOSTED_DFLT_TASK_FROM_SPIRAM=y
```

### `main/wifi.c`: one task for Wi-Fi

Every `esp_wifi_*` call is an RPC to the C6, and a scan blocks for ~2.5 s, so
one task does them all. The UI and the event handlers post it messages. It
scans once for the log, joins the network saved on screen (NVS) or else the
menuconfig one, and rejoins after each drop with a backoff.

```c
/* wifi.c - Wi-Fi through the onboard ESP32-C6 (esp_hosted): the plain
 * esp_wifi API, forwarded to the C6 over SDIO by esp_wifi_remote.
 * One task owns every esp_wifi call (each is an RPC to the C6): it scans, joins
 * the network saved on screen (NVS) or else the menuconfig one, and rejoins
 * after each drop. Everyone else just posts it a message. */
#include "wifi.h"
#include "esp_wifi.h"
#include "esp_netif.h"
#include "esp_event.h"
#include "nvs_flash.h"
#include "nvs.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
#include "freertos/task.h"
#include <stdio.h>
#include <string.h>

#define NVS_NS "p4wifi"   /* the network saved from the screen */

static const char *TAG = "wifi";

typedef enum { M_SCAN, M_JOIN, M_FORGET, M_DROPPED, M_GOT_IP } msg_kind_t;
typedef struct {
    msg_kind_t kind;
    wifi_scan_cb_t scan_cb;
    int reason;
    esp_ip4_addr_t ip;
    char ssid[33], pass[65];
} msg_t;

static QueueHandle_t s_q;
static wifi_status_cb_t s_status_cb;
static volatile bool s_connected;
/* the Wi-Fi task's own state */
static char s_ssid[33], s_pass[65];
static bool s_have, s_save, s_leaving, s_retry;
static int s_tries;
static TickType_t s_retry_at;

/* a failed step logs and gives up on Wi-Fi only: the rest of the app keeps
   running. The C6 link is unproven, and ESP_ERROR_CHECK would reboot the board */
#define TRY(x) do { esp_err_t e_ = (x); \
        if (e_ != ESP_OK) { ESP_LOGE(TAG, "%s: %s - no Wi-Fi", #x, esp_err_to_name(e_)); status(WIFI_OFF, esp_err_to_name(e_)); return; } } while (0)

static void status(wifi_state_t st, const char *detail) {
    s_connected = st == WIFI_CONNECTED;
    if (s_status_cb) s_status_cb(st, s_ssid, detail ? detail : "");
}

static void post(const msg_t *m) {
    if (!s_q || xQueueSend(s_q, m, 0) != pdTRUE) ESP_LOGW(TAG, "Wi-Fi not running, or busy: dropped a request");
}

bool wifi_connected(void) { return s_connected; }
void wifi_on_status(wifi_status_cb_t cb) { s_status_cb = cb; }
void wifi_scan(wifi_scan_cb_t cb) { post(&(msg_t){ .kind = M_SCAN, .scan_cb = cb }); }
void wifi_forget(void) { post(&(msg_t){ .kind = M_FORGET }); }

void wifi_join(const char *ssid, const char *password) {
    msg_t m = { .kind = M_JOIN };
    snprintf(m.ssid, sizeof m.ssid, "%s", ssid);
    snprintf(m.pass, sizeof m.pass, "%s", password ? password : "");
    post(&m);
}

static void do_scan(wifi_scan_cb_t cb) {
    static wifi_ap_record_t ap[WIFI_MAX_NETS];
    static wifi_net_t nets[WIFI_MAX_NETS];
    uint16_t total = 0, max = WIFI_MAX_NETS;
    esp_err_t err = esp_wifi_scan_start(NULL, true);   /* blocking, ~2.5 s */
    if (err == ESP_OK) esp_wifi_scan_get_ap_num(&total);
    if (err == ESP_OK) err = esp_wifi_scan_get_ap_records(&max, ap);
    if (err != ESP_OK) {
        ESP_LOGW(TAG, "scan: %s", esp_err_to_name(err));
        if (cb) cb(NULL, -1);
        return;
    }
    int n = 0;   /* strongest first already; one entry per name, hidden ones out */
    for (int i = 0; i < max; i++) {
        const char *name = (const char *)ap[i].ssid;
        bool dup = !name[0];
        for (int j = 0; j < n && !dup; j++) dup = !strcmp(nets[j].ssid, name);
        if (dup) continue;
        snprintf(nets[n].ssid, sizeof nets[n].ssid, "%s", name);
        nets[n].rssi = ap[i].rssi;
        nets[n].open = ap[i].authmode == WIFI_AUTH_OPEN;
        n++;
    }
    ESP_LOGI(TAG, "%u networks, %d listed", total, n);
    for (int i = 0; i < n; i++) ESP_LOGI(TAG, "  %-32s rssi %d%s", nets[i].ssid, nets[i].rssi, nets[i].open ? "  (open)" : "");
    if (cb) cb(nets, n);
}

/* try again in 1, 2, 4 ... up to 30 s */
static void retry_later(int reason) {
    char detail[48];
    s_tries++;
    int wait = s_tries < 6 ? 1 << (s_tries - 1) : 30;
    s_retry = true;
    s_retry_at = xTaskGetTickCount() + pdMS_TO_TICKS(wait * 1000);
    ESP_LOGW(TAG, "not connected to \"%s\" (reason %d), retry in %d s", s_ssid, reason, wait);
    snprintf(detail, sizeof detail, "reason %d, retry in %d s", reason, wait);
    status(WIFI_RETRYING, detail);
}

static void apply_and_connect(void) {
    wifi_config_t wc = { 0 };
    memcpy(wc.sta.ssid, s_ssid, strlen(s_ssid));
    memcpy(wc.sta.password, s_pass, strlen(s_pass));
    /* with a password, refuse anything weaker than WPA2; WPA3 (SAE) works too */
    wc.sta.threshold.authmode = s_pass[0] ? WIFI_AUTH_WPA2_PSK : WIFI_AUTH_OPEN;
    wc.sta.sae_pwe_h2e = WPA3_SAE_PWE_BOTH;
    esp_err_t err = esp_wifi_set_config(WIFI_IF_STA, &wc);
    if (err == ESP_OK) err = esp_wifi_connect();
    if (err != ESP_OK) {
        ESP_LOGW(TAG, "connect: %s", esp_err_to_name(err));
        retry_later(0);   /* no reason code: the call itself failed */
        return;
    }
    ESP_LOGI(TAG, "joining \"%s\"", s_ssid);
    status(WIFI_CONNECTING, NULL);
}

static void save_network(void) {
    nvs_handle_t h;
    if (nvs_open(NVS_NS, NVS_READWRITE, &h) != ESP_OK) return;
    nvs_set_str(h, "ssid", s_ssid);
    nvs_set_str(h, "pass", s_pass);
    nvs_commit(h);
    nvs_close(h);
    ESP_LOGI(TAG, "\"%s\" saved", s_ssid);
}

static bool load_network(void) {
    nvs_handle_t h;
    if (nvs_open(NVS_NS, NVS_READONLY, &h) == ESP_OK) {
        size_t ls = sizeof s_ssid, lp = sizeof s_pass;
        bool ok = nvs_get_str(h, "ssid", s_ssid, &ls) == ESP_OK && nvs_get_str(h, "pass", s_pass, &lp) == ESP_OK;
        nvs_close(h);
        if (ok && s_ssid[0]) {
            ESP_LOGI(TAG, "network saved on screen: \"%s\"", s_ssid);
            return true;
        }
    }
    snprintf(s_ssid, sizeof s_ssid, "%s", CONFIG_APP_WIFI_SSID);   /* the menuconfig fallback */
    snprintf(s_pass, sizeof s_pass, "%s", CONFIG_APP_WIFI_PASSWORD);
    return s_ssid[0] != 0;
}

static void handle(const msg_t *m) {
    char detail[48];
    switch (m->kind) {
    case M_SCAN:
        do_scan(m->scan_cb);
        break;
    case M_JOIN:
        if (s_have) { s_leaving = true; esp_wifi_disconnect(); }
        memcpy(s_ssid, m->ssid, sizeof s_ssid);
        memcpy(s_pass, m->pass, sizeof s_pass);
        s_have = s_save = true;
        s_tries = 0;
        s_retry = false;
        apply_and_connect();
        break;
    case M_FORGET: {
        nvs_handle_t h;
        if (nvs_open(NVS_NS, NVS_READWRITE, &h) == ESP_OK) { nvs_erase_all(h); nvs_commit(h); nvs_close(h); }
        if (s_have) { s_leaving = true; esp_wifi_disconnect(); }
        s_have = s_retry = s_save = false;
        ESP_LOGI(TAG, "network forgotten");
        status(WIFI_IDLE, "forgotten");
        s_ssid[0] = 0;
        break;
    }
    case M_DROPPED:
        if (m->reason == WIFI_REASON_ASSOC_LEAVE && s_leaving) { s_leaving = false; break; }   /* our own disconnect */
        if (s_have) retry_later(m->reason);
        break;
    case M_GOT_IP:
        s_tries = 0;
        s_leaving = false;
        if (s_save) { save_network(); s_save = false; }
        snprintf(detail, sizeof detail, IPSTR, IP2STR(&m->ip));
        ESP_LOGI(TAG, "connected to \"%s\", IP %s", s_ssid, detail);
        status(WIFI_CONNECTED, detail);
        break;
    }
}

static void wifi_task(void *arg) {
    msg_t m;
    do_scan(NULL);   /* one scan for the log */
    s_have = load_network();
    if (s_have) apply_and_connect();
    else {
        ESP_LOGI(TAG, "no network set (on screen, or idf.py menuconfig > CrowPanel Wi-Fi)");
        status(WIFI_IDLE, NULL);
    }
    for (;;) {
        TickType_t wait = portMAX_DELAY;
        if (s_retry) {
            TickType_t now = xTaskGetTickCount();
            wait = (int32_t)(s_retry_at - now) > 0 ? s_retry_at - now : 0;
        }
        if (xQueueReceive(s_q, &m, wait) == pdTRUE) handle(&m);
        else { s_retry = false; apply_and_connect(); }   /* the backoff ran out */
    }
}

static void on_event(void *arg, esp_event_base_t base, int32_t id, void *data) {
    msg_t m = { 0 };
    if (base == WIFI_EVENT && id == WIFI_EVENT_STA_DISCONNECTED) {
        m.kind = M_DROPPED;
        m.reason = ((const wifi_event_sta_disconnected_t *)data)->reason;
        s_connected = false;
    } else if (base == IP_EVENT && id == IP_EVENT_STA_GOT_IP) {
        m.kind = M_GOT_IP;
        m.ip = ((const ip_event_got_ip_t *)data)->ip_info.ip;
    } else {
        return;
    }
    post(&m);
}

void wifi_start(void) {
    esp_err_t err = nvs_flash_init();
    if (err == ESP_ERR_NVS_NO_FREE_PAGES || err == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        TRY(nvs_flash_erase());
        err = nvs_flash_init();
    }
    TRY(err);
    TRY(esp_netif_init());
    TRY(esp_event_loop_create_default());
    esp_netif_create_default_wifi_sta();
    wifi_init_config_t cfg = WIFI_INIT_CONFIG_DEFAULT();
    TRY(esp_wifi_init(&cfg));
    TRY(esp_wifi_set_mode(WIFI_MODE_STA));
    TRY(esp_wifi_start());
    TRY(esp_event_handler_register(WIFI_EVENT, WIFI_EVENT_STA_DISCONNECTED, on_event, NULL));
    TRY(esp_event_handler_register(IP_EVENT, IP_EVENT_STA_GOT_IP, on_event, NULL));
    s_q = xQueueCreate(8, sizeof(msg_t));
    if (!s_q || xTaskCreate(wifi_task, "wifi", 6144, NULL, 5, NULL) != pdPASS) {
        ESP_LOGE(TAG, "no memory for the Wi-Fi task - no Wi-Fi");
        status(WIFI_OFF, "no memory");
    }
}
```

`main/wifi.h`:

```c
#pragma once
/* Wi-Fi through the C6. A Wi-Fi task does the work; every call here returns at once */
#include <stdbool.h>
#include "lvgl.h"

#define WIFI_MAX_NETS 20

typedef enum { WIFI_OFF, WIFI_IDLE, WIFI_CONNECTING, WIFI_CONNECTED, WIFI_RETRYING } wifi_state_t;
typedef struct { char ssid[33]; int rssi; bool open; } wifi_net_t;
/* both callbacks run in the Wi-Fi task: take the LVGL lock to touch the UI.
 * detail: the IP when connected, the reason when retrying */
typedef void (*wifi_status_cb_t)(wifi_state_t state, const char *ssid, const char *detail);
typedef void (*wifi_scan_cb_t)(const wifi_net_t *nets, int n);   /* n < 0: the scan failed */

/* bring up Wi-Fi, log one scan, then join the network saved on screen (NVS), else the
 * one in menuconfig (CrowPanel Wi-Fi), and rejoin after each drop */
void wifi_start(void);
bool wifi_connected(void);
/* set before wifi_start to see every change */
void wifi_on_status(wifi_status_cb_t cb);
void wifi_scan(wifi_scan_cb_t cb);
/* join this network instead; saved in NVS once it connects (a wrong password never is) */
void wifi_join(const char *ssid, const char *password);
/* drop and erase the saved network (the menuconfig one, if any, is back at the next boot) */
void wifi_forget(void);
/* the screen's Wi-Fi button and setup panel (wifi_ui.c); call holding the LVGL lock */
void wifi_ui_create(lv_obj_t *parent);
```

### `main/wifi_ui.c`: setting the network on screen

Copy it from `template/modules/wifi/wifi_ui.c` (~160 lines). It puts a status
button in the top-left corner of the demo screen. The button opens a
full-screen panel on `lv_layer_top()`:
- the scan list;
- the chosen network, a password field and an on-screen keyboard (its OK key
  connects too);
- Connect, Rescan, Forget and Close;
- a status line: connecting, connected with the IP, or why it can't join.

The callbacks from `wifi.c` run in the Wi-Fi task, so they take
`lvgl_port_lock()`. The network is saved in NVS (namespace `p4wifi`) only once
it has connected, so a mistyped password is never saved. Forget erases it.

### `main/Kconfig.projbuild`: a fallback network, in menuconfig

```
menu "CrowPanel Wi-Fi"

    config APP_WIFI_SSID
        string "Network name (SSID)"
        default ""
        help
            The network to join at boot. Empty: only scan, and join nothing.
            Set it here (idf.py menuconfig): it is kept in sdkconfig, which the
            project's .gitignore keeps out of git. Don't put it in
            sdkconfig.defaults, which is committed.

    config APP_WIFI_PASSWORD
        string "Password"
        default ""
        help
            The network's password. Empty for an open network.

endmenu
```

Then:
- add `"wifi.c" "wifi_ui.c"` to `SRCS`;
- add `esp_wifi esp_netif esp_event nvs_flash` to `REQUIRES`;
- call `wifi_ui_create(lv_screen_active())` right after `build_ui()`, inside
  the LVGL lock;
- call `wifi_start()` at the end of `app_main`. It returns at once; the Wi-Fi
  task does the rest.

### Which network it joins

1. **The one saved on screen**: tap the Wi-Fi button, pick a network, type
   the password, Connect. It's kept across reboots until you press Forget.
2. **Else, the one set in menuconfig**: `idf.py menuconfig` > **CrowPanel
   Wi-Fi** (SSID, password), then rebuild. It lives in the generated
   `sdkconfig`, which the project's `.gitignore` keeps out of git. Don't put it
   in `sdkconfig.defaults`: that file is committed.
3. **Else, none**: it only scans, and the button reads "set up".

**The password is stored in plain text** either way: one from menuconfig is
compiled into the firmware (`build/*.bin`), and one typed on screen sits in
NVS. Both end up in the board's flash, and so in any flash backup. Don't share
or upload a build or a backup made with a real password, e.g. as a release in a
public repo. Build it with the password empty for that. ESP-IDF's flash and NVS
encryption would protect the flash; this scaffold doesn't set them up.

**Check:** the boot log shows the C6 answering, the scan, then
`joining "..."` and `connected to "...", IP ...`. A failure shows as
`not connected to "..." (reason N), retry in X s`, with retries 1, 2, 4 ... up
to 30 s apart; the panel's status line shows the same. The reason codes are
`wifi_err_reason_t` in `esp_wifi_types_generic.h`: e.g. 15 = 4-way handshake
timeout and 202 = authentication failed (often a wrong password), 201 = no AP
found (wrong SSID, or out of range).

## 11. Optional: the speaker

**The schematic and the board disagree.** The 10.1" V1.2 schematic draws an
ES8311 codec at I2C 0x18. The bench board has **none**: the I2C scan finds only
0x5d and 0x2f. Elecrow's own firmware and sound lessons use plain I2S into the
speaker amplifiers, the same as on the 7". That plays cleanly on the bench
board. Don't write an ES8311 path; trust the scan.

`main/audio.c` (add `"audio.c"` to `SRCS` and `esp_driver_i2s` to `REQUIRES`):

```c
/* audio.c - the speaker: plain 16-bit I2S into the board's amps, no codec,
 * no MCLK. The amps' enable (GPIO 30) is ACTIVE LOW: low = on. */
#include "audio.h"
#include "board_pins.h"
#include "driver/i2s_std.h"
#include "driver/gpio.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include <math.h>

#define RATE 16000
static i2s_chan_handle_t s_tx;

void audio_init(void) {
    i2s_chan_config_t cc = I2S_CHANNEL_DEFAULT_CONFIG(I2S_NUM_0, I2S_ROLE_MASTER);
    ESP_ERROR_CHECK(i2s_new_channel(&cc, &s_tx, NULL));
    i2s_std_config_t sc = {
        .clk_cfg = I2S_STD_CLK_DEFAULT_CONFIG(RATE),
        .slot_cfg = I2S_STD_PHILIPS_SLOT_DEFAULT_CONFIG(I2S_DATA_BIT_WIDTH_16BIT, I2S_SLOT_MODE_STEREO),
        .gpio_cfg = { .mclk = I2S_GPIO_UNUSED, .bclk = PIN_I2S_BCLK, .ws = PIN_I2S_WS,
                      .dout = PIN_I2S_DOUT, .din = I2S_GPIO_UNUSED },
    };
    ESP_ERROR_CHECK(i2s_channel_init_std_mode(s_tx, &sc));
    ESP_ERROR_CHECK(i2s_channel_enable(s_tx));
}

void audio_beep(int hz, int ms) {
    static int16_t buf[2 * 256];                   /* stereo frames: the same sample in both slots */
    int frames = RATE * ms / 1000;
    gpio_set_level(PIN_AMP_SD, 0);                 /* amps on */
    for (int done = 0; done < frames; ) {
        int n = frames - done < 256 ? frames - done : 256;
        for (int i = 0; i < n; i++) {
            int16_t v = (int16_t)(6000 * sinf(2 * (float)M_PI * hz * (done + i) / RATE));
            buf[2 * i] = buf[2 * i + 1] = v;
        }
        size_t w;
        i2s_channel_write(s_tx, buf, n * 4, &w, portMAX_DELAY);
        done += n;
    }
    vTaskDelay(pdMS_TO_TICKS(30));                 /* let the DMA drain before the amps go off */
    gpio_set_level(PIN_AMP_SD, 1);                 /* amps off */
}
```

`main/audio.h`:

```c
#pragma once
/* plain I2S into the speaker amps (call after board_init: it owns the amp pin) */
void audio_init(void);
void audio_beep(int hz, int ms);
```

Call `audio_init(); audio_beep(880, 150);` after `board_init()`. Keep the amps
off (GPIO 30 high) whenever nothing is playing. They are on whenever the pin
is low, and an idle I2S line can hiss.

## 12. Optional: AI, handwritten digits with ESP-DL

The P4 has no separate NPU. Its "AI" is the PIE vector instructions, which
Espressif's **ESP-DL** uses to run int8 models. ESP-DL ships no digit model, so
this repository trains one: `tools/train_digit_model.py` trains a small CNN
(3 conv + 1 dense, ~27k parameters) on MNIST and exports it with **esp-ppq**
as `template/modules/ai/models/digit.espdl` (24 KB). Measured on the host:
99.0% on the MNIST test set in float, 98.35% after int8 quantization.

**The finger is not a pen.** MNIST is pen on paper; the pad gets fat finger
strokes. Two things close the gap:
- the training data is augmented: strokes dilated, small rotations, scales and
  shears;
- the board feeds the model what MNIST did to its scans (`digit_prep.c`): the
  ink cropped, scaled so its longer side is 20 px, centred by mass in 28x28.

`tools/test_digit_prep.py` compiles `digit_prep.c` on the host and checks it:
MNIST test digits redrawn on a 240x240 pad (random size and place, strokes
about a finger wide) score 98.7% through it. Real finger drawings on the board
are untested.

The files (`template/modules/ai/`):
- `digit_model.cpp`: loads the model from the app's rodata, quantizes the
  28x28 input with the input tensor's exponent, runs it, softmax on the logits;
- `digit.c`: a 240x240 LVGL canvas on the right of the demo screen. A 700 ms
  pause ends the digit (so 4, 5 and 7 can take two strokes); the next touch
  clears it. It logs the digit, its probability, the inference time, and the
  28x28 input as ASCII art (`LOG_INPUT`), which is what to look at when it
  guesses wrong.

Wiring:
- `espressif/esp-dl: "^3.3.13"` under `dependencies:`;
- SRCS `"digit.c" "digit_prep.c" "digit_model.cpp"`, REQUIRES `esp-dl esp_timer`;
- **the model must be 16-byte aligned.** Embed it with ESP-DL's helper, after
  `idf_component_register` (`CMakeLists.ai.cmake`), not with `EMBED_FILES`:
  ```cmake
  idf_component_get_property(espdl_dir espressif__esp-dl COMPONENT_DIR)
  set(cmake_dir ${espdl_dir}/fbs_loader/cmake)
  include(${cmake_dir}/utilities.cmake)
  target_add_aligned_binary_data(${COMPONENT_LIB} models/digit.espdl BINARY)
  ```
- **a bigger app partition.** ESP-DL takes the app to ~2.5 MB, over
  `PARTITION_TABLE_SINGLE_APP_LARGE`'s 1.5 MB. The module's `partitions.csv`
  gives the factory app 6 MB; in `sdkconfig.defaults` it replaces the
  `SINGLE_APP_LARGE` line with `CONFIG_PARTITION_TABLE_CUSTOM=y` and
  `CONFIG_PARTITION_TABLE_CUSTOM_FILENAME="partitions.csv"`;
- `digit_ui_create(lv_screen_active())` right after `build_ui()`, holding the
  LVGL lock.

**Check:** the boot log shows `model loaded`. Draw each digit a few times: the
log gives what the model saw and its answer.

To retrain (e.g. with your own drawings added): see the docstring of
`tools/train_digit_model.py` for the Python 3.12 venv, then run it and
`tools/test_digit_prep.py`.

## 13. Pitfalls, in one place

| Symptom | Cause | Fix |
|---|---|---|
| builds, but the bootloader won't start the app | IDF 6.x targets P4 rev ≥ 3.1 by default; this board is rev v1.x | `CONFIG_ESP32P4_SELECTS_REV_LESS_V3=y` + `CONFIG_ESP32P4_REV_MIN_100=y` (step 3) |
| `abort()` inside `esp_lcd_new_dsi_bus` at the first boot, nothing logged | IDF 6.1's `MIPI_DSI_PHY_PLLREF_CLK_SRC_DEFAULT` is XTAL, rev >= 3.0 only | `MIPI_DSI_PHY_PLLREF_CLK_SRC_DEFAULT_LEGACY` (PLL_F20M) on rev v1.x (`DSI_PHY_CLK` in step 5) |
| `pixel_format` is not a member of `esp_lcd_dpi_panel_config_t` | renamed in IDF 6 | `.in_color_format = LCD_COLOR_FMT_RGB565` |
| `on_refresh_done` deprecated | renamed in IDF 5.5+ | `.on_frame_buf_complete` |
| screen flips between old and new content | `avoid_tearing` without `direct_mode` / `full_refresh`, or `num_fbs` < 2 | step 5 |
| dark screen, nothing on the DSI bus | D-PHY unpowered | LDO3 at 2.5 V **before** `esp_lcd_new_dsi_bus` |
| backlight off at low brightness | the MT9201 barely lights below ~200 / 2047 | duty floor (`BL_DUTY_FLOOR`) |
| GT911 init fails every boot | the driver skips the address latch without `driver_data` | `driver_data = &(esp_lcd_touch_io_gt911_config_t){ .dev_addr = ESP_LCD_TOUCH_IO_I2C_GT911_ADDRESS }` |
| no ES8311 found | the board has none, whatever the schematic says | plain I2S (step 11) |
| esp_hosted 3.x talks to nothing | 2.x option names silently ignored | 3.x names (step 10), check `sdkconfig` |
| boot aborts "Not enough memory to create timer task" with Wi-Fi | esp_hosted allocates from a C constructor while internal RAM is scarce | its buffers and stacks in PSRAM (step 10) |
| `esp_async_memcpy` refuses PSRAM copies | the default (AHB) GDMA can't reach PSRAM on the P4 | install it on the AXI GDMA (`esp_async_memcpy_install_gdma_axi`; in `esp_driver_dma` on IDF 6.x) |
| BOOT key doesn't wake deep sleep | GPIO 35 is not an LP pad; the P4 has no ext0 | wake with RESET (a deep-sleep wake is a reboot anyway) |
| GPIO 0 / 1 do strange things | they are the 32 kHz crystal | don't use them; BOOT is GPIO 35 |
| corrupted flash read-back | the CH340 drops bytes at 921600 | 460800 baud |
| LVGL registered with no sources | project path contains `[` or `]` | move the project |
| "app partition is too small" with ESP-DL | ESP-DL takes the app to ~2.5 MB | a custom partition table (step 12) |
| screen flickers at low brightness, worse on white | the MT9201 at under ~25 % duty, at any PWM frequency | 25 % floor for a brightness control, 0 for off (14.4) |
| TLS fails with `-0x008D`, `allocate_dma_buf: not enough mem`, pages half-draw | internal RAM ran out (PSRAM had plenty) | big buffers, cJSON, SQLite and worker stacks in PSRAM; measure (14.2) |
| `task_wdt: ... IDLE1 (CPU 1)`, over and over | a task computes for seconds (TLS handshake, JPEG, painting) above idle priority | `tskIDLE_PRIORITY`, or yield often (14.3) |
| "Stack protection fault" opening a page | a heavy page opened from `app_main`'s small stack | open it from the LVGL task (an `lv_timer`) (14.3) |
| reboot loop after mounting the microSD card | `SDMMC_HOST_DEFAULT()` picks slot 1 on the P4; the failed mount's cleanup removes esp_hosted's slot | `host.slot = SDMMC_HOST_SLOT_0`; never deinit the host (14.6) |
| "Unrecoverable host sdio state", 0x107, restart | the card was mounted while the C6 link was up or coming up | mount once, before `wifi_start()` (14.6) |
| card and Wi-Fi both dead after a reset | the card was left mid-read and holds D0 low | clock the card by hand and send CMD0 before mounting (14.6) |
| SQLite "disk I/O error" after a reset | `synchronous = NORMAL` on FAT | `PRAGMA synchronous = FULL`, one connection, no WAL (14.6) |
| the clock is set ~30 s late | SNTP's first tries ran before there was an IP | restart SNTP on each `IP_EVENT_STA_GOT_IP` (14.5) |
| a JPEG won't decode | progressive JPEG: both decoders are baseline only | skip it and say why (14.7) |
| the mic's level never moves, or "the data line is flat" | no mic fitted, or it talks in the other slot | check the board; the module reads both slots (step 16) |
| `i2s_channel_init_pdm_rx_mode` fails | PDM RX on a port other than I2S0, or I2S0 taken by the speaker | the mic on I2S0, the speaker on I2S1 (step 16) |
| no BME690 in the I2C scan | CS low or floating (SPI mode), or the connector's pins swapped | CS to 3.3 V, check the pin order with a meter (step 15) |
| accented letters show as boxes | the built-in Montserrat fonts are ASCII only | convert fonts with Latin-1 + Latin Extended-A (14.4) |
| a `DOTS` label wraps over the line below | `LV_LABEL_LONG_MODE_DOTS` needs a fixed height | give the label a height (14.4) |
| the digit model is sure of the wrong digit | the input doesn't look like MNIST | read the ASCII input in the log; adjust `BRUSH_R` or `digit_prep.c`, or retrain with your drawings |

## 14. Growing it into a real app: lessons from ArtShow

Steps 1-13 make a skeleton. This step is what it took to grow one into a
real app: **ArtShow**, made with the wizard (Wi-Fi 2.12.x + audio). It is a
slideshow with eleven pages, HTTPS APIs, SQLite on the microSD card and audio,
built on ESP-IDF 6.1, LVGL 9.6 and esp_hosted 2.12.x on the bench 10.1". Each
rule comes with the symptom that taught it. The rules were measured while
building ArtShow, not re-checked against the files in this repository.

### 14.1 More `sdkconfig.defaults` and components

Lines a bigger app adds to step 3 (one line each; delete `sdkconfig` and
rebuild after adding them):

```
CONFIG_MBEDTLS_EXTERNAL_MEM_ALLOC=y          # TLS buffers (~40 KB a connection) in PSRAM
# CONFIG_MBEDTLS_HARDWARE_ECDSA_VERIFY is not set   # rev v1.x has no ECDSA peripheral
CONFIG_SPIRAM_ALLOW_STACK_EXTERNAL_MEMORY=y  # task stacks in PSRAM (14.2)

CONFIG_LV_USE_CLIB_MALLOC=y                  # LVGL on the system heap, not a fixed 64 KB pool
CONFIG_LV_USE_PPA=y                          # the P4's 2D engine draws fills and images
CONFIG_LV_USE_PPA_IMG=y
CONFIG_LV_DRAW_BUF_ALIGN=64                  # the PPA wants cache-line (64 B) alignment

CONFIG_FATFS_LFN_HEAP=y                      # FAT on the card: long, accented names
CONFIG_FATFS_API_ENCODING_UTF_8=y

CONFIG_PARTITION_TABLE_CUSTOM=y
CONFIG_PARTITION_TABLE_CUSTOM_FILENAME="partitions.csv"
```

LVGL, fonts, TLS and SQLite reach ~3 MB quickly, more than
`SINGLE_APP_LARGE` holds. A 4 MB app partition (the AI module of step 12 uses
6 MB):

```
nvs,      data, nvs,     0x9000,   0x6000,
phy_init, data, phy,     0xf000,   0x1000,
factory,  app,  factory, 0x10000,  0x400000,
```

Components ArtShow added to `main/idf_component.yml`:

```yaml
  espressif/esp_new_jpeg: "^1.0.2"   # software JPEG: decodes and encodes, can shrink
  espressif/cjson: "^1.7.19"         # IDF 6 has no json component
```

### 14.2 Memory: internal RAM is what runs out

The P4 has ~500 KB of internal RAM and 32 MB of PSRAM. What ran out, every
time, was **internal RAM**, while PSRAM had 15 MB free.

Internal RAM goes to:
- task stacks (by default), LVGL objects and its draw buffers in flight,
  lwIP and esp_hosted buffers, FreeRTOS objects;
- each open file on the card: a ~4 KB cache (`CONFIG_FATFS_PER_FILE_CACHE`);
- DMA bounce buffers: the SD driver allocates one (internal) for a read into
  memory it can't DMA into;
- TLS handshakes, even with `CONFIG_MBEDTLS_EXTERNAL_MEM_ALLOC`;
- LVGL on the system heap: drawing a busy page takes ~125 KB for a moment.

Running out is **not** a clean error where you allocate:
- TLS fails with `-0x008D` (PSA_ERROR_INSUFFICIENT_MEMORY) in
  `mbedtls_ssl_setup` or the handshake;
- `sdmmc_cmd: allocate_dma_buf: not enough mem`, and a failed card read;
- LVGL pages that half-draw.

Rules:
- **Big buffers in PSRAM**, explicitly: `heap_caps_malloc(..., MALLOC_CAP_SPIRAM)`
  for images, canvases, text, JSON, tables and caches. Point cJSON at PSRAM
  with `cJSON_InitHooks`: a 70 KB JSON answer is ~3000 nodes, ~200 KB of
  internal RAM otherwise. SQLite too (`SQLITE_CONFIG_MALLOC`).
- Static arrays (`static uint16_t big[...]`) land in internal RAM: allocate
  them in PSRAM at start instead.
- **Worker task stacks in PSRAM**: `xTaskCreateWithCaps(fn, name, stack, arg,
  prio, &handle, MALLOC_CAP_SPIRAM)`. Only for tasks that **never write
  flash** (NVS, OTA, partitions): a flash write disables the cache, and a
  PSRAM stack with it. The Wi-Fi task of step 10 writes NVS, so its stack
  stays internal. Moving four network workers' stacks (42 KB) took ArtShow's
  lowest free internal RAM from 4 KB to ~40 KB.
- Few open files (`max_files` small); open databases only while in use.
- Thousands of LVGL objects don't fit: make a page's cells once and page
  through the data.
- **Measure**: log free, largest block and minimum-ever internal RAM
  (`heap_caps_get_free_size`, `heap_caps_get_largest_free_block`,
  `heap_caps_get_minimum_free_size` with `MALLOC_CAP_INTERNAL`) while Wi-Fi
  connects, TLS runs and pages draw at the same time. Aim for 40 KB+ at the
  lowest; ~90 KB free when idle is comfortable.

### 14.3 Tasks, cores and the watchdog

- FreeRTOS ticks at 100 Hz: `vTaskDelay(1)` is 10 ms. A loop that works in
  25 ms slices and yields a tick loses a third of its time: use ~100 ms slices.
- **Anything that computes for seconds without blocking** runs at
  **`tskIDLE_PRIORITY`**, or yields often. That covers a software JPEG decode
  (3-9 s, up to 60 s under load), image effects, procedural painting and TLS
  handshakes. At any higher priority it starves that core's idle task and the
  task watchdog fires (`task_wdt: ... IDLE1 (CPU 1)`). Equal priorities share
  the core round-robin, so idle priority still gets the work done.
- Pin CPU-heavy work to core 1: LVGL, Wi-Fi and esp_hosted keep core 0 busy.
  Put audio rendering on core 0 if a painter is on core 1.
- Work the UI waits for (thumbnails, page data) goes to a worker task with a
  request queue. A newer request makes older ones stale (a sequence number),
  and results are applied under the LVGL lock.
- Don't open a heavy page from `app_main`: its stack is small, and a page that
  opened a database there overflowed it ("Stack protection fault"). Open it
  from the LVGL task, e.g. a one-shot `lv_timer`.

### 14.4 LVGL and the screen, beyond the demo

LVGL 9.6 API (warnings are often the only sign of a deprecated call):
- per-flag setters and getters (`lv_obj_set_hidden`, `lv_obj_set_clickable`,
  `lv_obj_set_overflow_visible`, `lv_obj_is_hidden` ...), not
  `lv_obj_add_flag`/`has_flag`; `LV_LABEL_LONG_MODE_*`; no `lv_list` (a flex
  column); `lv_draw_task_get_draw_dsc()` (a draw task's fields are private).
- The built-in Montserrat fonts are **ASCII only**. For accented letters,
  typographic quotes and dashes, convert fonts with Latin-1 and Latin
  Extended-A (`lv_font_conv`). Size labels by the font's `line_height`
  (Montserrat 16: 22 px), not its nominal size.
- `LV_LABEL_LONG_MODE_DOTS` only shortens a label **with a fixed height**;
  without one it wraps over the line below.
- `lv_calendar`'s highlight is a fill on the day's cell, and a transparent
  cell draws no fill: make the cells opaque.
- LVGL keeps 32 invalid areas a frame: invalidate in bands, not per tile.
- Custom drawing: `LV_EVENT_DRAW_MAIN` (behind the children),
  `DRAW_MAIN_END`/`DRAW_POST` (over them), `LV_EVENT_DRAW_TASK_ADDED` to
  restyle what a widget draws (it needs the send-draw-task-events flag). Shapes
  drawn this way (frames, icons, clock hands) cost no memory and scale. For a
  full-screen texture, use one small tile as a tiled background image
  (`lv_obj_set_style_bg_image_tiled`).

Speed:
- Images the PPA draws (`CONFIG_LV_USE_PPA_IMG`) must be RGB565 buffers
  **64-byte aligned** (`heap_caps_aligned_alloc(64, ..., MALLOC_CAP_SPIRAM)`),
  with a row stride that is a multiple of 64 bytes. A full-screen image took
  ~40 ms by the CPU; the PPA takes a fraction of that.
- PSRAM bandwidth is the limit: the panel's scan-out (step 3), LVGL's
  framebuffers and every big buffer share it. A full-screen 1.2 MB PSRAM copy
  takes ~28 ms; a full-screen redraw per frame gives 7-12 fps. Redraw only
  what changed.
- With direct mode and two framebuffers (step 5), the off-screen buffer lags
  until the next refresh: comparing it with the picture shows differences,
  and that is normal.

Designing pages:
- Touch targets 44 px or more; enlarge small ones with
  `lv_obj_set_ext_click_area`.
- Buttons that stay on every page (ArtShow: menu top left, brightness bottom
  left, Wi-Fi bottom right) are styled for dark backgrounds and vanish on a
  light page. Keep a dark margin under them, or keep content out of the
  corners.
- Long text scrolls in a fixed box; captions are fixed-height one-line labels.

Backlight: ArtShow saw the screen **flicker below ~25 %** (worse on white),
at any PWM frequency from 1 to 30 kHz. Keep 25 % as the floor of a brightness
control and 0 for "off". The base's `BL_DUTY_FLOOR` (200 / 2047, ~10 %) only
keeps it lit, so it doesn't stop the flicker.

### 14.5 Wi-Fi in practice: SNTP and HTTPS

- SNTP: start it after `wifi_start()` (which initialises esp_netif), and
  **restart it on each `IP_EVENT_STA_GOT_IP`**. Its first tries fail before
  there is an IP, and then it waits ~27 s to retry. Restarted on GOT_IP, the
  time arrives ~3 s after the IP. Set `TZ` first thing in `app_main` if
  anything stamps local times before the sync.
- HTTPS: `esp_http_client` with IDF's certificate bundle.
- The rev v1.x P4 has no ECDSA peripheral: each handshake verifies in
  software, **~2 s**, longer when several overlap. Keep one connection open
  for a run of calls to one server, and cache answers.
- A handshake is seconds of CPU without a yield: **run network tasks at
  `tskIDLE_PRIORITY`**. At priority 3 one starved core 1's idle task, and the
  task watchdog fired again and again.
- `esp_http_client` didn't follow a relative 302 on the board: don't rely on
  it for unusual redirects.
- Never log a URL that carries an API key. Keep keys on the SD card (e.g. a
  `config.json`), never in sources.
- Public APIs rate-limit: Wikipedia's search returned HTTP 429 for minutes
  after a burst. Make one search per lookup, cache answers, and show
  "busy, try again". Free plans count calls, and every test boot fetches: a
  day of test reboots used up a 50-calls-a-day weather key.

### 14.6 The microSD card, and why it fights Wi-Fi

- SDMMC **slot 0**, 1-bit: CLK 43, CMD 44, D0 39. D1..D3 can't be used,
  since 40..42 are touch and LCD lines. Internal pull-ups; the IO is powered
  by LDO4 at 3.3 V (take it in the board's init). 20 MHz is fine; use 10 MHz
  if a card is flaky.
- **Set `host.slot = SDMMC_HOST_SLOT_0` by hand**: on the P4,
  `SDMMC_HOST_DEFAULT()` picks slot 1. A mount on slot 1 fails, its cleanup
  removes esp_hosted's slot, esp_hosted asserts, and the board reboots in a
  loop.
- esp_hosted owns **slot 1 of the same SDMMC host**: never deinit the host,
  only slot 0.
- **Mount the card once, before `wifi_start()`.** A card init changes the
  controller's clock. Doing it while the C6 link is up, or coming up, times out
  (0x107), breaks the link ("Unrecoverable host sdio state") and restarts the
  board. Reads and writes once both are up are fine. No remounts: if the card
  goes, say so and offer a restart.
- **A card left mid-read** by a board reset (the card keeps its power) holds
  D0 low, and the first clock update jams the whole host, Wi-Fi too. Before
  mounting, clock the card by hand and send CMD0 (an "unstick" step).
- The board is reset, never shut down, and a file's size reaches the card
  only when the file is synced or closed. SQLite on FAT needs
  `PRAGMA synchronous = FULL`: with NORMAL, the next boot read the database as
  "disk I/O error". FAT has no locks: one connection, one thread
  (`SQLITE_THREADSAFE=0` plus a mutex), no WAL, temp in memory. A database
  that is only a cache may be rebuilt when unreadable. One with the user's
  data must be renamed aside and kept, never replaced.
- 1-bit SD is slow: ~1.5-3 s to read a 3 MB file, much longer when the CPU is
  busy. Stream downloads to the card in chunks (16 KB).

### 14.7 Images and JPEG

- The **hardware JPEG engine** is fast (~50 ms), but **baseline only**, can't
  scale, and the full-size output must fit in memory (8 MB of RGB565 is ~4 MP).
- **esp_new_jpeg** (software) shrinks by 1/2, 1/4 or 1/8 while decoding, so a
  4096 px picture fits; it takes ~3-9 s. Also baseline only: skip progressive
  JPEGs, and say why. It also encodes (quality 75-92; 4:4:4 keeps thin
  coloured lines). Neither applies EXIF rotation.
- Box-scale into the target size afterwards; keep output buffers 64-byte
  aligned for the PPA (14.4).

### 14.8 Maths and speed on the P4 (measured)

- The FPU is **single precision**: doubles are software. That's fine for a few
  thousand operations (astronomy once a day), not per pixel.
- A float op takes ~6 cycles; `sinf` ~6 us (a 4096-entry table is 25x
  faster); `logf` ~0.35 us (use a table for per-pixel tone maps); a random
  write to a PSRAM buffer ~0.9 us.
- Build pixel loops at `-O2` even when the app is `-Og`
  (`set_source_files_properties(... COMPILE_OPTIONS "-O2")`). With -O2 and a
  tighter loop, a diffusion filter went from 94 s to 15 s. Interleave
  channels, use fixed point where it's simpler, flush denormals.
- Paint big pictures off the LVGL task, in place, and invalidate when done.
- Keep pure computation (image effects, painters, synthesis, astronomy) in
  plain C files with no IDF includes, like `digit_prep.c` (step 12). Then it
  builds and runs on the computer first: render a 1024 x 600 RGB565 file or a
  WAV there, look at it, then move it to the board.

### 14.9 Audio in practice

- Turn the amps on (GPIO 30 **low**) only while playing: off, they're silent.
- Enable the I2S channel's auto-clear, so gaps between writes are silence,
  not a buzz. Feed the DMA from one task in short blocks (e.g. 16 ms); the DMA
  paces it.
- USB audio out, a USB DAC on J16: the P4's host can do UAC 1.0, but the
  socket gives no 5 V (the DAC must be self-powered or on a powered hub),
  split transactions aren't supported (a full-speed DAC behind a high-speed hub
  fails), and IDF 6.1 has no full-speed-only option.

### 14.10 Testing on the board

- **Check the build's exit code before flashing.** A failed build followed by
  `flash` writes the *previous* binary, and the test then "passes" or "fails"
  on old code.
- Capture logs without an interactive monitor: a small pyserial script that
  pulses RTS (reset), reads for N seconds into a file, and is then grepped.
  Grep for `Guru`, `abort`, `assert`, `task_wdt`, `not enough mem`, `-0x`, and
  your own module's lines.
- Open the page under test from **a one-shot `lv_timer`**, a few seconds after
  boot, not from `app_main` (14.3).
- Mark temporary test code (`/* TEST */`), keep a copy of the file before
  adding it, and restore and rebuild before committing. While testing
  anything new, log internal RAM and PSRAM every few seconds (14.2).
- Tests that write to the card leave files behind (a test that pressed Save
  put its pictures in the slideshow): delete them after.
- An agent can't see the screen: report what the log showed, and ask a person
  to look at the rest.
- Write down what each pitfall cost (symptom, cause, fix) where the next
  person or agent will read it: the project's `CLAUDE.md`.

## 15. Optional: a BME690 sensor on the I2C connector

The BME690 measures temperature, humidity, pressure and gas (the resistance of
a heated metal-oxide plate). The module drives it with Bosch's own BME69x
Sensor API, on the I2C bus the board already runs for the GT911.

### Wiring

The board's **I2C connector** is a PH2.0 4-pin socket (2.0 mm pitch): SDA on
GPIO 45, SCL on GPIO 46, 3.3 V out, up to 1 A (Elecrow's wiki). It's the
touch controller's bus.

| BME690 pin | to | why |
|---|---|---|
| VCC | 3.3 V | the chip takes 1.71-3.6 V; 5 V only if the breakout has its own regulator |
| GND | GND | |
| SCL | SCL, GPIO 46 | |
| SDA | SDA, GPIO 45 | |
| CS | **3.3 V** | CS high at power-up selects I2C; low selects SPI, and then nothing answers on I2C |
| SDO | **GND** (0x76) or 3.3 V (0x77) | the address; neither clashes with 0x2f or 0x5d |

- Elecrow's wiki doesn't give the connector's pin order: read it off the
  silkscreen or the V1.2 schematic, and check 3.3 V and GND with a meter
  before plugging the sensor in.
- Many breakouts already pull CS and SDO to a level. On the bench board, a
  breakout wired with only VCC, GND, SCL and SDA answered at **0x77**: it pulls
  both up. If yours doesn't answer, tie CS to 3.3 V: a floating CS is the usual
  reason.
- The bus has its own pull-ups (and the P4's internal ones, enabled in
  `board.c`). A breakout's 10k pull-ups in parallel are fine on a short cable.
- **Check:** the boot's I2C scan (step 9) lists `0x76` (or `0x77`) next to
  `0x2f 0x5d`.

### Files

From `template/modules/bme690/` into `main/`:
- `bme69x.c`, `bme69x.h`, `bme69x_defs.h`: Bosch's BME69x Sensor API v1.1.0
  (https://github.com/boschsensortec/BME690_SensorAPI, commit 8a4d922),
  unchanged, with its licence as `LICENSE.bme69x` (BSD-3). Float output
  (`BME69X_USE_FPU`, the API's default).
- `bme690.c/.h`: the glue, ~140 lines:
  - `bme690_start()` probes 0x76, then 0x77, adds the device to
    `board_i2c_bus()` at 400 kHz, runs `bme69x_init` (soft reset, chip id
    0x61, calibration), and starts a task (priority 2, 4 KB stack);
  - the task configures oversampling (T 8x, P 4x, H 2x) and the heater
    (300 °C for 100 ms), then every 3 s triggers a forced measurement, waits
    `bme69x_get_meas_dur()` plus the heater time, reads, logs and updates the
    card under the LVGL lock;
  - `bme690_ui_create()` puts a readings card at the left middle of the demo
    screen; `bme690_latest()` returns the last reading;
  - no `ESP_ERROR_CHECK`: without a sensor it logs a warning and stops, the
    app runs on.

The three callbacks the API needs:

```c
static BME69X_INTF_RET_TYPE rd(uint8_t reg, uint8_t *data, uint32_t len, void *ctx) {
    return i2c_master_transmit_receive(s_dev, &reg, 1, data, len, 100) == ESP_OK ? 0 : -1;
}

/* the API passes reg_data as value, reg, value, ... after reg: one transfer */
static BME69X_INTF_RET_TYPE wr(uint8_t reg, const uint8_t *data, uint32_t len, void *ctx) {
    uint8_t buf[BME69X_LEN_INTERLEAVE_BUFF];   /* reg + at most 19 bytes */
    if (len >= sizeof buf) return -1;
    buf[0] = reg;
    memcpy(buf + 1, data, len);
    return i2c_master_transmit(s_dev, buf, len + 1, 100) == ESP_OK ? 0 : -1;
}

/* the tick is 10 ms: busy-wait the short delays, sleep the long ones */
static void delay_us(uint32_t us, void *ctx) {
    if (us < 10000) esp_rom_delay_us(us);
    else vTaskDelay(pdMS_TO_TICKS((us + 9999) / 1000));
}
```

### Wiring it in

- copy the files above into `main/`;
- in `main/CMakeLists.txt`, add `"bme690.c" "bme69x.c"` to SRCS (the base's
  `esp_driver_i2c` covers the rest);
- call `bme690_ui_create(lv_screen_active())` right after `build_ui()`, inside
  the LVGL lock, and `bme690_start()` at the end of `app_main` (before
  `wifi_start()`).

Notes:
- **One bus.** Add devices to `board_i2c_bus()`; never create a second bus on
  GPIO 45/46. The i2c_master driver locks the bus per transfer, so the touch
  task and the sensor task share it safely.
- **Gas** is valid only when the status has both `GASM_VALID` and
  `HEAT_STAB`, and it drifts for minutes after power-up. It is a raw
  resistance: an air-quality index (IAQ, eCO2) needs Bosch's BSEC library,
  which is closed source under its own licence and not included.
- The heater warms the sensor, so the temperature can read a little high;
  a longer period (less heater duty) or a calibration against a thermometer
  helps.

**Check:** the log shows `bme690: BME690 at 0x76, chip id 0x61, ...`, then a
line every 3 s, in the form `23.41 C, 45.20 %RH, 1013.25 hPa, gas 52000 ohm`. The card
shows the same; breathe on the sensor and the humidity climbs.

## 16. Optional: the PDM microphone

Elecrow's wiki lists a **PDM microphone** on GPIO 24 (clock) and GPIO 26
(data), straight to the P4, no codec. **The bench 10.1" has it** (2026-10-25):
it talks in the left slot, and its level follows a voice (about -60 dBFS in a
quiet room, -46 for a voice nearby, -29 for the boot beep). The same wiki
promises an ES8311 the board doesn't have (step 11), so the mic was checked
rather than assumed.

The P4's I2S0 turns the mic's 1-bit PDM stream into PCM in hardware (PDM RX
mode, `I2S_PDM_DATA_FMT_PCM`).

- **I2S0 is the only port with PDM RX** (`SOC_I2S_PDM_MAX_RX_LINES`, "on
  I2S0"). The mic takes it, so with the mic the speaker (step 11) moves to
  **I2S1**: change `I2S_NUM_0` to `I2S_NUM_1` in `audio.c` (the wizard does it
  when both are chosen). Its standard mode works on any of the three ports,
  and the boot beep on I2S1 was heard on the bench board.
- Pins in `board_pins.h`: `PIN_MIC_CLK 24`, `PIN_MIC_DATA 26`.

### `main/mic.c/.h`

From `template/modules/mic/`:
- `mic_start()`: a PDM RX channel on I2S0, 16 kHz, 16-bit, **both slots**,
  and a reader task (priority 4, 4 KB stack). Without the channel it logs and
  returns; the app runs on.
- The mic's select pin decides which slot it talks in, and Elecrow doesn't
  say how it's strapped. The task reads both, and the first block with sound
  picks the louder slot (`the mic is in the left slot` in the log).
- Every 20 ms block: its level in dBFS (`mic_level_db()`), the mono samples
  to `mic_on_block(cb)` (in the mic task: copy, don't block), a level bar
  (`mic_ui_create`, bottom left, -80..0 dBFS) 10 times a second, and a log
  line once a second.

The channel:

```c
i2s_chan_config_t cc = I2S_CHANNEL_DEFAULT_CONFIG(I2S_NUM_0, I2S_ROLE_MASTER);
i2s_new_channel(&cc, NULL, &s_rx);
i2s_pdm_rx_config_t pc = {
    .clk_cfg = I2S_PDM_RX_CLK_DEFAULT_CONFIG(MIC_RATE),
    .slot_cfg = I2S_PDM_RX_SLOT_DEFAULT_CONFIG(I2S_DATA_BIT_WIDTH_16BIT, I2S_SLOT_MODE_STEREO),
    .gpio_cfg = { .clk = PIN_MIC_CLK, .din = PIN_MIC_DATA },
};
i2s_channel_init_pdm_rx_mode(s_rx, &pc);
i2s_channel_enable(s_rx);
```

### Wiring it in

- copy `mic.c/.h` into `main/`;
- in `main/CMakeLists.txt`, add `"mic.c"` to SRCS and `esp_driver_i2s` to
  REQUIRES (once, if the speaker is there too);
- call `mic_ui_create(lv_screen_active())` right after `build_ui()`, inside
  the LVGL lock, and `mic_start()` at the end of `app_main`, before
  `wifi_start()`.

**Check:** the log shows `mic: PDM mic on clk 24, data 26, 16000 Hz`, then once
a second `level -62 dBFS, peak -55` or similar. Talk near the board: the level
and the bar rise. `the data line is flat` means no mic is fitted, or it isn't
on these pins.

For speech (wake words, commands), Espressif's ESP-SR supports the P4; feed it
from `mic_on_block`.

## Where this came from

- The pins, timings, power, backlight, touch and audio facts are from this
  repository's working CrowPanel P4 port, on IDF 5.4.1 on the bench 10.1" V1.2
  (`docs/board-crowpanel-p4.md`, `firmware/main/display_port_dsi.c`,
  `firmware/sdkconfig.crowp4`).
- The port's sources: Elecrow's V1.2 schematic and readme, their
  `example/V1.2/idf-code` Lessons 05 / 07 / 11 / 17, and the factory firmware's
  boot log.
- The IDF 6.x specifics come from building this exact scaffold on ESP-IDF v6.1
  (2026-10-18):
  - the chip-revision options;
  - `in_color_format` and `on_frame_buf_complete`;
  - `esp_lcd_ek79007` 2.0.2, esp_lvgl_port 2.9.0 and LVGL 9.6;
  - both esp_hosted lines and their option names.
- Step 14 is from building **ArtShow** with the wizard on the bench 10.1",
  ESP-IDF 6.1 (2026-10): its `docs/guide_for_agent_advance-p4.md`, also kept
  in this repository's `docs/`. The measurements are ArtShow's.
- esp_hosted compatibility is from the esp_hosted 3.0.9 component's own
  `docs/migration.md` and `docs/troubleshooting.md`.
