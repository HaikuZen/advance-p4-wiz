
## Microphone (PDM)

- A PDM microphone on GPIO 24 (clock) and GPIO 26 (data), with no codec
  (`PIN_MIC_CLK`, `PIN_MIC_DATA` in `board_pins.h`). Seen working on the bench
  10.1" (2026-10-25): left slot, about -60 dBFS in a quiet room, -46 for a voice
  nearby.
- `main/mic.c/.h`: I2S0 in PDM RX mode, which turns the 1-bit stream into
  16 kHz 16-bit PCM in hardware (`I2S_PDM_DATA_FMT_PCM`). A task (priority 4)
  reads 20 ms blocks and measures them (`mic_level_db()`, in dBFS). It hands
  each block to `mic_on_block(cb)` and moves a level bar
  (`mic_ui_create`, bottom left) 10 times a second. It logs the level once a
  second, or "the data line is flat" if nothing comes in.
- **I2S0 is the only port with PDM RX** on the P4, so the mic owns it. With
  the speaker too, `audio.c` runs on I2S1 (heard working on the board). Don't
  move either.
- Which slot the mic talks in depends on its select pin, which isn't
  documented: both slots are read, and the first block with sound picks the
  louder one (the log says which). Once known, read mono from that slot.
- The block callback runs in the mic task: copy the samples out, don't block
  in it, and take the LVGL lock before touching the UI.
- Speech recognition, wake words, etc. sit on top of `mic_on_block`
  (Espressif's ESP-SR supports the P4); the module stops at clean PCM.
