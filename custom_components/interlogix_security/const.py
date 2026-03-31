"""Constants for Interlogix Security integration."""

DOMAIN = "interlogix_security"
MQTT_TOPIC = "rtl_433/9b13b3f4-rtl433-next/events"

CONF_DEVICE_ID = "device_id"
CONF_CONTACT_SWITCH = "contact_switch"
CONF_DEVICE_CLASS = "device_class"

DISCOVER_TIMEOUT = 10  # seconds to listen for devices during discovery

CONTACT_SWITCHES = ["switch1", "switch2", "switch3", "switch4", "switch5"]

DEVICE_CLASSES = [
    "door",
    "window",
    "opening",
    "garage_door",
    "lock",
]

OFF_DELAY_SECONDS = 600  # 10 minutes for tamper and alarm
