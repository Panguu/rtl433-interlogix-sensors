"""Binary sensor entities for Interlogix Security."""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import timedelta
from typing import Any

from homeassistant.components import mqtt
from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_call_later

from .const import (
    DOMAIN,
    MQTT_TOPIC,
    CONF_DEVICE_ID,
    CONF_CONTACT_SWITCH,
    CONF_DEVICE_CLASS,
    OFF_DELAY_SECONDS,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Interlogix binary sensors from a config entry."""
    device_id: str = entry.data[CONF_DEVICE_ID]
    contact_switch: str = entry.data[CONF_CONTACT_SWITCH]
    device_class: str = entry.data[CONF_DEVICE_CLASS]
    name: str = entry.data["name"]

    device_info = DeviceInfo(
        identifiers={(DOMAIN, device_id)},
        name=name,
        manufacturer="Interlogix",
        model="Security Sensor",
    )

    entities = [
        InterlogixContactSensor(device_id, name, contact_switch, device_class, device_info),
        InterlogixTamperSensor(device_id, name, device_info),
        InterlogixAlarmSensor(device_id, name, device_info),
        InterlogixSupervisionSensor(device_id, name, device_info),
        InterlogixBatterySensor(device_id, name, device_info),
        # Diagnostic switch entities (switch1–switch5)
        *[InterlogixSwitchSensor(device_id, name, f"switch{i}", device_info) for i in range(1, 6)],
    ]

    async_add_entities(entities)

    # Subscribe all entities to the shared MQTT topic
    @callback
    def message_received(msg):
        try:
            payload = json.loads(msg.payload)
        except (json.JSONDecodeError, AttributeError):
            return

        if payload.get("id") != device_id:
            return

        for entity in entities:
            entity.handle_message(payload)

    entry.async_on_unload(
        await mqtt.async_subscribe(hass, MQTT_TOPIC, message_received)
    )


class InterlogixBaseSensor(BinarySensorEntity):
    """Base class for Interlogix sensors."""

    _attr_should_poll = False
    _attr_has_entity_name = True

    def __init__(self, device_id: str, device_name: str, device_info: DeviceInfo) -> None:
        self._device_id = device_id
        self._device_name = device_name
        self._attr_device_info = device_info
        self._attr_is_on = None

    def handle_message(self, payload: dict) -> None:
        """Handle an incoming MQTT message — override in subclasses."""
        raise NotImplementedError

    @callback
    def _update(self, is_on: bool) -> None:
        self._attr_is_on = is_on
        self.async_write_ha_state()


class InterlogixContactSensor(InterlogixBaseSensor):
    """Contact (door/window open/close) sensor."""

    def __init__(
        self,
        device_id: str,
        device_name: str,
        contact_switch: str,
        device_class: str,
        device_info: DeviceInfo,
    ) -> None:
        super().__init__(device_id, device_name, device_info)
        self._contact_switch = contact_switch
        self._attr_name = "Contact"
        self._attr_unique_id = f"{device_id}_contact"
        self._attr_device_class = device_class

    def handle_message(self, payload: dict) -> None:
        if payload.get("subtype") != "contact":
            return
        value = payload.get(self._contact_switch)
        if value is None:
            return
        self._update(value == "OPEN")


class InterlogixLatchingSensor(InterlogixBaseSensor):
    """Base for latching sensors with off_delay (tamper, alarm)."""

    _subtype: str = ""
    _off_delay: int = OFF_DELAY_SECONDS

    def __init__(self, device_id: str, device_name: str, device_info: DeviceInfo) -> None:
        super().__init__(device_id, device_name, device_info)
        self._cancel_off_delay = None

    def handle_message(self, payload: dict) -> None:
        if payload.get("subtype") != self._subtype:
            return

        # Cancel any pending off delay
        if self._cancel_off_delay is not None:
            self._cancel_off_delay()
            self._cancel_off_delay = None

        self._update(True)

        # Schedule auto-reset
        @callback
        def _turn_off(_now):
            self._cancel_off_delay = None
            self._update(False)

        self._cancel_off_delay = self.hass.helpers.event.async_call_later(
            self._off_delay, _turn_off
        )


class InterlogixTamperSensor(InterlogixLatchingSensor):
    """Tamper sensor."""

    _subtype = "tamper"

    def __init__(self, device_id: str, device_name: str, device_info: DeviceInfo) -> None:
        super().__init__(device_id, device_name, device_info)
        self._attr_name = "Tamper"
        self._attr_unique_id = f"{device_id}_tamper"
        self._attr_device_class = BinarySensorDeviceClass.TAMPER


class InterlogixAlarmSensor(InterlogixLatchingSensor):
    """Alarm sensor."""

    _subtype = "alarm"

    def __init__(self, device_id: str, device_name: str, device_info: DeviceInfo) -> None:
        super().__init__(device_id, device_name, device_info)
        self._attr_name = "Alarm"
        self._attr_unique_id = f"{device_id}_alarm"
        self._attr_device_class = BinarySensorDeviceClass.SAFETY


class InterlogixSupervisionSensor(InterlogixBaseSensor):
    """Supervision (heartbeat) sensor — latches ON, never resets."""

    def __init__(self, device_id: str, device_name: str, device_info: DeviceInfo) -> None:
        super().__init__(device_id, device_name, device_info)
        self._attr_name = "Supervision"
        self._attr_unique_id = f"{device_id}_supervision"
        self._attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    def handle_message(self, payload: dict) -> None:
        if payload.get("subtype") != "supervision":
            return
        self._update(True)


class InterlogixSwitchSensor(InterlogixBaseSensor):
    """Diagnostic sensor showing raw state of a single switch (switch1–switch5)."""

    _attr_entity_registry_enabled_default = False  # hidden by default, enable manually

    def __init__(
        self,
        device_id: str,
        device_name: str,
        switch: str,
        device_info: DeviceInfo,
    ) -> None:
        super().__init__(device_id, device_name, device_info)
        self._switch = switch
        self._attr_name = f"Switch {switch[-1]}"
        self._attr_unique_id = f"{device_id}_{switch}"

    def handle_message(self, payload: dict) -> None:
        # Only update on contact packets — that's where switch states are meaningful
        if payload.get("subtype") != "contact":
            return
        value = payload.get(self._switch)
        if value is None:
            return
        self._update(value == "OPEN")


class InterlogixBatterySensor(InterlogixBaseSensor):
    """Battery low sensor."""

    def __init__(self, device_id: str, device_name: str, device_info: DeviceInfo) -> None:
        super().__init__(device_id, device_name, device_info)
        self._attr_name = "Battery"
        self._attr_unique_id = f"{device_id}_battery"
        self._attr_device_class = BinarySensorDeviceClass.BATTERY

    def handle_message(self, payload: dict) -> None:
        battery_ok = payload.get("battery_ok")
        if battery_ok is None:
            return
        # battery_ok=1 means battery is fine → battery LOW sensor should be OFF
        self._update(not bool(battery_ok))
