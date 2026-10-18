#!/bin/bash
# assemble_reference.sh - the wiring a wizard must reproduce: base + Wi-Fi + audio.
# Build-tested on ESP-IDF v6.1 (2026-10-18) with both esp_hosted options.
#
#   tools/assemble_reference.sh <out_dir> <2|3>     # 2 = esp_hosted 2.12.x (recommended), 3 = 3.x
#   cd <out_dir> && ../tools/idf61.sh idf.py set-target esp32p4 build   (or your own IDF 6.x env)
set -e
W="$(cd "$(dirname "$0")/.." && pwd)"; D=$1; H=${2:-2}
[ -n "$D" ] || { echo "usage: $0 <out_dir> <2|3>"; exit 1; }
[ -e "$D" ] && { echo "$D exists"; exit 1; }
cp -r "$W/template/base" "$D"
cp "$W"/template/modules/wifi/wifi.[ch] "$W"/template/modules/wifi/wifi_ui.c "$W"/template/modules/wifi/Kconfig.projbuild "$W"/template/modules/audio/audio.[ch] "$D/main/"
grep -v '^#' "$W/template/modules/wifi/idf_component.hosted$H.yml" >> "$D/main/idf_component.yml"
{ echo; cat "$W/template/modules/wifi/sdkconfig.hosted$H"; } >> "$D/sdkconfig.defaults"
sed -i 's/SRCS "main.c" "board.c"/SRCS "main.c" "board.c" "wifi.c" "wifi_ui.c" "audio.c"/; s/esp_hw_support)/esp_hw_support esp_wifi esp_netif esp_event nvs_flash esp_driver_i2s)/' "$D/main/CMakeLists.txt"
python3 - "$D/main/main.c" <<'PY'
import sys
p = sys.argv[1]; s = open(p).read()
s = s.replace('#include "esp_log.h"', '#include "esp_log.h"\n#include "wifi.h"\n#include "audio.h"', 1)
s = s.replace("        build_ui();\n", "        build_ui();\n        wifi_ui_create(lv_screen_active());\n", 1)
a = "        lvgl_port_unlock();\n    }\n}"
assert s.count(a) == 1
s = s.replace(a, "        lvgl_port_unlock();\n    }\n    audio_init();\n    audio_beep(880, 150);\n    wifi_start();\n}")
open(p, "w").write(s)
PY
echo "assembled $D (esp_hosted $H.x)"
