#pragma once
/* a finger drawing -> the model's MNIST-style 28x28 input. Pure C, no IDF:
 * tools/test_digit_prep.py compiles it on the host */
#include <stdbool.h>
#include <stdint.h>

#define DIGIT_IN 28

/* ink: w x h, 0 = paper, anything else = ink. out: 28x28, 0..255, row by row.
 * false if there is no ink at all */
bool digit_prep(const uint8_t *ink, int w, int h, uint8_t out[DIGIT_IN * DIGIT_IN]);
