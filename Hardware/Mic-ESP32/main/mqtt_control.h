#pragma once

#include <stdbool.h>

#include "esp_err.h"

esp_err_t mqtt_control_init(void);
void mqtt_control_set_network_ready(bool ready);
void mqtt_control_publish_boot_state(void);
