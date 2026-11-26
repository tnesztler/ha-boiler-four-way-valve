# Boiler Four-Way Valve

A Home Assistant helper that sets a **4-way boiler mixing valve** from the indoor temperature and the outdoor temperature.

The driving constraint is to keep heating oil consumption as low as possible while tracking the desired room temperature as closely as possible. A small deadband around the target is acceptable. Heat above the target is wasted oil: the house loses it faster, and the valve has to open again to recover.

The valve is a [Shelly 2PM Gen4](https://www.shelly.com/) paired over **Zigbee** and set to **Cover** mode. Every move is `cover.set_cover_position`. The integration does not call open, close, or stop.

- **0%** does not mix the boiler into the radiator loop. The two loops stay separate, so the radiators are not heated.
- **100%** joins them into one loop: water leaves the boiler toward the radiators, and the radiator return goes back into the boiler.

The indoor curve turns the gap between the target and the room temperature into a cover position from 0% to 100%. Outdoor temperature then adds or removes opening, so a mild day holds the valve further closed and burns less oil. Near the target the valve stays put. It opens a few points at a time and closes as soon as the room is warm enough. A **maximum position** is a safety ceiling on the command. **100% disables that ceiling.** The calculated position can still show a higher opening.

## Shelly 2PM Gen4

1. Put the Shelly 2PM Gen4 into Zigbee mode and pair it with ZHA or Zigbee2MQTT.
2. Set the device profile to **Cover**.
3. Calibrate the travel so the valve's closed end is **0%** and the open end is **100%**.
4. If the motor runs the wrong way, swap the two switch outputs or invert the direction on the Shelly. This integration does not invert position. It uses the cover entity's position as Home Assistant reports it.
5. Check that the cover supports **Set position**. A cover that can only open and close cannot hold a partial valve position.

The helper reads an indoor sensor and, optionally, an outdoor sensor, then writes one position to that cover. Extra covers can be attached; they receive the same position.

## Valve position mapping

The difference is **target − current**, rounded to 0.1 °C. The position stored on a key is the opening **at that difference**. Between two keys the opening moves in a straight line. Colder than the first key keeps that key's position, and warmer than the last key keeps the last one.

The default line is closed once the room is 0.2 °C above the target. At the target it is already open far enough for high-temperature steel radiators. A four-way valve at a few percent only trickles boiler water into the radiator loop, and a lukewarm loop does not heat emitters that were sized for about 80/60 °C or 90/70 °C. Their output falls sharply as the water cools, roughly with the temperature difference between the water and the room. A deficit opens the valve further from that holding point.

```yaml
"-0.2": 0
"0.0": 32
"0.3": 40
"0.7": 52
"1.2": 68
"1.7": 84
"2.0": 100
```

| Target − current | Cover position |
| --- | --- |
| ≤ -0.2 | 0% closed |
| -0.1 | 16% |
| 0.0 | 32% |
| 0.3 | 40% |
| 0.5 | 46% |
| 0.7 | 52% |
| 1.0 | 62% |
| 1.2 | 68% |
| 1.7 | 84% |
| ≥ 2.0 | 100% open |

Example: target 21.0 °C, room 20.7 °C. The difference is 0.3, so the curve is **40%** before the outdoor trim. A 0.5 °C deficit is **46%**, on the line between 40% and 52%. The 1.0 °C point on that next line is **62%** after rounding.

This curve is part of the integration. It is not a helper option, so installing a new version replaces it.

`off` uses the lowest position in the map. With the default map that is **0%**, closed. While the mode stays `off`, a position you set on the cover yourself is left alone. Changing the mode, a preset, or the target temperature skips the wait between moves. An opening is still limited to the maximum increase. A closing move follows the curve in one step.

## Deadband and slow opening

The curve is the opening the room is asking for. The command is that opening after three oil-saving rules:

- While the room is above the target, or exactly on it, the valve follows the closing side of the curve immediately.
- While the room is below the target by at most the **temperature deadband** (default **0.3 °C**), the valve stays at its current opening. The first move in that band uses the opening the curve gives at the target, including the outdoor trim.
- While the room is further below the target, the valve may open by at most the **maximum position increase** (default **5** points) per move. It takes the next step after each minimum cycle while the room stays that cold, without waiting for the temperature to change again. If the curve has fallen below the current opening, the valve closes to it in one move.

A deadband of `0` follows the curve on every change. A maximum increase of `100` lets one move reach the curve. The minimum cycle still spaces automatic moves apart. Mode, preset, and target changes skip that wait, and the same open and close rules apply.

## Manual override

**Manual position** is a slider from 0% to 100%, capped by the maximum position. In heat mode, set it to **15%** and the valve goes to 15%. The climate preset switches to **Manual**, and indoor and outdoor changes no longer move the valve. `calculated_position` still shows the opening the curve would ask for, including the outdoor trim. It is not capped by the ceiling, the deadband, or the slow open.

Choosing **Manual** without moving the slider commands whatever position the slider already shows. Choosing another preset, or changing the target temperature, leaves Manual and follows the maps again. `off` still closes the valve; with Manual still selected, heat mode returns to that position.

The slider, the preset, and the HVAC mode are restored after a restart.

The climate action is `heating` while any cover is above that lowest position, and `idle` while it is at the closed position and the mode is `heat`.

The indoor curve and the outdoor curve both ship with the integration. A new version replaces them. Every indoor value is from 0 to 100.

This indoor position is not sent on its own once an outdoor sensor is configured. The outdoor adjustment below is added first. The deadband, the slow open, and the maximum position are applied to the command after that.

## Outdoor adjustment

Keys are outdoor temperatures in °C. The value is **percent points added** to the indoor position. Negative values close the valve. Between two keys the adjustment moves in a straight line. Colder than the coldest key keeps that key's adjustment, and warmer than the warmest key keeps the last one.

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
| ≤ -10 °C | +35 |
| -8 °C | +29 |
| -5 °C | +20 |
| 0 °C | +10 |
| 2 °C | +6 |
| 5 °C | 0 |
| 10 °C | -15 |
| 12 °C | -25 |
| ≥ 15 °C | -40 |

The curve plus this adjustment is clamped to 0–100%. That number is `calculated_position`. The command then applies the deadband, the slow open, and the maximum position.

Examples with the default curve, a 0.3 °C deadband, a maximum increase of 5, and no safety ceiling. "First command" is the move when the valve has not been set yet.

| Indoor | Outdoor | Calculated | First command |
| --- | --- | --- | --- |
| At the target (32%) | 12 °C (-25) | 7% | 7% |
| 0.3 °C below the target (40%) | 2 °C (+6) | 46% | 38% |
| 2 °C or more below the target (100%) | -8 °C (+29) | 100% | 66%, then +5 per move |

A mild afternoon trims the opening. At 12 °C with the room on the target the command is 7%, and at 15 °C the outdoor trim closes the valve. A cold outdoor temperature opens it further even when the room is briefly at the target, because the house is about to lose heat. If the outdoor sensor is missing, the indoor curve is used on its own. `off` does not apply the outdoor adjustment: the valve goes to the lowest indoor position, normally 0%.

## Maximum position

Every command is held at or below this value, including the emergency position, a large outdoor boost, and a manual position. `calculated_position` is left above the ceiling when the curve asks for more, so the gap stays visible.

| Maximum | Effect |
| --- | --- |
| `100` | Limit disabled. The valve may be commanded fully open. |
| `60` | The command is never above 60%, even if the curve asks for more. |
| `0` | The valve is kept closed. |

With the ceiling at 60%, the third example above is calculated as **100%** and the command climbs toward **60%**, five points at a time. That keeps the boiler from being fully coupled to the radiators.

## Installation

Requires Home Assistant 2026.11 or newer.

### Marketplace

[![Open your Home Assistant instance and open a repository in the Marketplace.](https://my.home-assistant.io/badges/marketplace_repository.svg)](https://my.home-assistant.io/redirect/marketplace_repository/?owner=tnesztler&repository=ha-boiler-four-way-valve&category=integration)

Or add it manually: **Settings** → **Marketplace** → **Add from link**, and enter:

`https://github.com/tnesztler/ha-boiler-four-way-valve`

Open **Boiler Four-Way Valve** and select **Install**. Restart Home Assistant.

### HACS

1. In HACS, open **Custom repositories** and add `https://github.com/tnesztler/ha-boiler-four-way-valve` as an **Integration**.
2. Install **Boiler Four-Way Valve**.
3. Restart Home Assistant.

A new version is loaded only when Home Assistant restarts. Reloading the helper applies its options and does not load the updated code. Rebooting the machine is unnecessary.

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
| Minimum cycle duration | 2 minutes | Minimum time between automatic moves. Mode, preset, and target changes skip the wait. Opening is still limited to the maximum increase. `0` disables the wait |
| Temperature deadband | `0.3` | Degrees the room may sit below the target without the valve opening further. `0` follows the curve |
| Maximum position increase | `5` | Largest opening added in one move while the room is below the deadband. Closing is not limited. `100` jumps to the curve |
| Maximum cover position | `100` | Safety ceiling on the command. `calculated_position` may read higher. `100` disables the limit |
| Emergency cover position | `32` | Used when the indoor sensor has no numeric reading from the last 10 minutes. Outdoor trim and the ceiling still apply |
| Minimum temperature change | `0` | Smallest room-temperature change that triggers another move. `0` reacts to every change |
| Position tolerance | `1` | Skip a command when the cover is already within this many percent |

Automatic moves also wait while a cover reports `opening` or `closing`, so a new position is not sent halfway through a travel. A failing indoor sensor keeps its last reading for 10 minutes, including across a Home Assistant restart. After that it does not wait out the cycle: the cover goes to the emergency position, adjusted for the outdoor temperature and the ceiling, as soon as it is not already moving. A failing outdoor sensor keeps its last reading for 10 minutes, including across a restart, then drops the outdoor adjustment and keeps the indoor curve.

On a restart, a reading from the last 10 minutes is used immediately, so the valve resumes while a Zigbee sensor is still starting. If that reading is older, heat mode waits up to 30 seconds for the indoor sensor before the first move. `off` closes the valve on startup.

### Outdoor

| Option | Default | Description |
| --- | --- | --- |
| Outdoor temperature sensor | | Outside air temperature. Leave empty to ignore the weather. The adjustment curve above is part of the integration |

### Temperature

| Option | Default | Description |
| --- | --- | --- |
| Minimum temperature | `7` | Lowest target |
| Maximum temperature | `35` | Highest target |
| Target temperature step | `0.5` | Step of the target control |

### Presets

`manual`, `home`, `away`, `comfort`, and `eco`. Manual is always shown. A temperature preset without a temperature is hidden. Choosing no preset restores the target from before the preset.

Target temperature, HVAC mode, preset, and manual position are restored after a restart.

The climate entity also reports `current_command` (the position last sent to the valve, or the one ready to send), `calculated_position` (the curve after the outdoor trim, before the deadband, the slow open, and the ceiling), `manual_position`, `temperature_difference`, `outdoor_temperature`, `outdoor_adjustment`, and `max_position`. `outdoor_temperature` stays on the entity for checks and is not drawn on the thermostat panel. `cover_position` is the position the main cover is reporting. `valve_position` is the same value as `current_command`.

Five sensors record the same numbers so History and long-term statistics can graph them: **Current command**, **Calculated position**, **Temperature offset** (target minus indoor temperature), **Outdoor offset** (percent points added from the outdoor map), and **Maximum position**. Temperature offset is unknown while the indoor temperature is missing. Outdoor offset is unknown while the outdoor temperature is missing.

**Integration version** reports the installed version of this helper. The state stays the same until the integration is updated, so temperature history can be compared across releases.

Those values are drawn above the built-in thermostat. A Thermostat card for this climate entity shows the panel over the dial, and opening the entity shows the same panel at the top of the dialog. The History button opens the cover's device, so the recorded command and the other valve sensors are on the graph with the climate entity. Changing the target from the thermostat asks for confirmation before the new setpoint is sent. Restart Home Assistant after installing or updating, then refresh the browser. If the dial is cramped, make the card taller.

## Credits

The position map and the way a difference picks a position come from [Xitee1/ha-thermostat-valve-controller](https://github.com/Xitee1/ha-thermostat-valve-controller) (MIT). This project adapts that curve to a Zigbee cover position of 0–100%.
