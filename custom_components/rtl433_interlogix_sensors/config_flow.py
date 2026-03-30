"""Config flow for the RTL433 Interlogix Sensors integration."""

import asyncio
import json

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.components import mqtt
from homeassistant.core import callback

from .const import DOMAIN, SENSOR_TYPES


class RTL433ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle the config flow for RTL433 Interlogix Sensors."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._classified: dict[str, dict[str, str]] = {}
        self._current_serial: str | None = None
        self._current_topic: str | None = None
        self._scan_task: asyncio.Task | None = None
        self._found_serial: str | None = None
        self._found_topic: str | None = None

    async def async_step_user(
        self, user_input: dict | None = None
    ) -> config_entries.FlowResult:
        """Handle the initial step — start scanning immediately.

        Args:
            user_input: Unused on first load; 'finish' key signals done.

        Returns:
            A flow result for the scan step or the created entry.
        """
        if user_input is not None and user_input.get("action") == "finish":
            if not self._classified:
                return self.async_show_form(
                    step_id="user",
                    data_schema=vol.Schema({
                        vol.Required("action", default="scan"): vol.In(
                            {"scan": "Keep scanning", "finish": "Finish"}
                        ),
                    }),
                    errors={"base": "no_devices_found"},
                )
            return self.async_create_entry(
                title="RTL433 Interlogix Sensors",
                data={"sensors": self._classified},
            )
        return await self.async_step_scan()

    async def async_step_scan(
        self, user_input: dict | None = None
    ) -> config_entries.FlowResult:
        """Wait until a new device is detected on MQTT.

        Args:
            user_input: Unused; present for step handler signature compatibility.

        Returns:
            A flow result showing scan progress or directing to classify.
        """
        if not self._scan_task:
            self._found_serial = None
            self._found_topic = None
            self._scan_task = self.hass.async_create_task(self._wait_for_device())
            self._scan_task.add_done_callback(
                lambda _: self.hass.async_create_task(
                    self.hass.config_entries.flow.async_configure(self.flow_id)
                )
            )

        if not self._scan_task.done():
            return self.async_show_progress(
                step_id="scan",
                progress_action="scanning",
                progress_task=self._scan_task,
            )

        self._scan_task = None

        if not self._found_serial:
            return self.async_show_progress_done(next_step_id="user")

        self._current_serial = self._found_serial
        self._current_topic = self._found_topic
        return await self.async_step_classify()

    async def _wait_for_device(self) -> None:
        """Subscribe to MQTT and return as soon as one new device is seen."""
        found = asyncio.Event()

        @callback
        def message_received(msg) -> None:
            if found.is_set():
                return
            try:
                payload = json.loads(msg.payload)
                serial = str(
                    payload.get("id") or payload.get("device_serial", "")
                )
                if serial and serial not in self._classified:
                    base_topic = "/".join(msg.topic.split("/")[:-1])
                    self._found_serial = serial
                    self._found_topic = base_topic
                    found.set()
            except (json.JSONDecodeError, AttributeError):
                pass

        unsubscribe = await mqtt.async_subscribe(
            self.hass, "rtl_433/#", message_received
        )
        await found.wait()
        unsubscribe()

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
        topic = self._current_topic

        if user_input is not None:
            self._classified[serial] = {
                "topic": topic,
                "type": user_input["sensor_type"],
            }
            return await self.async_step_scan()

        return self.async_show_form(
            step_id="classify",
            data_schema=vol.Schema({
                vol.Required("sensor_type"): vol.In(SENSOR_TYPES),
            }),
            description_placeholders={
                "serial": serial,
                "topic": topic,
            },
        )
