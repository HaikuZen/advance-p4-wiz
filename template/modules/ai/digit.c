/* digit.c - the AI module's demo: draw a digit with a finger, the CNN names it.
 * The pad keeps its own ink map for the model; a pause ends the digit. */
#include "digit.h"
#include "digit_prep.h"
#include "esp_heap_caps.h"
#include "esp_log.h"
#include "esp_timer.h"
#include <stdio.h>
#include <string.h>

#define PAD        240    /* the pad, px square */
#define BRUSH_R    11     /* finger-wide: ~2 px once the digit is scaled into MNIST's 20 px box */
#define SETTLE_MS  700    /* a pause this long ends the digit (4, 5, 7 often take two strokes) */
#define LOG_INPUT  1      /* log the 28x28 the model sees, as ASCII: what to look at when it guesses wrong */

static const char *TAG = "digit";
static uint8_t *s_ink;                 /* PAD x PAD, 0 / 255 */
static lv_obj_t *s_canvas, *s_hint, *s_result;
static lv_timer_t *s_settle;
static lv_point_t s_last;
static bool s_stroking, s_answered, s_have_model;

static void pad_clear(void) {
    memset(s_ink, 0, PAD * PAD);
    lv_canvas_fill_bg(s_canvas, lv_color_black(), LV_OPA_COVER);
    lv_obj_set_hidden(s_hint, false);
    lv_label_set_text(s_result, s_have_model ? "Digit: -" : "No model");
    s_answered = false;
}

static void stamp(int cx, int cy) {
    for (int dy = -BRUSH_R; dy <= BRUSH_R; dy++)
        for (int dx = -BRUSH_R; dx <= BRUSH_R; dx++) {
            int x = cx + dx, y = cy + dy;
            if (dx * dx + dy * dy > BRUSH_R * BRUSH_R || x < 0 || y < 0 || x >= PAD || y >= PAD) continue;
            s_ink[y * PAD + x] = 255;
            lv_canvas_set_px(s_canvas, x, y, lv_color_white(), LV_OPA_COVER);
        }
}

/* a stroke segment as overlapping stamps, then redraw just that part of the pad */
static void segment(lv_point_t a, lv_point_t b) {
    int dx = b.x - a.x, dy = b.y - a.y, len = (dx < 0 ? -dx : dx) + (dy < 0 ? -dy : dy);
    int steps = len / (BRUSH_R / 2) + 1;
    for (int i = 0; i <= steps; i++) stamp(a.x + dx * i / steps, a.y + dy * i / steps);
    lv_area_t c, r;
    lv_obj_get_coords(s_canvas, &c);
    r.x1 = c.x1 + LV_MIN(a.x, b.x) - BRUSH_R; r.x2 = c.x1 + LV_MAX(a.x, b.x) + BRUSH_R;
    r.y1 = c.y1 + LV_MIN(a.y, b.y) - BRUSH_R; r.y2 = c.y1 + LV_MAX(a.y, b.y) + BRUSH_R;
    lv_obj_invalidate_area(s_canvas, &r);
}

static void recognize(lv_timer_t *t) {
    lv_timer_pause(t);
    uint8_t img[DIGIT_IN * DIGIT_IN];
    if (!s_have_model || !digit_prep(s_ink, PAD, PAD, img)) return;
    float conf;
    int64_t t0 = esp_timer_get_time();
    int d = digit_run(img, &conf);
    int us = (int)(esp_timer_get_time() - t0);
    lv_label_set_text_fmt(s_result, "Digit: %d  (%d%%)", d, (int)(conf * 100 + 0.5f));
    s_answered = true;
    ESP_LOGI(TAG, "%d at %.0f%%, inference %d us", d, conf * 100, us);
#if LOG_INPUT
    static const char shade[] = " .:-=+*#%@";
    char row[DIGIT_IN + 1] = { 0 };
    for (int y = 0; y < DIGIT_IN; y++) {
        for (int x = 0; x < DIGIT_IN; x++) row[x] = shade[img[y * DIGIT_IN + x] * 9 / 255];
        printf("  |%s|\n", row);
    }
#endif
}

static void pad_cb(lv_event_t *e) {
    lv_event_code_t code = lv_event_get_code(e);
    lv_indev_t *indev = lv_indev_active();
    if (code == LV_EVENT_PRESSED) {
        lv_timer_pause(s_settle);
        if (s_answered) pad_clear();           /* answered: the next touch starts a new digit */
        lv_obj_set_hidden(s_hint, true);
        s_stroking = false;
    }
    if ((code == LV_EVENT_PRESSED || code == LV_EVENT_PRESSING) && indev) {
        lv_point_t p;
        lv_area_t c;
        lv_indev_get_point(indev, &p);
        lv_obj_get_coords(s_canvas, &c);
        p.x -= c.x1; p.y -= c.y1;
        segment(s_stroking ? s_last : p, p);
        s_last = p;
        s_stroking = true;
    }
    if (code == LV_EVENT_RELEASED || code == LV_EVENT_PRESS_LOST) {
        s_stroking = false;
        lv_timer_reset(s_settle);
        lv_timer_resume(s_settle);
    }
}

static void clear_cb(lv_event_t *e) {
    lv_timer_pause(s_settle);
    pad_clear();
}

void digit_ui_create(lv_obj_t *parent) {
    s_have_model = digit_init();
    s_ink = heap_caps_malloc(PAD * PAD, MALLOC_CAP_SPIRAM);
    void *px = heap_caps_malloc(PAD * PAD * 2, MALLOC_CAP_SPIRAM);
    if (!s_ink || !px) { ESP_LOGE(TAG, "no memory for the pad"); return; }

    s_canvas = lv_canvas_create(parent);
    lv_canvas_set_buffer(s_canvas, px, PAD, PAD, LV_COLOR_FORMAT_RGB565);
    lv_obj_set_style_outline_width(s_canvas, 2, 0);
    lv_obj_set_style_outline_color(s_canvas, lv_color_hex(0x00C8FF), 0);
    lv_obj_align(s_canvas, LV_ALIGN_RIGHT_MID, -24, 0);
    lv_obj_set_clickable(s_canvas, true);
    lv_obj_add_event_cb(s_canvas, pad_cb, LV_EVENT_ALL, NULL);
    lv_obj_update_layout(s_canvas);   /* align_to below needs its final position */

    s_hint = lv_label_create(s_canvas);
    lv_label_set_text(s_hint, "Draw a digit");
    lv_obj_set_style_text_color(s_hint, lv_color_hex(0x607080), 0);
    lv_obj_set_style_text_font(s_hint, &lv_font_montserrat_24, 0);
    lv_obj_center(s_hint);

    s_result = lv_label_create(parent);
    lv_obj_set_style_text_color(s_result, lv_color_hex(0xE0F0FF), 0);
    lv_obj_set_style_text_font(s_result, &lv_font_montserrat_24, 0);
    lv_obj_align_to(s_result, s_canvas, LV_ALIGN_OUT_BOTTOM_LEFT, 0, 14);

    lv_obj_t *btn = lv_button_create(parent);
    lv_obj_t *bl = lv_label_create(btn);
    lv_label_set_text(bl, "Clear");
    lv_obj_align_to(btn, s_canvas, LV_ALIGN_OUT_BOTTOM_RIGHT, 0, 8);
    lv_obj_add_event_cb(btn, clear_cb, LV_EVENT_CLICKED, NULL);

    s_settle = lv_timer_create(recognize, SETTLE_MS, NULL);
    lv_timer_pause(s_settle);
    pad_clear();
}
