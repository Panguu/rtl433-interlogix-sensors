"""Binary sensor platform for RTL433 Interlogix sensors via MQTT."""

import json
from typing import Callable

from homeassistant.components import mqtt
from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback

from .const import DOMAIN

_DEVICE_CLASS_MAP: dict[str, BinarySensorDeviceClass] = {
    "door": BinarySensorDeviceClass.DOOR,
    "window": BinarySensorDeviceClass.WINDOW,
    "vibration": BinarySensorDeviceClass.VIBRATION,
}

_OPEN_STATE_FIELDS: tuple[str, ...] = (
    "switch5", "f1_latch_state", "state", "opened"
)
_VIBRATION_FIELDS: tuple[str, ...] = ("switch4", "f2_latch_state", "alarm")
_TAMPER_FIELDS: tuple[str, ...] = (
    "tamper", "tamper_status", "switch3", "f3_latch_state"
)

_OPEN_TRUTHY: frozenset[str] = frozenset({"OPEN", "1", "TRUE", "ON"})
_VIBRATION_TRUTHY: frozenset[str] = frozenset({"OPEN", "1", "TRUE", "ON", "ALARM"})
_TAMPER_TRUTHY: frozenset[str] = frozenset({"OPEN", "1", "TRUE", "ON", "TAMPER"})


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: Callable,
) -> None:
    """Set up RTL433 Interlogix binary sensors from a config entry.

    Args:
        hass: The Home Assistant instance.
        entry: The config entry containing sensor data.
        async_add_entities: Callback to register new entities.
    """
    entities = []
    for serial, config in entry.data.get("sensors", {}).items():
        sensor_type = config["type"]
        base_topic = config["topic"]
        entities.append(
            RTL433BinarySensor(
                serial=serial,
                base_topic=base_topic,
                sensor_type=sensor_type,
                is_tamper=False,
            )
        )
        entities.append(
            RTL433BinarySensor(
                serial=serial,
                base_topic=base_topic,
                sensor_type=sensor_type,
                is_tamper=True,
            )
        )
    async_add_entities(entities)


class RTL433BinarySensor(BinarySensorEntity):
    """Binary sensor entity for an RTL433 Interlogix device.

    Each physical sensor produces two entities: a primary state entity
    and a tamper entity.
    """

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(
        self,
        serial: str,
        base_topic: str,
        sensor_type: str,
        is_tamper: bool,
    ) -> None:
        """Initialize the binary sensor.

        Args:
            serial: The sensor's unique serial number.
            base_topic: The base MQTT topic for this device.
            sensor_type: One of 'door', 'window', or 'vibration'.
            is_tamper: Whether this entity represents the tamper channel.
        """
        self._serial = serial
        self._base_topic = base_topic
        self._sensor_type = sensor_type
        self._is_tamper = is_tamper
        self._unsubscribe: Callable | None = None

        if is_tamper:
            self._attr_unique_id = f"rtl433_{serial}_tamper"
            self._attr_name = f"{serial} Tamper"
            self._attr_device_class = BinarySensorDeviceClass.TAMPER
        else:
            self._attr_unique_id = f"rtl433_{serial}_{sensor_type}"
            self._attr_name = f"{serial} {sensor_type.title()}"
            self._attr_device_class = _DEVICE_CLASS_MAP.get(sensor_type)

        self._attr_is_on: bool | None = None

    @property
    def device_info(self) -> dict:
        """Return device info to group primary and tamper under one device.

        Returns:
            A dict of device registry attributes.
        """
        return {
            "identifiers": {(DOMAIN, self._serial)},
            "name": f"Interlogix Sensor {self._serial}",
            "model": "Interlogix Contact/Vibration Sensor",
            "manufacturer": "GE/Interlogix",
        }

    async def async_added_to_hass(self) -> None:
        """Subscribe to MQTT topics when added to Home Assistant."""
        subscribe_topic = f"{self._base_topic}/#"

        @callback
        def message_received(msg) -> None:
            try:
                payload = json.loads(msg.payload)
            except (json.JSONDecodeError, AttributeError):
                payload = {"_raw": msg.payload}

            if self._is_tamper:
                self._attr_is_on = self._extract_tamper(payload)
            elif self._sensor_type == "vibration":
                self._attr_is_on = self._extract_vibration(payload)
            else:
                self._attr_is_on = self._extract_open(payload)

            if self._attr_is_on is not None:
                self.async_write_ha_state()

        self._unsubscribe = await mqtt.async_subscribe(
            self.hass, subscribe_topic, message_received
        )

    async def async_will_remove_from_hass(self) -> None:
        """Unsubscribe from MQTT when removed from Home Assistant."""
        if self._unsubscribe:
            self._unsubscribe()

    def _extract_open(self, payload: dict) -> bool | None:
        """Extract open/closed state from a contact sensor payload.

        Args:
            payload: Parsed MQTT message payload.

        Returns:
            True if open, False if closed, None if indeterminate.
        """
        for field in _OPEN_STATE_FIELDS:
            val = payload.get(field)
            if val is not None:
                return str(val).upper() in _OPEN_TRUTHY
        return None

    def _extract_vibration(self, payload: dict) -> bool | None:
        """Extract triggered state from a vibration sensor payload.

        Args:
            payload: Parsed MQTT message payload.

        Returns:
            True if triggered, False if clear, None if indeterminate.
        """
        for field in _VIBRATION_FIELDS:
            val = payload.get(field)
            if val is not None:
                return str(val).upper() in _VIBRATION_TRUTHY
        return None

    def _extract_tamper(self, payload: dict) -> bool | None:
        """Extract tamper state from a sensor payload.

        Args:
            payload: Parsed MQTT message payload.

        Returns:
            True if tampered, False if clear, None if indeterminate.
        """
        for field in _TAMPER_FIELDS:
            val = payload.get(field)
            if val is not None:
                return str(val).upper() in _TAMPER_TRUTHY
        return None
