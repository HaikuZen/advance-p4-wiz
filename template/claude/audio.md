
## Audio

- `main/audio.c/.h`: plain I2S into the speaker amps (BCLK 22, WS 21, DOUT 23),
  no codec. `audio_init()` after `board_init()`, then `audio_beep(hz, ms)`.
- The amps' enable, GPIO 30, is **active low** (10k pull-up: off by default).
