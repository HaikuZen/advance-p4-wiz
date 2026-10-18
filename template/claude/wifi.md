
## Wi-Fi (esp_hosted $hosted)

The P4 has no radio: Wi-Fi runs on the onboard ESP32-C6, over 4-bit SDIO (CLK
18, CMD 19, D0..D3 17..14, C6 reset GPIO 32). esp_wifi_remote forwards the plain
`esp_wifi_*` API to it, so **every `esp_wifi_*` call is an RPC to the C6**.

- `main/wifi.c/.h`: one Wi-Fi task owns every esp_wifi call. Others post it a
  message (`wifi_scan`, `wifi_join`, `wifi_forget`) and get callbacks
  (`wifi_on_status`, the scan callback), which run in the Wi-Fi task: take the
  LVGL lock in them before touching the UI. `wifi_start()` returns at once.
  Add new Wi-Fi work as a message to that task, not as calls from elsewhere.
- At boot it scans once (for the log), then joins the network saved on screen
  (NVS namespace `p4wifi`), else the menuconfig one, and rejoins with a backoff
  (1, 2, 4 ... 30 s) after each drop. A network set on screen is saved once it
  gets an IP.
- `main/wifi_ui.c`: the status button (top left) and the setup panel on
  `lv_layer_top()`: scan list, password, Connect, Forget.
- `main/Kconfig.projbuild`: `idf.py menuconfig` > CrowPanel Wi-Fi sets a
  fallback network. It lands in `sdkconfig`, which is gitignored. **Never put
  the SSID or password in `sdkconfig.defaults`**: that file is committed.
- The password ends up as **plain text** in `build/*.bin` and in the board's
  flash, either way. Don't share or upload such builds or flash backups.
- A failed Wi-Fi step logs and turns Wi-Fi off; it never reboots the app. Keep
  it that way: no `ESP_ERROR_CHECK` in the Wi-Fi code.
- Disconnect reasons (`esp_wifi_types_generic.h`): 15 handshake timeout (often a
  wrong password), 201 no AP found, 202 auth failed, 8 we left.
- The `CONFIG_ESP_HOSTED_*` lines in `sdkconfig.defaults` are for esp_hosted
  $hosted only. **esp_hosted 3.x renamed every option**: 2.x names under 3.x
  still build, but with the wrong SDIO pins and C6 reset pin, and the only sign
  is "unknown kconfig symbol" in the build log. After a config change, check
  that `sdkconfig` has D0 = 17 and reset = 32 (`p4wiz.py --check .` prints them).
- Elecrow ships the C6 with esp_hosted 2.12.3. esp_hosted 2.12.x matches it.
- esp_hosted warns that `CONFIG_FREERTOS_HZ` is 100 and it recommends 1000.
  Wi-Fi works at 100.
