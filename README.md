# Boiler Four-Way Valve

A Home Assistant helper that sets a **4-way boiler mixing valve** from the indoor temperature and the outdoor temperature.

The valve is a [Shelly 2PM Gen4](https://www.shelly.com/) paired over **Zigbee** and set to **Cover** mode. Every move is `cover.set_cover_position`. The integration does not call open, close, or stop.

- **0%** does not mix the boiler into the radiator loop. The two loops stay separate, so the radiators are not heated.
- **100%** joins them into one loop: water leaves the boiler toward the radiators, and the radiator return goes back into the boiler.

The indoor map turns the gap between the target and the room temperature into a cover position from 0% to 100%. Outdoor temperature then adds or removes opening, so a mild day holds the valve further closed and burns less oil. A **maximum position** is a safety ceiling on every command. **100% disables that ceiling.**

## Shelly 2PM Gen4

1. Put the Shelly 2PM Gen4 into Zigbee mode and pair it with ZHA or Zigbee2MQTT.
2. Set the device profile to **Cover**.
3. Calibrate the travel so the valve's closed end is **0%** and the open end is **100%**.
4. If the motor runs the wrong way, swap the two switch outputs or invert the direction on the Shelly. This integration does not invert position. It uses the cover entity's position as Home Assistant reports it.
5. Check that the cover supports **Set position**. A cover that can only open and close cannot hold a partial valve position.

The helper reads an indoor sensor and, optionally, an outdoor sensor, then writes one position to that cover. Extra covers can be attached; they receive the same position.

## Valve position mapping

The difference is **target − current**, rounded to 0.1 °C. The position stored on a key is used when the difference is **greater than that key**, up to and including the next key.

Default mapping:

```yaml
"-0.2": 0
"-0.1": 8
"0.0": 14
"0.1": 19
"0.2": 28
"0.4": 44
"0.7": 50
"1.0": 56
"1.3": 67
"1.7": 83
"2.0": 100
```

| Target − current | Cover position |
| --- | --- |
| ≤ -0.1 | 0% closed |
| > -0.1 to 0.0 | 8% |
| > 0.0 to 0.1 | 14% |
| > 0.1 to 0.2 | 19% |
| > 0.2 to 0.4 | 28% |
| > 0.4 to 0.7 | 44% |
| > 0.7 to 1.0 | 50% |
| > 1.0 to 1.3 | 56% |
| > 1.3 to 1.7 | 67% |
| > 1.7 to < 2.0 | 83% |
| ≥ 2.0 | 100% open |

Example: target 21.0 °C, room 20.7 °C. The difference is 0.3, so the cover is set to **28%**.

`off` uses the lowest position in the map. With the default map that is **0%**, closed. While the mode stays `off`, a position you set on the cover yourself is left alone. Changing the mode, a preset, or the target temperature moves the cover immediately.

## Manual override

**Manual position** is a slider from 0% to 100%, capped by the maximum position. In heat mode, set it to **15%** and the valve goes to 15%. The climate preset switches to **Manual**, and indoor and outdoor changes no longer move the valve. `calculated_position` still shows the opening the maps would command, including the outdoor trim and the ceiling.

Choosing **Manual** without moving the slider commands whatever position the slider already shows. Choosing another preset, or changing the target temperature, leaves Manual and follows the maps again. `off` still closes the valve; with Manual still selected, heat mode returns to that position.

The slider, the preset, and the HVAC mode are restored after a restart.

The climate action is `heating` while any cover is above that lowest position, and `idle` while it is at the closed position and the mode is `heat`.

Start with the default map. Change it later in the helper options. Every value has to be from 0 to 100.

This indoor position is not sent on its own once an outdoor sensor is configured. The outdoor adjustment below is added first, and the maximum position is applied after that.

## Outdoor adjustment

Keys are outdoor temperatures in °C. The value is **percent points added** to the indoor position. Negative values close the valve. The value of a key applies from that temperature up to, but not including, the next warmer key. Colder than the coldest key keeps that key's adjustment.

```yaml
"-10": 35
"-5": 20
"0": 10
"5": 0
"10": -15
"15": -40
```

| Outdoor | Added to the indoor position |
| --- | --- |
| < -10 °C | +35 |
| -10 °C to < -5 °C | +35 |
| -5 °C to < 0 °C | +20 |
| 0 °C to < 5 °C | +10 |
| 5 °C to < 10 °C | 0 |
| 10 °C to < 15 °C | -15 |
| ≥ 15 °C | -40 |

The result is clamped to 0–100% and then to the maximum position.

Examples, with the default indoor map and no safety ceiling:

| Indoor | Outdoor | Command |
| --- | --- | --- |
| At the target (difference 0.0 → 8%) | 12 °C | 0% |
| 0.3 °C below the target (28%) | 2 °C | 38% |
| 2 °C or more below the target (100%) | -8 °C | 100% |

A mild afternoon with the room already at the target closes the valve, so the boiler is not mixed into the radiators. A cold outdoor temperature opens it further even when the room is briefly at the target, because the house is about to lose heat. If the outdoor sensor is missing, the indoor map is used on its own. `off` does not apply the outdoor adjustment: the valve goes to the lowest indoor position, normally 0%.

## Maximum position

Every command is held at or below this value, including the emergency position, a large outdoor boost, and a manual position.

| Maximum | Effect |
| --- | --- |
| `100` | Limit disabled. The valve may be commanded fully open. |
| `60` | The command is never above 60%, even if the maps ask for more. |
| `0` | The valve is kept closed. |

With the ceiling at 60%, the third example above (100% + 35) is sent as **60%**, not 100%. That keeps the boiler from being fully coupled to the radiators.

## Installation

Requires Home Assistant 2026.11 or newer.

### Marketplace

[![Open your Home Assistant instance and open a repository in the Marketplace.](https://my.home-assistant.io/badges/marketplace_repository.svg)](https://my.home-assistant.io/redirect/marketplace_repository/?owner=tnesztler&repository=ha-boiler-four-way-valve&category=integration)

Or add it manually: **Settings** → **Marketplace** → **Add from link**, and enter:

`https://github.com/tnesztler/ha-boiler-four-way-valve`

Open **Boiler Four-Way Valve** and select **Install**. Restart Home Assistant if a repair asks you to.

### HACS

1. In HACS, open **Custom repositories** and add `https://github.com/tnesztler/ha-boiler-four-way-valve` as an **Integration**.
2. Install **Boiler Four-Way Valve**.
3. Restart Home Assistant.

### Create the helper

[![Open your Home Assistant instance and show your helpers.](https://my.home-assistant.io/badges/helpers.svg)](https://my.home-assistant.io/redirect/helpers/)

**Settings** → **Devices & services** → **Helpers** → **Create helper** → **Boiler Four-Way Valve**.

The climate entity is added to the device of the main cover, so it shows on the Shelly device page.

## Configuration

All of these can be changed later in the helper options.

### Cover

| Option | Default | Description |
| --- | --- | --- |
| Indoor temperature sensor | | `sensor`, `number`, or `input_number` with the room temperature |
| Temperature sensor precision | `0.1` | How the current temperature is displayed |
| Valve cover | | Cover whose position is the mixing valve. 0% no mixing, 100% one loop |
| Additional valve covers | | More covers. They get the same position |
| Minimum cycle duration | 2 minutes | Minimum time between automatic moves. Mode, preset, and target changes apply immediately. `0` disables the wait |
| Maximum cover position | `100` | Safety ceiling. The command never goes above this. `100` disables the limit |
| Emergency cover position | `14` | Used when the indoor sensor is missing or not numeric. Outdoor trim and the ceiling still apply |
| Minimum temperature change | `0` | Smallest room-temperature change that triggers another move. `0` reacts to every change |
| Position tolerance | `1` | Skip a command when the cover is already within this many percent |

Automatic moves also wait while a cover reports `opening` or `closing`, so a new position is not sent halfway through a travel. A failing indoor sensor does not wait out the cycle: the cover goes to the emergency position, adjusted for the outdoor temperature and the ceiling, as soon as it is not already moving. A failing outdoor sensor drops the outdoor adjustment and keeps the indoor map.

On a restart, heat mode waits up to 30 seconds for the indoor sensor before the first move, so a Zigbee sensor that is still starting does not push the valve to the emergency position. `off` closes the valve on startup.

### Outdoor

| Option | Default | Description |
| --- | --- | --- |
| Outdoor temperature sensor | | Outside air temperature. Leave empty to ignore the weather |
| Outdoor adjustment | see the table above | Percent points added to the indoor position |

### Temperature

| Option | Default | Description |
| --- | --- | --- |
| Minimum temperature | `7` | Lowest target |
| Maximum temperature | `35` | Highest target |
| Target temperature step | `0.5` | Step of the target control |

### Presets

`manual`, `home`, `away`, `comfort`, `eco`, `sleep`, and `activity`. Manual is always shown. A temperature preset without a temperature is hidden. Choosing no preset restores the target from before the preset.

Target temperature, HVAC mode, preset, and manual position are restored after a restart.

The climate entity also reports `current_command` (the position last sent to the valve, or the one ready to send), `calculated_position` (the opening the maps would command), `manual_position`, `temperature_difference`, `outdoor_temperature`, `outdoor_adjustment`, and `max_position`. `cover_position` is the position the main cover is reporting. `valve_position` is the same value as `current_command`.

Five sensors record the same numbers so History and long-term statistics can graph them: **Current command**, **Calculated position**, **Temperature offset** (target minus indoor temperature), **Outdoor offset** (percent points added from the outdoor map), and **Maximum position**. Temperature offset is unknown while the indoor temperature is missing. Outdoor offset is unknown while the outdoor temperature is missing.

Those values are drawn above the built-in thermostat. A Thermostat card for this climate entity shows the panel over the dial, and opening the entity shows the same panel at the top of the dialog. Restart Home Assistant after installing or updating, then refresh the browser. If the dial is cramped, make the card taller.

## Credits

The position map and the way a difference picks a position come from [Xitee1/ha-thermostat-valve-controller](https://github.com/Xitee1/ha-thermostat-valve-controller) (MIT). This project adapts that curve to a Zigbee cover position of 0–100%.
