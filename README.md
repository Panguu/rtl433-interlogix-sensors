# Interlogix Security for Home Assistant

A custom integration for Interlogix security sensors received via RTL_433 → MQTT.

## Features

- Auto-discovers Interlogix devices from your MQTT topic
- Creates 5 entities per sensor: Contact, Tamper, Alarm, Supervision, Battery
- Tamper and Alarm auto-reset after 10 minutes
- Full device registry support — each sensor appears as a device in HA

## Requirements

- RTL_433 publishing to MQTT (`rtl_433/9b13b3f4-rtl433-next/events`)
- Home Assistant MQTT integration configured

## Installation

### Via HACS (recommended)

1. In HACS, go to **Integrations → Custom repositories**
2. Add your repo URL, category: **Integration**
3. Install **Interlogix Security**
4. Restart Home Assistant

### Manual

1. Copy the `custom_components/interlogix_security` folder into your HA `custom_components` directory
2. Restart Home Assistant

## Setup

1. Go to **Settings → Devices & Services → Add Integration**
2. Search for **Interlogix Security**
3. The integration will listen on MQTT for 10 seconds — trigger one of your sensors during this time
4. Select the discovered device from the dropdown
5. Give it a name, choose which switch is the contact, and set the device class (door/window/etc.)
6. Repeat for each sensor

## Entities per sensor

| Entity | Device Class | Notes |
|---|---|---|
| Contact | door / window / opening | Tracks open/close state |
| Tamper | tamper | Latches ON, resets after 10 min |
| Alarm | safety | Latches ON, resets after 10 min |
| Supervision | connectivity | Latches ON after first heartbeat |
| Battery | battery | ON = battery low |
