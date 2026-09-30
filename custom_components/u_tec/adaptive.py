"""Adaptive Aggressive confirmation polling for a single lock.

Standalone from Home Assistant entity code so the burst rules can be unit
tested without loading lock.py. The coordinator owns one AdaptivePoller.
"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_call_later
from homeassistant.util import dt as dt_util

from .const import (
    ADAPTIVE_AGGRESSIVE_INITIAL_DELAY,
    ADAPTIVE_AGGRESSIVE_MAX_ATTEMPTS,
    ADAPTIVE_AGGRESSIVE_TIMEOUT_VALUE,
    DEFAULT_SCAN_INTERVAL,
    SIGNAL_ADAPTIVE_OUTCOME,
    SIGNAL_DEVICE_UPDATE,
)

_LOGGER = logging.getLogger(__name__)

_SKIP_OUTCOME = {"unload", "restarted", "device gone"}


def outcome_value(reason: str, attempts: int) -> int | None:
    """Map a burst stop to the 0-6 statistic.

    0 = push cancelled the burst (webhook won).
    1-5 = polls until the commanded state was confirmed.
    6 = gave up (max attempts or next delay >= idle).
    """
    if reason in _SKIP_OUTCOME:
        return None
    if reason == "push":
        return 0
    if reason == "confirmed":
        return min(ADAPTIVE_AGGRESSIVE_MAX_ATTEMPTS, max(1, int(attempts)))
    return ADAPTIVE_AGGRESSIVE_TIMEOUT_VALUE


class AdaptivePoller:
    """Per-device Fibonacci confirmation bursts (1, 2, 3, 5, 8s)."""

    def __init__(self, coordinator) -> None:
        self.coordinator = coordinator
        self._bursts: dict[str, dict[str, Any]] = {}
        self.last_outcome: dict[str, dict[str, Any]] = {}

    def idle_interval_seconds(self) -> int:
        interval = self.coordinator.update_interval
        if interval is None:
            return DEFAULT_SCAN_INTERVAL
        return max(1, int(interval.total_seconds()))

    def cancel(self, device_id: str, reason: str) -> None:
        burst = self._bursts.pop(device_id, None)
        if burst is None:
            return
        unsub = burst.get("unsub")
        if unsub:
            unsub()
        attempts = int(burst.get("attempt", 0))
        _LOGGER.info(
            "Adaptive aggressive stopped for %s after %s attempt(s): %s",
            device_id,
            attempts,
            reason,
        )
        self._record_outcome(device_id, reason, attempts, burst)

    def cancel_all(self, reason: str = "unload") -> None:
        for device_id in list(self._bursts):
            self.cancel(device_id, reason)

    def _record_outcome(
        self,
        device_id: str,
        reason: str,
        attempts: int,
        burst: dict[str, Any],
    ) -> None:
        value = outcome_value(reason, attempts)
        if value is None:
            return
        self.last_outcome[device_id] = {
            "value": value,
            "attempts": attempts,
            "reason": reason,
            "expected_locked": burst.get("expected_locked"),
            "at": dt_util.utcnow().isoformat(),
        }
        _LOGGER.info(
            "Adaptive aggressive outcome for %s: %s (reason=%s attempts=%s)",
            device_id,
            value,
            reason,
            attempts,
        )
        async_dispatcher_send(
            self.coordinator.hass,
            f"{SIGNAL_ADAPTIVE_OUTCOME}_{device_id}",
        )

    def start(self, device_id: str, expected_locked: bool) -> None:
        idle = self.idle_interval_seconds()
        initial = ADAPTIVE_AGGRESSIVE_INITIAL_DELAY
        if initial >= idle:
            _LOGGER.info(
                "Adaptive aggressive not started for %s: initial delay %ss >= idle %ss",
                device_id,
                initial,
                idle,
            )
            return

        if device_id in self._bursts:
            self.cancel(device_id, "restarted")

        # prev_delay starts equal to initial so the sequence is 1, 2, 3, 5, 8
        # rather than 1, 1, 2, 3, 5.
        self._bursts[device_id] = {
            "expected_locked": expected_locked,
            "attempt": 0,
            "delay": initial,
            "prev_delay": initial,
            "unsub": None,
        }
        _LOGGER.info(
            "Adaptive aggressive started for %s: expected_locked=%s idle=%ss",
            device_id,
            expected_locked,
            idle,
        )
        self._schedule(device_id, initial)

    def cancel_if_confirmed(self, device_id: str, device) -> None:
        burst = self._bursts.get(device_id)
        if burst is None:
            return
        if getattr(device, "is_locked", None) == burst["expected_locked"]:
            self.cancel(device_id, "confirmed")

    def _schedule(self, device_id: str, delay: int) -> None:
        burst = self._bursts.get(device_id)
        if burst is None:
            return

        async def _fire(_now) -> None:
            await self.async_tick(device_id)

        burst["unsub"] = async_call_later(self.coordinator.hass, delay, _fire)

    async def async_tick(self, device_id: str) -> None:
        """Run one poll after the Adaptive Aggressive timer ends."""
        burst = self._bursts.get(device_id)
        if burst is None:
            return

        burst["unsub"] = None
        burst["attempt"] = int(burst["attempt"]) + 1
        delay = int(burst["delay"])
        expected = bool(burst["expected_locked"])
        _LOGGER.info(
            "Adaptive aggressive timer ended for %s: attempt %s/%s after %ss",
            device_id,
            burst["attempt"],
            ADAPTIVE_AGGRESSIVE_MAX_ATTEMPTS,
            delay,
        )

        device = self.coordinator.devices.get(device_id)
        if device is None:
            self.cancel(device_id, "device gone")
            return

        confirmed = False
        try:
            response = await self.coordinator.api.get_device_state([device_id], None)
            from .coordinator import _raise_for_error_payload

            _raise_for_error_payload(response)
            if response and "payload" in response:
                for device_data in response["payload"].get("devices", []):
                    if device_data.get("id") == device_id:
                        await device.update_state_data(device_data)
                        break
            self.coordinator.consecutive_update_failures = 0
            actual = getattr(device, "is_locked", None)
            _LOGGER.info(
                "Adaptive aggressive result for %s: locked=%s expected=%s",
                device_id,
                actual,
                expected,
            )
            async_dispatcher_send(
                self.coordinator.hass,
                f"{SIGNAL_DEVICE_UPDATE}_{device_id}",
                device.get_state_data(),
            )
            confirmed = actual == expected
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning(
                "Adaptive aggressive poll failed for %s: %s", device_id, err
            )

        if confirmed:
            snapshot = device.get_state_data()
            current = dict(self.coordinator.data) if self.coordinator.data else {}
            current[device_id] = snapshot
            self.coordinator.async_set_updated_data(current)
            self.cancel(device_id, "confirmed")
            return

        if burst["attempt"] >= ADAPTIVE_AGGRESSIVE_MAX_ATTEMPTS:
            self.cancel(device_id, "max attempts")
            return

        prev_delay = int(burst.get("prev_delay", delay))
        next_delay = delay + prev_delay
        idle = self.idle_interval_seconds()
        if next_delay >= idle:
            self.cancel(
                device_id,
                f"next delay {next_delay}s >= idle {idle}s",
            )
            return

        burst["prev_delay"] = delay
        burst["delay"] = next_delay
        self._schedule(device_id, next_delay)
