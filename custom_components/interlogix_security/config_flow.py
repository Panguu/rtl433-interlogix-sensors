"""Config flow for Interlogix Security integration."""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.components import mqtt
from homeassistant.data_entry_flow import FlowResult

from .const import (
    DOMAIN,
    MQTT_TOPIC,
    CONF_DEVICE_ID,
    CONF_CONTACT_SWITCH,
    CONF_DEVICE_CLASS,
    CONTACT_SWITCHES,
    DEVICE_CLASSES,
    DISCOVER_TIMEOUT,
)

_LOGGER = logging.getLogger(__name__)


class InterlogixConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Interlogix Security."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialise the config flow."""
        self._discovered_devices: dict[str, dict] = {}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step — discover devices from MQTT."""
        return await self.async_step_discover()

    async def async_step_discover(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Listen on MQTT for Interlogix devices and present a picker."""
        errors: dict[str, str] = {}

        if user_input is not None:
            selected_id = user_input[CONF_DEVICE_ID]
            self._selected_device_id = selected_id
            return await self.async_step_configure()

        # Listen for devices on MQTT for DISCOVER_TIMEOUT seconds
        discovered: dict[str, dict] = {}
        done = asyncio.Event()

        async def message_received(msg):
            try:
                payload = json.loads(msg.payload)
                if payload.get("model") == "Interlogix-Security":
                    device_id = payload.get("id")
                    if device_id:
                        discovered[device_id] = payload
            except (json.JSONDecodeError, AttributeError):
                pass

        unsubscribe = await mqtt.async_subscribe(
            self.hass, MQTT_TOPIC, message_received
        )

        await asyncio.sleep(DISCOVER_TIMEOUT)
        unsubscribe()

        # Also include already-seen devices from other entries for convenience
        existing_ids = {
            entry.data[CONF_DEVICE_ID]
            for entry in self.hass.config_entries.async_entries(DOMAIN)
        }

        available = {
            device_id: data
            for device_id, data in discovered.items()
            if device_id not in existing_ids
        }

        if not available:
            errors["base"] = "no_devices_found"
            return self.async_show_form(
                step_id="discover",
                data_schema=vol.Schema({}),
                errors=errors,
                description_placeholders={
                    "timeout": str(DISCOVER_TIMEOUT),
                },
            )

        self._discovered_devices = available

        device_options = {
            device_id: f"{device_id} (battery: {'OK' if data.get('battery_ok') else 'LOW'})"
            for device_id, data in available.items()
        }

        return self.async_show_form(
            step_id="discover",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_DEVICE_ID): vol.In(device_options),
                }
            ),
            errors=errors,
        )

    async def async_step_configure(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Configure the selected sensor — name, switch, device class."""
        errors: dict[str, str] = {}

        if user_input is not None:
            await self.async_set_unique_id(self._selected_device_id)
            self._abort_if_unique_id_configured()

            return self.async_create_entry(
                title=user_input["name"],
                data={
                    CONF_DEVICE_ID: self._selected_device_id,
                    CONF_CONTACT_SWITCH: user_input[CONF_CONTACT_SWITCH],
                    CONF_DEVICE_CLASS: user_input[CONF_DEVICE_CLASS],
                    "name": user_input["name"],
                },
            )

        default_name = f"Interlogix {self._selected_device_id}"

        return self.async_show_form(
            step_id="configure",
            data_schema=vol.Schema(
                {
                    vol.Required("name", default=default_name): str,
                    vol.Required(CONF_CONTACT_SWITCH, default="switch1"): vol.In(
                        CONTACT_SWITCHES
                    ),
                    vol.Required(CONF_DEVICE_CLASS, default="door"): vol.In(
                        DEVICE_CLASSES
                    ),
                }
            ),
            errors=errors,
        )
