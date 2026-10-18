#pragma once
/* the AI module: handwritten digits, an int8 CNN run by ESP-DL on the P4 */
#include <stdbool.h>
#include <stdint.h>
#include "lvgl.h"

#ifdef __cplusplus
extern "C" {
#endif

/* load the model embedded in the app (models/digit.espdl); false if it won't load */
bool digit_init(void);
/* a 28x28 image (0..255, row by row) -> the digit 0..9, -1 without a model.
 * conf (optional): the softmax probability of that digit */
int digit_run(const uint8_t *img28, float *conf);
/* the drawing pad, its answer and a Clear button; loads the model (digit_init) too.
 * Call holding the LVGL lock */
void digit_ui_create(lv_obj_t *parent);

#ifdef __cplusplus
}
#endif
