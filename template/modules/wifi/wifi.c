/* wifi.c - Wi-Fi through the onboard ESP32-C6 (esp_hosted): the plain
 * esp_wifi API, forwarded to the C6 over SDIO by esp_wifi_remote. */
#include "wifi.h"
#include "esp_wifi.h"
#include "esp_netif.h"
#include "esp_event.h"
#include "nvs_flash.h"
#include "esp_log.h"

static const char *TAG = "wifi";

void wifi_scan_once(void) {
    esp_err_t err = nvs_flash_init();
    if (err == ESP_ERR_NVS_NO_FREE_PAGES || err == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_ERROR_CHECK(nvs_flash_erase());
        ESP_ERROR_CHECK(nvs_flash_init());
    }
    ESP_ERROR_CHECK(esp_netif_init());
    ESP_ERROR_CHECK(esp_event_loop_create_default());
    esp_netif_create_default_wifi_sta();
    wifi_init_config_t cfg = WIFI_INIT_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_wifi_init(&cfg));
    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_STA));
    ESP_ERROR_CHECK(esp_wifi_start());
    ESP_ERROR_CHECK(esp_wifi_scan_start(NULL, true));   /* blocking */
    uint16_t n = 0;
    esp_wifi_scan_get_ap_num(&n);
    wifi_ap_record_t ap[10];
    uint16_t max = 10;
    esp_wifi_scan_get_ap_records(&max, ap);
    ESP_LOGI(TAG, "%u networks, showing %u", n, max);
    for (int i = 0; i < max; i++) ESP_LOGI(TAG, "  %-32s ch %2d rssi %d", (char *)ap[i].ssid, ap[i].primary, ap[i].rssi);
}
