"""Config flow for the RTL433 Interlogix Sensors integration."""

import asyncio
import json

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.components import mqtt
from homeassistant.core import callback

from .const import DOMAIN, SENSOR_TYPES

_SCAN_DURATION_SECONDS: int = 30
_MQTT_WILDCARD_TOPIC: str = "rtl_433/#"


class RTL433ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle the config flow for RTL433 Interlogix Sensors."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._discovered: dict[str, str] = {}
        self._pending: list[str] = []
        self._classified: dict[str, dict[str, str]] = {}
        self._current_serial: str | None = None
        self._scan_task: asyncio.Task | None = None

    async def async_step_user(
        self, user_input: dict | None = None
    ) -> config_entries.FlowResult:
        """Handle the initial user step.

        Args:
            user_input: Form data submitted by the user, or None on first load.

        Returns:
            A flow result directing to the next step or showing the form.
        """
        if user_input is None:
            return self.async_show_form(
                step_id="user",
                data_schema=vol.Schema({}),
                description_placeholders={
                    "info": (
                        "Click Submit to scan for 30 seconds. "
                        "Trigger each sensor to detect it."
                    )
                },
            )
        return await self.async_step_scan()

    async def async_step_scan(
        self, user_input: dict | None = None
    ) -> config_entries.FlowResult:
        """Scan MQTT for Interlogix sensor broadcasts using a progress step.

        Args:
            user_input: Unused; present for step handler signature compatibility.

        Returns:
            A flow result showing scan progress or directing to classify.
        """
        if not self._scan_task:
            self._scan_task = self.hass.async_create_task(self._do_scan())
            self._scan_task.add_done_callback(
                lambda _: self.hass.async_create_task(
                    self.hass.config_entries.flow.async_configure(self.flow_id)
                )
            )

        if not self._scan_task.done():
            return self.async_show_progress(
                step_id="scan",
                progress_action="scanning",
            )

        self._scan_task = None

        if not self._discovered:
            return self.async_show_form(
                step_id="user",
                data_schema=vol.Schema({}),
                errors={"base": "no_devices_found"},
            )

        self._pending = list(self._discovered.keys())
        return await self._next_classify_step()

    async def _do_scan(self) -> None:
        """Run the MQTT scan for the configured duration."""
        discovered: dict[str, str] = {}

        @callback
        def message_received(msg) -> None:
            try:
                payload = json.loads(msg.payload)
                model = payload.get("model", "")
                if "Interlogix" not in model:
                    return
                serial = str(
                    payload.get("id") or payload.get("device_serial", "")
                )
                if serial and serial not in discovered:
                    base_topic = "/".join(msg.topic.split("/")[:-1])
                    discovered[serial] = base_topic
            except (json.JSONDecodeError, AttributeError):
                pass

        unsubscribe = await mqtt.async_subscribe(
            self.hass, _MQTT_WILDCARD_TOPIC, message_received
        )
        await asyncio.sleep(_SCAN_DURATION_SECONDS)
        unsubscribe()
        self._discovered = discovered

    async def _next_classify_step(self) -> config_entries.FlowResult:
        """Advance to the next sensor classification step or finish.

        Returns:
            A flow result for the next classify step, or the created entry.
        """
        if not self._pending:
            return self.async_create_entry(
                title="RTL433 Interlogix Sensors",
                data={"sensors": self._classified},
            )
        self._current_serial = self._pending[0]
        return await self.async_step_classify()

    async def async_step_classify(
        self, user_input: dict | None = None
    ) -> config_entries.FlowResult:
        """Prompt the user to classify a discovered sensor.

        Args:
            user_input: Form data with 'sensor_type', or None on first load.

        Returns:
            A flow result for the next step or showing the classify form.
        """
        serial = self._current_serial
        topic = self._discovered[serial]
        remaining = len(self._pending)

        if user_input is not None:
            self._classified[serial] = {
                "topic": topic,
                "type": user_input["sensor_type"],
            }
            self._pending.pop(0)
            return await self._next_classify_step()

        return self.async_show_form(
            step_id="classify",
            data_schema=vol.Schema({
                vol.Required("sensor_type"): vol.In(SENSOR_TYPES),
            }),
            description_placeholders={
                "serial": serial,
                "topic": topic,
                "remaining": str(remaining),
            },
        )
