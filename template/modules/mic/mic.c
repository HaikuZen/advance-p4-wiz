/* mic.c - the board's PDM microphone: I2S0 in PDM RX mode turns the 1-bit
 * stream into 16 kHz PCM in hardware. Which slot the mic answers in depends on
 * its select pin, which Elecrow doesn't document: both slots are read, and the
 * louder one is used. A task reads 20 ms blocks, measures them and passes them on. */
#include "mic.h"
#include "board_pins.h"
#include "driver/i2s_pdm.h"
#include "esp_lvgl_port.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include <math.h>

#define BLOCK  (MIC_RATE / 50)   /* 20 ms */

static const char *TAG = "mic";
static i2s_chan_handle_t s_rx;
static mic_block_cb_t s_cb;
static volatile float s_db = -100;
static lv_obj_t *s_bar, *s_label;

float mic_level_db(void) { return s_db; }
void mic_on_block(mic_block_cb_t cb) { s_cb = cb; }

static float rms_db(const int16_t *x, int n, int step) {
    double sum = 0;
    for (int i = 0; i < n; i += step) sum += (double)x[i] * x[i];
    double rms = sqrt(sum / (n / step));
    return rms < 1 ? -100 : 20 * log10f(rms / 32768.0f);
}

static void show(float db) {
    if (!s_bar || !lvgl_port_lock(0)) return;
    lv_bar_set_value(s_bar, db < -80 ? 0 : (int)db + 80, LV_ANIM_OFF);   /* -80..0 dBFS */
    lv_label_set_text_fmt(s_label, "Mic %d dB", (int)db);
    lvgl_port_unlock();
}

static void mic_task(void *arg) {
    static int16_t lr[2 * BLOCK], mono[BLOCK];
    int slot = -1, blocks = 0, flat = 0;
    float peak = -100;
    for (;;) {
        size_t got = 0;
        if (i2s_channel_read(s_rx, lr, sizeof lr, &got, pdMS_TO_TICKS(1000)) != ESP_OK || got < sizeof lr) {
            ESP_LOGW(TAG, "read timed out");
            continue;
        }
        float dl = rms_db(lr, 2 * BLOCK, 2), dr = rms_db(lr + 1, 2 * BLOCK, 2);
        if (slot < 0 && fmaxf(dl, dr) > -90) {   /* the first block with sound picks the slot */
            slot = dr > dl;
            ESP_LOGI(TAG, "the mic is in the %s slot", slot ? "right" : "left");
        }
        int s = slot < 0 ? 0 : slot;
        for (int i = 0; i < BLOCK; i++) mono[i] = lr[2 * i + s];
        s_db = s ? dr : dl;
        peak = fmaxf(peak, s_db);
        flat += lr[0] == lr[2 * BLOCK - 2] && s_db <= -100;
        if (s_cb) s_cb(mono, BLOCK);
        if (++blocks % 5 == 0) show(s_db);   /* the bar: 10 updates a second */
        if (blocks % 50 == 0) {              /* the log: once a second */
            if (flat >= 50) ESP_LOGW(TAG, "the data line is flat: no mic fitted, or not on GPIO %d/%d?", PIN_MIC_CLK, PIN_MIC_DATA);
            else ESP_LOGI(TAG, "level %.0f dBFS, peak %.0f", s_db, peak);
            peak = -100;
            flat = 0;
        }
    }
}

void mic_start(void) {
    i2s_chan_config_t cc = I2S_CHANNEL_DEFAULT_CONFIG(I2S_NUM_0, I2S_ROLE_MASTER);
    esp_err_t err = i2s_new_channel(&cc, NULL, &s_rx);
    i2s_pdm_rx_config_t pc = {
        .clk_cfg = I2S_PDM_RX_CLK_DEFAULT_CONFIG(MIC_RATE),
        .slot_cfg = I2S_PDM_RX_SLOT_DEFAULT_CONFIG(I2S_DATA_BIT_WIDTH_16BIT, I2S_SLOT_MODE_STEREO),
        .gpio_cfg = { .clk = PIN_MIC_CLK, .din = PIN_MIC_DATA },
    };
    if (err == ESP_OK) err = i2s_channel_init_pdm_rx_mode(s_rx, &pc);
    if (err == ESP_OK) err = i2s_channel_enable(s_rx);
    if (err != ESP_OK) {   /* log and carry on: the rest of the app doesn't need the mic */
        ESP_LOGE(TAG, "PDM RX on I2S0: %s - no mic", esp_err_to_name(err));
        return;
    }
    if (xTaskCreate(mic_task, "mic", 4096, NULL, 4, NULL) != pdPASS) ESP_LOGE(TAG, "no memory for its task");
    else ESP_LOGI(TAG, "PDM mic on clk %d, data %d, %d Hz", PIN_MIC_CLK, PIN_MIC_DATA, MIC_RATE);
}

void mic_ui_create(lv_obj_t *parent) {
    s_label = lv_label_create(parent);
    lv_label_set_text(s_label, "Mic --");
    lv_obj_set_style_text_color(s_label, lv_color_hex(0xE0F0FF), 0);
    lv_obj_set_style_text_font(s_label, &lv_font_montserrat_24, 0);
    lv_obj_align(s_label, LV_ALIGN_BOTTOM_LEFT, 24, -100);

    s_bar = lv_bar_create(parent);
    lv_obj_set_size(s_bar, 160, 20);
    lv_bar_set_range(s_bar, 0, 80);
    lv_obj_align(s_bar, LV_ALIGN_BOTTOM_LEFT, 24, -64);
}
