"""Tests for consecutive poll-failure tracking and push/auth interaction."""

import pytest

from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import UpdateFailed
from utec_py.exceptions import ApiError, AuthenticationError

from custom_components.u_tec.const import CONF_MAX_UPDATE_FAILURES
from custom_components.u_tec.coordinator import UhomeDataUpdateCoordinator
from tests.common import make_config_entry, make_fake_switch


@pytest.fixture
async def coordinator(hass, mock_uhome_api):
    """Default threshold is 2 (matches main after #61)."""
    entry = make_config_entry()
    entry.add_to_hass(hass)
    return UhomeDataUpdateCoordinator(
        hass, mock_uhome_api, config_entry=entry, scan_interval=10, discovery_interval=300,
    )


@pytest.fixture
async def coordinator_threshold_1(hass, mock_uhome_api):
    entry = make_config_entry(options={CONF_MAX_UPDATE_FAILURES: 1})
    entry.add_to_hass(hass)
    return UhomeDataUpdateCoordinator(
        hass, mock_uhome_api, config_entry=entry, scan_interval=10, discovery_interval=300,
    )


@pytest.fixture
async def coordinator_threshold_3(hass, mock_uhome_api):
    entry = make_config_entry(options={CONF_MAX_UPDATE_FAILURES: 3})
    entry.add_to_hass(hass)
    return UhomeDataUpdateCoordinator(
        hass, mock_uhome_api, config_entry=entry, scan_interval=10, discovery_interval=300,
    )


async def test_default_threshold_tolerates_one_failure(
    coordinator, mock_uhome_api,
):
    """Default of 2 keeps entities available through a single failed poll."""
    sw = make_fake_switch("sw-1")
    sw.get_state_data = lambda: {}
    coordinator.devices["sw-1"] = sw

    mock_uhome_api.get_device_state.side_effect = ApiError(500, "blip")
    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()
    assert coordinator.consecutive_update_failures == 1
    assert coordinator.poll_healthy_enough is True

    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()
    assert coordinator.consecutive_update_failures == 2
    assert coordinator.poll_healthy_enough is False

    mock_uhome_api.get_device_state.side_effect = None
    mock_uhome_api.get_device_state.return_value = {
        "payload": {"devices": [{"id": "sw-1", "states": []}]}
    }
    await coordinator._async_update_data()
    assert coordinator.consecutive_update_failures == 0
    assert coordinator.poll_healthy_enough is True


async def test_threshold_1_fails_on_first_poll(
    coordinator_threshold_1, mock_uhome_api,
):
    """Threshold 1 is classic fail-fast."""
    coord = coordinator_threshold_1
    sw = make_fake_switch("sw-1")
    sw.get_state_data = lambda: {}
    coord.devices["sw-1"] = sw

    mock_uhome_api.get_device_state.side_effect = ApiError(500, "blip")
    with pytest.raises(UpdateFailed):
        await coord._async_update_data()
    assert coord.consecutive_update_failures == 1
    assert coord.poll_healthy_enough is False


async def test_threshold_3_tolerates_two_failures(
    coordinator_threshold_3, mock_uhome_api,
):
    coord = coordinator_threshold_3
    sw = make_fake_switch("sw-1")
    sw.get_state_data = lambda: {}
    coord.devices["sw-1"] = sw

    mock_uhome_api.get_device_state.side_effect = ApiError(500, "blip")
    with pytest.raises(UpdateFailed):
        await coord._async_update_data()
    assert coord.consecutive_update_failures == 1
    assert coord.poll_healthy_enough is True

    with pytest.raises(UpdateFailed):
        await coord._async_update_data()
    assert coord.consecutive_update_failures == 2
    assert coord.poll_healthy_enough is True

    with pytest.raises(UpdateFailed):
        await coord._async_update_data()
    assert coord.consecutive_update_failures == 3
    assert coord.poll_healthy_enough is False


async def test_auth_failure_sets_counter_to_threshold(
    coordinator, mock_uhome_api,
):
    """Auth failures must immediately mark entities unavailable (scheduler stops)."""
    coordinator.devices["sw-1"] = make_fake_switch("sw-1")
    mock_uhome_api.get_device_state.side_effect = AuthenticationError("bad token")

    with pytest.raises(ConfigEntryAuthFailed):
        await coordinator._async_update_data()

    assert coordinator.consecutive_update_failures == coordinator.max_update_failures
    assert coordinator.poll_healthy_enough is False


async def test_invalid_token_envelope_sets_counter_to_threshold(
    coordinator, mock_uhome_api,
):
    coordinator.devices["sw-1"] = make_fake_switch("sw-1")
    mock_uhome_api.get_device_state.return_value = {
        "payload": {"error": {"code": "INVALID_TOKEN", "message": "expired"}}
    }

    with pytest.raises(ConfigEntryAuthFailed):
        await coordinator._async_update_data()

    assert coordinator.consecutive_update_failures == coordinator.max_update_failures
    assert coordinator.poll_healthy_enough is False


async def test_successful_push_resets_failure_counter(coordinator):
    """Push proving the channel is alive must restore availability."""
    sw = make_fake_switch("sw-1")
    coordinator.devices["sw-1"] = sw
    coordinator.consecutive_update_failures = coordinator.max_update_failures
    assert coordinator.poll_healthy_enough is False

    await coordinator.update_push_data(
        [{"id": "sw-1", "states": []}]
    )

    assert coordinator.consecutive_update_failures == 0
    assert coordinator.poll_healthy_enough is True
    sw.update_state_data.assert_awaited_once()
