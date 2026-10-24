#pragma once
/* a BME690 on the board's I2C connector (SDA 45, SCL 46, the touch's bus).
 * Wire CS to 3.3 V (I2C mode) and SDO to GND (0x76) or 3.3 V (0x77) */
#include <stdbool.h>
#include "lvgl.h"

typedef struct {
    float temp_c, hum_pct, press_hpa;
    float gas_ohm;     /* the heated plate's resistance; 0 until the heater is stable */
    bool valid;        /* false until the first reading */
} bme690_data_t;

/* find the sensor (0x76, then 0x77) and read it every few seconds in its own
 * task; returns at once. Without a sensor it logs and does nothing else */
void bme690_start(void);
/* the latest reading */
bme690_data_t bme690_latest(void);
/* the readings card on the demo screen; call holding the LVGL lock */
void bme690_ui_create(lv_obj_t *parent);
