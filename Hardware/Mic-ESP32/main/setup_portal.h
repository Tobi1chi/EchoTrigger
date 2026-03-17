#pragma once

#include "esp_err.h"

typedef enum {
    SETUP_PORTAL_MODE_AP = 0,
    SETUP_PORTAL_MODE_STA = 1,
} setup_portal_mode_t;

esp_err_t setup_portal_start(setup_portal_mode_t mode);
