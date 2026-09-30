"""The Uhome integration."""

from __future__ import annotations

from datetime import timedelta
import logging

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_CLIENT_ID, CONF_CLIENT_SECRET, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import aiohttp_client, config_entry_oauth2_flow
import homeassistant.helpers.config_validation as cv
from utec_py.api import UHomeApi

from . import api
from .const import (
    CONF_DISCOVERY_INTERVAL,
    CONF_PUSH_DEVICES,
    CONF_PUSH_ENABLED,
    CONF_SCAN_INTERVAL,
    DEFAULT_DISCOVERY_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
    YAML_CONFIG_KEY,
)
from .coordinator import UhomeDataUpdateCoordinator

_PLATFORMS: list[Platform] = [
    Platform.LOCK,
    Platform.LIGHT,
    Platform.SWITCH,
    Platform.SENSOR,
]

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema(
            {
                vol.Optional(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL): vol.All(
                    cv.positive_int, vol.Range(min=1)
                ),
                vol.Optional(CONF_DISCOVERY_INTERVAL, default=DEFAULT_DISCOVERY_INTERVAL): vol.All(
                    cv.positive_int, vol.Range(min=10)
                ),
            }
        )
    },
    extra=vol.ALLOW_EXTRA,
)


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Read configuration.yaml settings and store for use by config entries."""
    hass.data.setdefault(DOMAIN, {})
    if DOMAIN in config:
        hass.data[DOMAIN][YAML_CONFIG_KEY] = config[DOMAIN]
        if CONF_SCAN_INTERVAL in config[DOMAIN]:
            _LOGGER.warning(
                "configuration.yaml scan_interval for u_tec is deprecated; "
                "configure the poll interval via Configure → Polling Interval. "
                "YAML applies only until a UI value is saved; after that the UI "
                "value takes permanent precedence (remove the options key to "
                "fall back to YAML again)."
            )
        _LOGGER.debug(
            "Loaded u_tec config from configuration.yaml: scan_interval=%s, discovery_interval=%s",
            config[DOMAIN].get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
            config[DOMAIN].get(CONF_DISCOVERY_INTERVAL, DEFAULT_DISCOVERY_INTERVAL),
        )
    return True


def _resolve_scan_interval(hass: HomeAssistant, entry: ConfigEntry) -> int:
    """Prefer an explicitly saved UI option, then configuration.yaml, then default.

    scan_interval is only written to entry.options when the user saves the
    Polling Interval options step — not on initial entry create — so YAML
    continues to apply until the user opts into the UI setting. Values are
    clamped to [MIN_SCAN_INTERVAL, MAX_SCAN_INTERVAL].
    """
    if CONF_SCAN_INTERVAL in entry.options:
        value = int(entry.options[CONF_SCAN_INTERVAL])
    else:
        yaml_config = hass.data.get(DOMAIN, {}).get(YAML_CONFIG_KEY, {})
        value = int(yaml_config.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL))
    return max(MIN_SCAN_INTERVAL, min(MAX_SCAN_INTERVAL, value))


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Uhome from a config entry."""
    implementation = (
        await config_entry_oauth2_flow.async_get_config_entry_implementation(
            hass, entry
        )
    )

    session = config_entry_oauth2_flow.OAuth2Session(hass, entry, implementation)

    auth_data = api.AsyncConfigEntryAuth(
        aiohttp_client.async_get_clientsession(hass), session
    )

    Uhomeapi = UHomeApi(auth_data)

    # Explicit UI option > configuration.yaml > built-in default.
    yaml_config = hass.data.get(DOMAIN, {}).get(YAML_CONFIG_KEY, {})
    scan_interval = _resolve_scan_interval(hass, entry)
    discovery_interval = yaml_config.get(
        CONF_DISCOVERY_INTERVAL, DEFAULT_DISCOVERY_INTERVAL
    )

    coordinator = UhomeDataUpdateCoordinator(
        hass,
        Uhomeapi,
        config_entry=entry,
        scan_interval=scan_interval,
        discovery_interval=discovery_interval,
    )

    # Initial discovery populates self.devices before the first state poll.
    await coordinator.async_discover_devices()
    _LOGGER.debug("Initial device discovery complete")

    await coordinator.async_config_entry_first_refresh()
    _LOGGER.debug("First Refresh Completed")

    # Periodic re-discovery runs on a long interval to pick up added/removed devices.
    await coordinator.async_start_periodic_discovery()

    # Initialize webhook handler
    webhook_handler = api.AsyncPushUpdateHandler(hass, Uhomeapi, entry.entry_id)
    _LOGGER.debug("Webhook handler initialised")

    # Check if push notifications are enabled in options
    push_enabled = entry.options.get(CONF_PUSH_ENABLED, True)
    push_devices = entry.options.get(CONF_PUSH_DEVICES, [])

    # Set push devices in coordinator
    coordinator.push_devices = push_devices

    # Register webhook if push is enabled
    if push_enabled:
        _LOGGER.debug("Push updates enabled")
        await webhook_handler.async_register_webhook(auth_data)
        _LOGGER.debug("Webhook registered complete")

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "api": Uhomeapi,
        "coordinator": coordinator,
        "auth_data": auth_data,
        "webhook_handler": webhook_handler,
        # Track previous push_enabled so async_update_options can detect a real
        # change. entry.options reflects current state; without a stored prior
        # we can't tell a toggle from a no-op data update (e.g. OAuth refresh).
        "push_enabled": push_enabled,
    }

    await hass.config_entries.async_forward_entry_setups(entry, _PLATFORMS)
    # Listener fires on ANY entry update (data or options). The handler is
    # responsible for filtering down to actual option changes — see
    # async_update_options. Calling async_reload from this listener on every
    # update would loop on OAuth token refreshes, which the integration cannot
    # recover from without a working async_unload_entry.
    entry.async_on_unload(entry.add_update_listener(async_update_options))
    # Unregister the webhook when the entry is unloaded
    entry.async_on_unload(webhook_handler.unregister_webhook)
    # Stop periodic discovery when the entry is unloaded
    entry.async_on_unload(coordinator.async_stop_periodic_discovery)
    entry.async_on_unload(coordinator.async_stop_adaptive_polls)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, _PLATFORMS)
    if unload_ok:
        hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    return unload_ok


async def async_update_options(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update.

    Reconciles webhook registration, push_devices, and poll interval inline
    based on the new options. Deliberately does NOT call async_reload — token
    refreshes update entry.data and would otherwise trigger a reload on every
    refresh.
    """
    entry_data = hass.data[DOMAIN][entry.entry_id]
    webhook_handler = entry_data["webhook_handler"]
    coordinator = entry_data["coordinator"]
    auth_data = entry_data["auth_data"]

    old_push_enabled = entry_data.get("push_enabled", True)
    new_push_enabled = entry.options.get(CONF_PUSH_ENABLED, True)

    coordinator.push_devices = entry.options.get(CONF_PUSH_DEVICES, [])

    if old_push_enabled != new_push_enabled:
        if new_push_enabled:
            await webhook_handler.async_register_webhook(auth_data)
        else:
            await webhook_handler.unregister_webhook()
        entry_data["push_enabled"] = new_push_enabled

    # Apply poll interval without a full reload. Setting update_interval alone
    # may not reschedule an already-pending timer on all HA versions, so call
    # _schedule_refresh when available (private HA API; getattr guards crashes).
    if CONF_SCAN_INTERVAL in entry.options:
        new_interval = max(
            MIN_SCAN_INTERVAL,
            min(MAX_SCAN_INTERVAL, int(entry.options[CONF_SCAN_INTERVAL])),
        )
        coordinator.update_interval = timedelta(seconds=new_interval)
        schedule = getattr(coordinator, "_schedule_refresh", None)
        if callable(schedule):
            schedule()
        _LOGGER.debug("Updated poll interval to %ds", new_interval)
