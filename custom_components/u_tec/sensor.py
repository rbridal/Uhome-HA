"""Support for Uhome battery and Adaptive Aggressive sensors."""

from typing import Any, cast

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory, PERCENTAGE
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from utec_py.devices.device_const import DeviceCapability
from utec_py.devices.lock import Lock as UhomeLock

from .const import DOMAIN, SIGNAL_ADAPTIVE_OUTCOME, SIGNAL_DEVICE_UPDATE, SIGNAL_NEW_DEVICE
from .coordinator import UhomeDataUpdateCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Uhome sensors based on a config entry."""
    coordinator: UhomeDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id][
        "coordinator"
    ]

    async_add_entities(_create_battery_entities(coordinator))
    async_add_entities(_create_adaptive_entities(coordinator))

    @callback
    def async_add_sensor_entities() -> None:
        async_add_entities(_create_battery_entities(coordinator, add_only_new=True))
        async_add_entities(_create_adaptive_entities(coordinator, add_only_new=True))

    entry.async_on_unload(
        async_dispatcher_connect(hass, SIGNAL_NEW_DEVICE, async_add_sensor_entities)
    )


def _create_battery_entities(coordinator, add_only_new=False):
    """Create battery entities for devices with battery capability."""
    entities = []
    for device_id, device in coordinator.devices.items():
        if hasattr(device, "has_capability") and device.has_capability(
            DeviceCapability.BATTERY_LEVEL
        ):
            entity_id = f"{DOMAIN}_battery_{device_id}"
            if add_only_new and entity_id in coordinator.added_sensor_entities:
                continue
            entities.append(UhomeBatterySensorEntity(coordinator, device_id))
            coordinator.added_sensor_entities.add(entity_id)
    return entities


def _create_adaptive_entities(coordinator, add_only_new=False):
    """Create Adaptive Aggressive outcome sensors for locks."""
    entities = []
    for device_id, device in coordinator.devices.items():
        if not isinstance(device, UhomeLock):
            continue
        entity_id = f"{DOMAIN}_adaptive_{device_id}"
        if add_only_new and entity_id in coordinator.added_sensor_entities:
            continue
        entities.append(UhomeAdaptiveAggressiveSensor(coordinator, device_id))
        coordinator.added_sensor_entities.add(entity_id)
    return entities


class UhomeBatterySensorEntity(CoordinatorEntity, SensorEntity):
    """Representation of a Uhome battery sensor."""

    def __init__(self, coordinator: UhomeDataUpdateCoordinator, device_id: str) -> None:
        super().__init__(coordinator)
        self._device = cast(UhomeLock, coordinator.devices[device_id])
        self._attr_unique_id = f"{DOMAIN}_battery_{device_id}"
        self._attr_name = f"{self._device.name} Battery"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._device.device_id)},
            name=self._device.name,
            manufacturer=self._device.manufacturer,
            model=self._device.model,
            hw_version=self._device.hw_version,
        )
        self._attr_device_class = SensorDeviceClass.BATTERY
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_native_unit_of_measurement = PERCENTAGE

    @property
    def available(self) -> bool:
        return self.coordinator.poll_healthy_enough and self._device.available

    @property
    def native_value(self) -> int | None:
        return self._device.battery_level

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                f"{SIGNAL_DEVICE_UPDATE}_{self._device.device_id}",
                self._handle_push_update,
            )
        )

    @callback
    def _handle_push_update(self, push_data):
        self.async_write_ha_state()


class UhomeAdaptiveAggressiveSensor(CoordinatorEntity, SensorEntity):
    """Last Adaptive Aggressive outcome for one lock.

    0 = push confirmed the command.
    1-5 = polls until the commanded state was confirmed.
    6 = burst timed out.
    unknown until the first command after load.
    """

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_has_entity_name = True
    _attr_name = "Adaptive Aggressive"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:timer-sand"

    def __init__(self, coordinator: UhomeDataUpdateCoordinator, device_id: str) -> None:
        super().__init__(coordinator)
        self._device_id = device_id
        self._device = cast(UhomeLock, coordinator.devices[device_id])
        self._attr_unique_id = f"{DOMAIN}_adaptive_{device_id}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device_id)},
            name=self._device.name,
            manufacturer=self._device.manufacturer,
            model=self._device.model,
            hw_version=self._device.hw_version,
        )

    @property
    def available(self) -> bool:
        return True

    @property
    def native_value(self) -> int | None:
        outcome = self.coordinator.adaptive.last_outcome.get(self._device_id)
        if not outcome:
            return None
        return int(outcome["value"])

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        outcome = self.coordinator.adaptive.last_outcome.get(self._device_id) or {}
        return {
            "attempts": outcome.get("attempts"),
            "reason": outcome.get("reason"),
            "expected_locked": outcome.get("expected_locked"),
            "at": outcome.get("at"),
        }

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                f"{SIGNAL_ADAPTIVE_OUTCOME}_{self._device_id}",
                self._handle_outcome,
            )
        )

    @callback
    def _handle_outcome(self) -> None:
        self.async_write_ha_state()
