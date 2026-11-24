# Boiler Four-Way Valve

The driving constraint is to keep heating oil consumption as low as possible while tracking the desired room temperature as closely as possible.

A deadband around the target is acceptable. Overshoot wastes oil: the house loses heat faster while it is warmer than the target, and the valve then has to open again.

When changing the control law:

- Prefer the smallest opening that holds the room inside the deadband.
- Open in small steps. Close in one move when the room is at or above the target, or when the curve has fallen below the current opening.
- Keep stepping on the cycle timer while the room stays below the deadband. Do not wait for the temperature to change before the next upward step.
- Keep the indoor and outdoor curves in code. They are not helper options, so a release replaces them.
- `calculated_position` may exceed the safety ceiling. The command sent to the valve may not.
- Do not pre-heat ahead of colder weather. An oil burner does not get cheaper by heating earlier.

Run `python -m unittest discover -s tests -v`. `tests/test_mapping.py` covers the curve, the command, and when another opening step is still owed. Those tests do not import Home Assistant.

Before every release, check the imports against Home Assistant 2026.11, the version in `hacs.json`. Load each module in `custom_components/boiler_four_way_valve` with that Home Assistant on `sys.path`, or resolve each imported name in the 2026.11 source. A missing name means the helper fails to start and the climate entity stays unavailable. Do not tag or publish until the imports load.
