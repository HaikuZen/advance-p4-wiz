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
