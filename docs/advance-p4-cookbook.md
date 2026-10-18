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
**speaker**, and an **AI** demo (handwritten digits with ESP-DL).

**Status (2026-10-18):**
- **Built on ESP-IDF v6.1:** every file in this cookbook, including both Wi-Fi
  options and the audio snippet, compiles with no warnings.
- **Not yet flashed** from a 6.x build.
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
| backlight | GPIO 31 into an MT9201, LEDC PWM 30 kHz, 11-bit, lit from duty ~200 / 2047 |
| touch | GT911 at 0x5d: SDA 45, SCL 46, INT 42, RST 40 |
| other I2C | 0x2f: an STC8 battery helper. **No ES8311**, despite the schematic (see step 11) |
| audio | plain I2S, no codec: BCLK 22, WS 21, DOUT 23, no MCLK; amps enable GPIO 30 **active low** |
| Wi-Fi | ESP32-C6 over 4-bit SDIO: CLK 18, CMD 19, D0..D3 17 / 16 / 15 / 14, C6 enable GPIO 32 |
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
- LVGL only compiles in the fonts enabled here.
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
                                          .phy_clk_src = MIPI_DSI_PHY_PLLREF_CLK_SRC_DEFAULT,
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
   low end.

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

Both build cleanly on IDF 6.1 with the pins below. **Neither has connected to
a network from a 6.x build yet.** The tank's IDF 5.4 port boots esp_hosted
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

### `main/wifi.c`: bring it up and scan once

```c
/* wifi.c - Wi-Fi through the onboard ESP32-C6 (esp_hosted): the plain
 * esp_wifi API, forwarded to the C6 over SDIO by esp_wifi_remote. */
#include "wifi.h"
#include "esp_wifi.h"
#include "esp_netif.h"
#include "esp_event.h"
#include "nvs_flash.h"
#include "esp_log.h"

static const char *TAG = "wifi";

void wifi_scan_once(void) {
    esp_err_t err = nvs_flash_init();
    if (err == ESP_ERR_NVS_NO_FREE_PAGES || err == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_ERROR_CHECK(nvs_flash_erase());
        ESP_ERROR_CHECK(nvs_flash_init());
    }
    ESP_ERROR_CHECK(esp_netif_init());
    ESP_ERROR_CHECK(esp_event_loop_create_default());
    esp_netif_create_default_wifi_sta();
    wifi_init_config_t cfg = WIFI_INIT_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_wifi_init(&cfg));
    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_STA));
    ESP_ERROR_CHECK(esp_wifi_start());
    ESP_ERROR_CHECK(esp_wifi_scan_start(NULL, true));   /* blocking */
    uint16_t n = 0;
    esp_wifi_scan_get_ap_num(&n);
    wifi_ap_record_t ap[10];
    uint16_t max = 10;
    esp_wifi_scan_get_ap_records(&max, ap);
    ESP_LOGI(TAG, "%u networks, showing %u", n, max);
    for (int i = 0; i < max; i++) ESP_LOGI(TAG, "  %-32s ch %2d rssi %d", (char *)ap[i].ssid, ap[i].primary, ap[i].rssi);
}
```

`main/wifi.h`:

```c
#pragma once
/* bring up Wi-Fi through the C6 and log one scan */
void wifi_scan_once(void);
```

Then:
- add `"wifi.c"` to `SRCS`;
- add `esp_wifi esp_netif esp_event nvs_flash` to `REQUIRES`;
- call `wifi_scan_once()` at the end of `app_main`.

**Check:** the boot log shows the C6 answering, with its esp_hosted firmware
version, and then a list of nearby networks.

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
| the digit model is sure of the wrong digit | the input doesn't look like MNIST | read the ASCII input in the log; adjust `BRUSH_R` or `digit_prep.c`, or retrain with your drawings |

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
- esp_hosted compatibility is from the esp_hosted 3.0.9 component's own
  `docs/migration.md` and `docs/troubleshooting.md`.
