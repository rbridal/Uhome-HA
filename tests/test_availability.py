"""Tests for entity availability (device offline + consecutive poll failures)."""

from unittest.mock import MagicMock

from custom_components.u_tec.const import (
    CONF_MAX_UPDATE_FAILURES,
    CONF_OPTIMISTIC_LOCKS,
    DEFAULT_MAX_UPDATE_FAILURES,
)
from custom_components.u_tec.lock import UhomeLockEntity
from tests.common import make_config_entry, make_fake_lock


def _coord_with_lock(*, options: dict | None = None):
    entry = make_config_entry(
        options={CONF_OPTIMISTIC_LOCKS: True, **(options or {})}
    )
    lock = make_fake_lock("lock-1", is_locked=True)
    lock.available = True
    coord = MagicMock()
    coord.devices = {"lock-1": lock}
    coord.config_entry = entry
    coord.last_update_success = True
    coord.consecutive_update_failures = 0
    threshold = int(
        entry.options.get(CONF_MAX_UPDATE_FAILURES, DEFAULT_MAX_UPDATE_FAILURES)
    )
    coord.max_update_failures = threshold
    coord.poll_healthy_enough = True
    coord.data = {}
    return coord, lock


def test_available_when_healthy():
    coord, lock = _coord_with_lock()
    ent = UhomeLockEntity(coord, "lock-1")
    assert ent.available is True


def test_unavailable_after_one_failure_by_default():
    """Default threshold is 1 — a single failed poll marks entities unavailable."""
    coord, lock = _coord_with_lock()
    coord.consecutive_update_failures = 1
    coord.poll_healthy_enough = (
        coord.consecutive_update_failures < coord.max_update_failures
    )
    coord.last_update_success = False
    ent = UhomeLockEntity(coord, "lock-1")
    assert ent.available is False


def test_available_through_single_failure_when_threshold_two():
    """Threshold 2 tolerates one blip."""
    coord, lock = _coord_with_lock(options={CONF_MAX_UPDATE_FAILURES: 2})
    coord.consecutive_update_failures = 1
    coord.poll_healthy_enough = (
        coord.consecutive_update_failures < coord.max_update_failures
    )
    coord.last_update_success = False
    ent = UhomeLockEntity(coord, "lock-1")
    assert ent.available is True


def test_unavailable_after_threshold_reached():
    coord, lock = _coord_with_lock(options={CONF_MAX_UPDATE_FAILURES: 2})
    coord.consecutive_update_failures = 2
    coord.poll_healthy_enough = (
        coord.consecutive_update_failures < coord.max_update_failures
    )
    coord.last_update_success = False
    ent = UhomeLockEntity(coord, "lock-1")
    assert ent.available is False


def test_unavailable_when_device_offline():
    coord, lock = _coord_with_lock()
    lock.available = False
    ent = UhomeLockEntity(coord, "lock-1")
    assert ent.available is False


def test_poll_healthy_enough_property():
    """Coordinator helper mirrors the consecutive-failure threshold from options."""
    from custom_components.u_tec.coordinator import UhomeDataUpdateCoordinator

    c = object.__new__(UhomeDataUpdateCoordinator)
    c.config_entry = make_config_entry(options={CONF_MAX_UPDATE_FAILURES: 2})
    c.consecutive_update_failures = 0
    assert c.poll_healthy_enough is True
    c.consecutive_update_failures = 1
    assert c.poll_healthy_enough is True
    c.consecutive_update_failures = 2
    assert c.poll_healthy_enough is False

    c.config_entry = make_config_entry(options={})  # default threshold 1
    c.consecutive_update_failures = 1
    assert c.poll_healthy_enough is False
