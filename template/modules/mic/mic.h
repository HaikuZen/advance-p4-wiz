#pragma once
/* the board's PDM microphone (Elecrow's wiki: clock GPIO 24, data GPIO 26),
 * read as 16 kHz 16-bit PCM by the P4's I2S0, the only port with PDM RX */
#include <stdint.h>
#include "lvgl.h"

#define MIC_RATE 16000

/* a block of mono samples, in the mic task; keep it short */
typedef void (*mic_block_cb_t)(const int16_t *samples, int n);

/* start the mic and its reader task; returns at once. Logs the level every second */
void mic_start(void);
/* the last block's level in dBFS (0 = full scale; -100 with no signal) */
float mic_level_db(void);
/* every block, to whoever wants the sound (set it before mic_start) */
void mic_on_block(mic_block_cb_t cb);
/* the level bar on the demo screen; call holding the LVGL lock */
void mic_ui_create(lv_obj_t *parent);
