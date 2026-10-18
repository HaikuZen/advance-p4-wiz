/* digit_model.cpp - the ESP-DL side of the AI module: the int8 CNN from
 * tools/train_digit_model.py, embedded in the app's rodata (16-byte aligned,
 * as ESP-DL requires; see main/CMakeLists.txt). */
#include "digit.h"
#include "digit_prep.h"
#include "dl_model_base.hpp"
#include "esp_log.h"
#include <cmath>

extern const uint8_t digit_espdl[] asm("_binary_digit_espdl_start");

static const char *TAG = "digit";
static dl::Model *s_model;
static dl::TensorBase *s_in, *s_out;

extern "C" bool digit_init(void)
{
    s_model = new dl::Model((const char *)digit_espdl, fbs::MODEL_LOCATION_IN_FLASH_RODATA);
    s_in = s_model->get_inputs().begin()->second;
    s_out = s_model->get_outputs().begin()->second;
    if (s_in->get_size() != DIGIT_IN * DIGIT_IN || s_out->get_size() != 10 ||
        s_in->dtype != dl::DATA_TYPE_INT8 || s_out->dtype != dl::DATA_TYPE_INT8) {
        ESP_LOGE(TAG, "unexpected model: in %d x %s, out %d x %s", s_in->get_size(), dl::dtype_to_string(s_in->dtype),
                 s_out->get_size(), dl::dtype_to_string(s_out->dtype));
        delete s_model;
        s_model = nullptr;
        return false;
    }
    ESP_LOGI(TAG, "model loaded: in exponent %d, out exponent %d", s_in->get_exponent(), s_out->get_exponent());
    return true;
}

extern "C" int digit_run(const uint8_t *img28, float *conf)
{
    if (!s_model) return -1;
    /* the model was trained on 0..1 floats; ESP-DL wants them quantized with the input's exponent */
    const float inv_scale = DL_RESCALE(s_in->get_exponent());
    int8_t *in = (int8_t *)s_in->data;
    for (int i = 0; i < DIGIT_IN * DIGIT_IN; i++) in[i] = dl::quantize<int8_t>(img28[i] / 255.0f, inv_scale);

    s_model->run();

    const float scale = DL_SCALE(s_out->get_exponent());
    const int8_t *out = (const int8_t *)s_out->data;
    int best = 0;
    for (int i = 1; i < 10; i++)
        if (out[i] > out[best]) best = i;
    if (conf) {
        float sum = 0;
        for (int i = 0; i < 10; i++) sum += expf((out[i] - out[best]) * scale);
        *conf = 1.0f / sum;
    }
    return best;
}
