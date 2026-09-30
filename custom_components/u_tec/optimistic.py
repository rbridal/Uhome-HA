"""Optimistic-update configuration resolver.

Standalone module with no project or Home Assistant imports, so it can be
unit-tested without loading the integration package or Home Assistant.
"""

from __future__ import annotations

from typing import Any, Mapping

CONF_OPTIMISTIC_LIGHTS = "optimistic_lights"
CONF_OPTIMISTIC_SWITCHES = "optimistic_switches"
CONF_OPTIMISTIC_LOCKS = "optimistic_locks"
DEFAULT_OPTIMISTIC = True

CONF_ADAPTIVE_AGGRESSIVE_LOCKS = "adaptive_aggressive_locks"
# Recommended on for locks: confirm commanded state with a short burst
# instead of waiting for the idle poll (U-Tec push is unreliable).
DEFAULT_ADAPTIVE_AGGRESSIVE = True


def _is_device_option_enabled(
    options: Mapping[str, Any],
    conf_key: str,
    device_id: str,
    default: bool,
) -> bool:
    """Resolve a True / False / list[device_id] option for one device."""
    value = options.get(conf_key, default)
    if isinstance(value, bool):
        return value
    return device_id in value


def is_optimistic_enabled(
    options: Mapping[str, Any],
    conf_key: str,
    device_id: str,
) -> bool:
    """Return True if optimistic updates are enabled for this device.

    value shape:
      - absent  -> DEFAULT_OPTIMISTIC (True)
      - True    -> all devices of this type optimistic
      - False   -> no devices of this type optimistic
      - list    -> only listed device IDs optimistic
    """
    return _is_device_option_enabled(options, conf_key, device_id, DEFAULT_OPTIMISTIC)


def is_adaptive_aggressive_enabled(
    options: Mapping[str, Any],
    device_id: str,
) -> bool:
    """Return True if Adaptive Aggressive polling is enabled for this lock."""
    return _is_device_option_enabled(
        options,
        CONF_ADAPTIVE_AGGRESSIVE_LOCKS,
        device_id,
        DEFAULT_ADAPTIVE_AGGRESSIVE,
    )


def push_asserts_state(push_data: Any, capability: str, attribute: str) -> bool:
    """Return True if a push payload actually carries the given capability state."""
    if not isinstance(push_data, dict):
        return False
    cap = push_data.get(capability)
    return isinstance(cap, dict) and attribute in cap
