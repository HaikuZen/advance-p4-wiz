
## AI: handwritten digits (ESP-DL)

- `main/digit.c/.h`: the drawing pad, its answer and a Clear button
  (`digit_ui_create`, under the LVGL lock; it loads the model too).
  `digit_run(img28, &conf)` runs the model on any 28x28 image.
- `main/digit_prep.c/.h`: plain C, turns the strokes into an MNIST-like 28x28
  (crop, scale to 20x20, centre of mass). `main/digit_model.cpp`: ESP-DL.
- `main/models/digit.espdl`: the int8 model, made by
  `tools/train_digit_model.py` in the wizard repo (MNIST, esp-ppq). To retrain
  or swap it, see that script; `tools/test_digit_prep.py` scores a model
  through `digit_prep.c` on the host.
- ESP-DL needs the model **16-byte aligned**: `main/CMakeLists.txt` embeds it
  with `target_add_aligned_binary_data`, after `idf_component_register`.
  `EMBED_FILES` doesn't guarantee the alignment.
- ESP-DL makes the app ~2.6 MB: `partitions.csv` has a 6 MB factory partition
  (`CONFIG_PARTITION_TABLE_CUSTOM`). Grow it there if the app grows.
- The log prints what the model saw (ASCII art) and the answer; one inference
  takes ~3 ms at 360 MHz.
