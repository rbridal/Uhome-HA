"""Constants for the Uhome integration."""

from datetime import timedelta

from .optimistic import (
    CONF_ADAPTIVE_AGGRESSIVE_LOCKS,
    CONF_OPTIMISTIC_LIGHTS,
    CONF_OPTIMISTIC_SWITCHES,
    CONF_OPTIMISTIC_LOCKS,
    DEFAULT_ADAPTIVE_AGGRESSIVE,
    DEFAULT_OPTIMISTIC,
    is_adaptive_aggressive_enabled,
    is_optimistic_enabled,
    push_asserts_state,
)

DOMAIN = "u_tec"

OPTIMISTIC_TIMEOUT = timedelta(seconds=30)
MAX_CONSECUTIVE_UPDATE_FAILURES = 2

CONF_SCAN_INTERVAL = "scan_interval"
CONF_DISCOVERY_INTERVAL = "discovery_interval"

DEFAULT_SCAN_INTERVAL = 10  # seconds
DEFAULT_DISCOVERY_INTERVAL = 300  # seconds (5 minutes)
MIN_SCAN_INTERVAL = 10
MAX_SCAN_INTERVAL = 3600

# Adaptive Aggressive lock confirmation. After a lock/unlock command, poll
# that one device on 1, 2, 4, 8, 16s until the API reports the commanded
# state. Cap at 5 attempts and never schedule a delay >= the idle scan
# interval.
ADAPTIVE_AGGRESSIVE_INITIAL_DELAY = 1
ADAPTIVE_AGGRESSIVE_MAX_ATTEMPTS = 5
# Sensor encoding: 0=push, 1-5=polls until confirm, 6=timed out.
ADAPTIVE_AGGRESSIVE_TIMEOUT_VALUE = 6

YAML_CONFIG_KEY = "_yaml_config"

OAUTH2_AUTHORIZE = "https://oauth.u-tec.com/authorize"
OAUTH2_TOKEN = "https://oauth.u-tec.com/token"

CONF_PUSH_ENABLED = "push_enabled"
CONF_PUSH_DEVICES = "push_devices"
CONF_HA_DEVICES = "HomeAssistant_devices"
DEFAULT_API_SCOPE = "openapi"

API_BASE_URL = "https://api.u-tec.com/action"

SIGNAL_NEW_DEVICE = f"{DOMAIN}_new_device"
SIGNAL_DEVICE_UPDATE = f"{DOMAIN}_device_update"
SIGNAL_ADAPTIVE_OUTCOME = f"{DOMAIN}_adaptive_outcome"

WEBHOOK_ID_PREFIX = "u_tec_push_"
WEBHOOK_HANDLER = "u_tec_webhook_handler"
