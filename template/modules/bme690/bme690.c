/* bme690.c - a BME690 (temperature, humidity, pressure, gas) on the board's I2C
 * connector, through Bosch's BME69x Sensor API (bme69x.c, BSD-3, v1.1.0). It
 * shares the bus that board.c set up for the GT911: the i2c_master driver locks
 * it per transfer. One task reads the sensor in forced mode every PERIOD_MS. */
#include "bme690.h"
#include "bme69x.h"
#include "board.h"
#include "esp_lvgl_port.h"
#include "esp_log.h"
#include "esp_rom_sys.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include <string.h>

#define PERIOD_MS    3000
#define HEATER_C     300    /* gas plate temperature, and how long it's held */
#define HEATER_MS    100
#define I2C_HZ       400000

static const char *TAG = "bme690";
static i2c_master_dev_handle_t s_dev;
static struct bme69x_dev s_bme;
static bme690_data_t s_last;
static lv_obj_t *s_vals;

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

static void show(void) {
    if (!s_vals || !lvgl_port_lock(0)) return;
    if (!s_last.valid) lv_label_set_text(s_vals, "No sensor\n(see the log)");
    else if (s_last.gas_ohm > 0)
        lv_label_set_text_fmt(s_vals, "%.1f °C\n%.1f %% RH\n%.1f hPa\ngas %.1f kOhm",
                              s_last.temp_c, s_last.hum_pct, s_last.press_hpa, s_last.gas_ohm / 1000);
    else
        lv_label_set_text_fmt(s_vals, "%.1f °C\n%.1f %% RH\n%.1f hPa\ngas: heating",
                              s_last.temp_c, s_last.hum_pct, s_last.press_hpa);
    lvgl_port_unlock();
}

static void bme690_task(void *arg) {
    struct bme69x_conf conf = { .filter = BME69X_FILTER_OFF, .odr = BME69X_ODR_NONE,
                                .os_hum = BME69X_OS_2X, .os_pres = BME69X_OS_4X, .os_temp = BME69X_OS_8X };
    struct bme69x_heatr_conf heatr = { .enable = BME69X_ENABLE, .heatr_temp = HEATER_C, .heatr_dur = HEATER_MS };
    if (bme69x_set_conf(&conf, &s_bme) != BME69X_OK || bme69x_set_heatr_conf(BME69X_FORCED_MODE, &heatr, &s_bme) != BME69X_OK) {
        ESP_LOGE(TAG, "configuration failed - no readings");
        vTaskDelete(NULL);
    }
    for (;;) {
        struct bme69x_data d;
        uint8_t n = 0;
        int8_t r = bme69x_set_op_mode(BME69X_FORCED_MODE, &s_bme);
        if (r == BME69X_OK) {
            delay_us(bme69x_get_meas_dur(BME69X_FORCED_MODE, &conf, &s_bme) + HEATER_MS * 1000, NULL);
            r = bme69x_get_data(BME69X_FORCED_MODE, &d, &n, &s_bme);
        }
        if (r == BME69X_OK && n) {
            bool gas = (d.status & BME69X_GASM_VALID_MSK) && (d.status & BME69X_HEAT_STAB_MSK);
            s_last = (bme690_data_t){ .temp_c = d.temperature, .hum_pct = d.humidity, .press_hpa = d.pressure / 100,
                                      .gas_ohm = gas ? d.gas_resistance : 0, .valid = true };
            ESP_LOGI(TAG, "%.2f C, %.2f %%RH, %.2f hPa, gas %.0f ohm%s", s_last.temp_c, s_last.hum_pct,
                     s_last.press_hpa, d.gas_resistance, gas ? "" : " (heater not stable)");
            show();
        } else {
            ESP_LOGW(TAG, "read failed (%d)", r);
        }
        vTaskDelay(pdMS_TO_TICKS(PERIOD_MS));
    }
}

bme690_data_t bme690_latest(void) { return s_last; }

void bme690_start(void) {
    i2c_master_bus_handle_t bus = board_i2c_bus();
    uint8_t addr = 0;
    if (i2c_master_probe(bus, BME69X_I2C_ADDR_LOW, 20) == ESP_OK) addr = BME69X_I2C_ADDR_LOW;
    else if (i2c_master_probe(bus, BME69X_I2C_ADDR_HIGH, 20) == ESP_OK) addr = BME69X_I2C_ADDR_HIGH;
    if (!addr) {
        ESP_LOGW(TAG, "nothing at 0x76 or 0x77: check the wiring (CS to 3.3 V for I2C)");
        show();
        return;
    }
    const i2c_device_config_t dc = { .dev_addr_length = I2C_ADDR_BIT_LEN_7, .device_address = addr, .scl_speed_hz = I2C_HZ };
    if (i2c_master_bus_add_device(bus, &dc, &s_dev) != ESP_OK) {
        ESP_LOGE(TAG, "can't add the device");
        show();
        return;
    }
    s_bme = (struct bme69x_dev){ .intf = BME69X_I2C_INTF, .read = rd, .write = wr, .delay_us = delay_us, .amb_temp = 25 };
    int8_t r = bme69x_init(&s_bme);
    if (r != BME69X_OK) {
        ESP_LOGE(TAG, "0x%02x answers, but bme69x_init failed (%d): not a BME690?", addr, r);
        show();
        return;
    }
    ESP_LOGI(TAG, "BME690 at 0x%02x, chip id 0x%02x, variant %lu", addr, s_bme.chip_id, (unsigned long)s_bme.variant_id);
    if (xTaskCreate(bme690_task, "bme690", 4096, NULL, 2, NULL) != pdPASS) ESP_LOGE(TAG, "no memory for its task");
}

void bme690_ui_create(lv_obj_t *parent) {
    lv_obj_t *card = lv_obj_create(parent);
    lv_obj_set_size(card, 260, 210);
    lv_obj_set_style_bg_color(card, lv_color_hex(0x1B263B), 0);
    lv_obj_set_style_border_width(card, 0, 0);
    lv_obj_set_scrollable(card, false);
    lv_obj_align(card, LV_ALIGN_LEFT_MID, 24, 0);

    lv_obj_t *title = lv_label_create(card);
    lv_label_set_text(title, "BME690");
    lv_obj_set_style_text_color(title, lv_color_hex(0x00C8FF), 0);
    lv_obj_set_style_text_font(title, &lv_font_montserrat_24, 0);
    lv_obj_align(title, LV_ALIGN_TOP_LEFT, 0, 0);

    s_vals = lv_label_create(card);
    lv_label_set_text(s_vals, "Reading...");
    lv_obj_set_style_text_color(s_vals, lv_color_hex(0xE0F0FF), 0);
    lv_obj_set_style_text_font(s_vals, &lv_font_montserrat_24, 0);
    lv_obj_align(s_vals, LV_ALIGN_TOP_LEFT, 0, 40);
}
