"""Tests for the cover valve-position mapping."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(
    0,
    str(
        Path(__file__).resolve().parents[1]
        / "custom_components"
        / "boiler_four_way_valve"
    ),
)

import mapping  # noqa: E402


# Points on the default curve, including the straight lines between keys.
CURVE = (
    (-1.0, 0),
    (-0.2, 0),
    (-0.1, 4),
    (0.0, 8),
    (0.3, 12),
    (0.5, 20),
    (0.7, 28),
    (1.0, 41.2),
    (1.2, 50),
    (1.7, 75),
    (2.0, 100),
    (3.0, 100),
)


class MappingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.mapping = mapping.parse_position_mapping(mapping.DEFAULT_POSITION_MAPPING)

    def test_default_spans_closed_to_open(self) -> None:
        self.assertEqual(mapping.DEFAULT_POSITION_MAPPING["-0.2"], 0)
        self.assertEqual(mapping.DEFAULT_POSITION_MAPPING["2.0"], 100)
        self.assertEqual(mapping.DEFAULT_EMERGENCY_POSITION, 14)

    def test_curve_matches_the_published_line(self) -> None:
        for difference, expected in CURVE:
            with self.subTest(difference=difference):
                self.assertAlmostEqual(
                    mapping.position_for_difference(self.mapping, difference),
                    expected,
                )

    def test_small_indoor_gap_opens_the_valve_partway(self) -> None:
        # Target 21.0 °C, current 20.7 °C. Difference 0.3 is the 12% point.
        position, difference = mapping.cover_position(
            self.mapping,
            current=20.7,
            target=21.0,
            emergency=14,
            hvac_off=False,
        )
        self.assertEqual(difference, 0.3)
        self.assertEqual(position, 12)

    def test_zero_celsius_is_a_real_temperature(self) -> None:
        position, difference = mapping.cover_position(
            self.mapping,
            current=0.0,
            target=0.0,
            emergency=14,
            hvac_off=False,
        )
        self.assertEqual(difference, 0.0)
        self.assertEqual(position, 8)

    def test_off_uses_the_lowest_position(self) -> None:
        position, difference = mapping.cover_position(
            self.mapping,
            current=10.0,
            target=22.0,
            emergency=14,
            hvac_off=True,
        )
        self.assertEqual(position, 0)
        self.assertIsNone(difference)

    def test_missing_temperature_uses_emergency_position(self) -> None:
        for current, target in ((None, 21.0), (21.0, None), (None, None)):
            position, difference = mapping.cover_position(
                self.mapping,
                current=current,
                target=target,
                emergency=14,
                hvac_off=False,
            )
            self.assertEqual(position, 14)
            self.assertIsNone(difference)

    def test_emergency_position_is_clamped_to_the_cover_range(self) -> None:
        high, _ = mapping.cover_position(
            self.mapping,
            current=None,
            target=None,
            emergency=150,
            hvac_off=False,
        )
        low, _ = mapping.cover_position(
            self.mapping,
            current=None,
            target=None,
            emergency=-5,
            hvac_off=False,
        )
        self.assertEqual(high, 100)
        self.assertEqual(low, 0)

    def test_curve_holds_each_end_and_draws_a_line_between_keys(self) -> None:
        parsed = mapping.parse_position_mapping({"-0.2": 10, "0.0": 0, "1.0": 50})
        self.assertEqual(mapping.position_for_difference(parsed, -0.2), 10)
        self.assertEqual(mapping.position_for_difference(parsed, -1), 10)
        self.assertEqual(mapping.position_for_difference(parsed, 0.0), 0)
        self.assertEqual(mapping.position_for_difference(parsed, 0.5), 25)
        self.assertEqual(mapping.position_for_difference(parsed, 1), 50)

    def test_rejects_positions_outside_0_to_100(self) -> None:
        with self.assertRaises(mapping.InvalidPositionMapping):
            mapping.parse_position_mapping({"0.0": 101})
        with self.assertRaises(mapping.InvalidPositionMapping):
            mapping.parse_position_mapping({"0.0": -1})

    def test_rejects_empty_duplicate_and_non_numeric_values(self) -> None:
        with self.assertRaises(mapping.InvalidPositionMapping):
            mapping.parse_position_mapping({})
        with self.assertRaises(mapping.InvalidPositionMapping):
            mapping.parse_position_mapping({"0": 10, "0.0": 20})
        with self.assertRaises(mapping.InvalidPositionMapping):
            mapping.parse_position_mapping({"0.0": True})
        with self.assertRaises(mapping.InvalidPositionMapping):
            mapping.parse_position_mapping({"cold": 10})

    def test_half_up_rounding(self) -> None:
        self.assertEqual(mapping.to_cover_percent(14.5), 15)
        self.assertEqual(mapping.to_cover_percent(14.4), 14)
        self.assertEqual(mapping.to_cover_percent(100.4), 100)


class OutdoorAndLimitTests(unittest.TestCase):
    def setUp(self) -> None:
        self.indoor = mapping.parse_position_mapping(mapping.DEFAULT_POSITION_MAPPING)
        self.outdoor = mapping.parse_outdoor_adjustment(mapping.DEFAULT_OUTDOOR_ADJUSTMENT)

    def test_outdoor_curve(self) -> None:
        cases = (
            (-20, 35),
            (-10, 35),
            (-8, 29),
            (-5, 20),
            (0, 10),
            (2, 6),
            (5, 0),
            (10, -15),
            (12, -25),
            (15, -40),
            (20, -40),
        )
        for outdoor, expected in cases:
            with self.subTest(outdoor=outdoor):
                self.assertAlmostEqual(
                    mapping.adjustment_for_outdoor(self.outdoor, outdoor),
                    expected,
                )

    def test_mild_weather_closes_a_satisfied_room(self) -> None:
        indoor, _ = mapping.cover_position(
            self.indoor,
            current=20.0,
            target=20.0,
            emergency=14,
            hvac_off=False,
        )
        position, adjustment = mapping.apply_outdoor_and_limit(
            indoor,
            outdoor=12,
            outdoor_mapping=self.outdoor,
            max_position=100,
        )
        self.assertEqual(indoor, 8)
        self.assertAlmostEqual(adjustment, -25)
        self.assertEqual(position, 0)

    def test_cool_weather_adds_to_a_small_indoor_demand(self) -> None:
        indoor, difference = mapping.cover_position(
            self.indoor,
            current=20.7,
            target=21.0,
            emergency=14,
            hvac_off=False,
        )
        position, adjustment = mapping.apply_outdoor_and_limit(
            indoor,
            outdoor=2,
            outdoor_mapping=self.outdoor,
            max_position=100,
        )
        self.assertEqual(difference, 0.3)
        self.assertEqual(indoor, 12)
        self.assertAlmostEqual(adjustment, 6)
        self.assertEqual(position, 18)

    def test_maximum_of_100_disables_the_ceiling(self) -> None:
        for ceiling in (100, 100.0, None):
            position, _ = mapping.apply_outdoor_and_limit(
                100,
                outdoor=-8,
                outdoor_mapping=self.outdoor,
                max_position=ceiling,
            )
            self.assertEqual(position, 100)

    def test_maximum_below_100_caps_the_command(self) -> None:
        position, adjustment = mapping.apply_outdoor_and_limit(
            100,
            outdoor=-8,
            outdoor_mapping=self.outdoor,
            max_position=60,
        )
        self.assertAlmostEqual(adjustment, 29)
        self.assertEqual(position, 60)

    def test_ceiling_also_limits_the_emergency_position(self) -> None:
        emergency, difference = mapping.cover_position(
            self.indoor,
            current=None,
            target=21.0,
            emergency=80,
            hvac_off=False,
        )
        position, _ = mapping.apply_outdoor_and_limit(
            emergency,
            outdoor=None,
            outdoor_mapping=self.outdoor,
            max_position=40,
        )
        self.assertIsNone(difference)
        self.assertEqual(emergency, 80)
        self.assertEqual(position, 40)

    def test_missing_outdoor_keeps_the_indoor_position_under_the_ceiling(self) -> None:
        position, adjustment = mapping.apply_outdoor_and_limit(
            28,
            outdoor=None,
            outdoor_mapping=self.outdoor,
            max_position=20,
        )
        self.assertIsNone(adjustment)
        self.assertEqual(position, 20)

    def test_manual_position_stays_under_the_ceiling(self) -> None:
        self.assertEqual(mapping.limit_position(15, 100), 15)
        self.assertEqual(mapping.limit_position(15, None), 15)
        self.assertEqual(mapping.limit_position(80, 60), 60)

    def test_rejects_outdoor_adjustments_outside_minus_100_to_100(self) -> None:
        with self.assertRaises(mapping.InvalidPositionMapping):
            mapping.parse_outdoor_adjustment({"0": 101})
        with self.assertRaises(mapping.InvalidPositionMapping):
            mapping.parse_outdoor_adjustment({"0": -101})
        with self.assertRaises(mapping.InvalidPositionMapping):
            mapping.parse_outdoor_adjustment({})


class ControlDecisionTests(unittest.TestCase):
    """Command versus the opening the maps would choose."""

    def setUp(self) -> None:
        self.indoor = mapping.parse_position_mapping(mapping.DEFAULT_POSITION_MAPPING)
        self.outdoor = mapping.parse_outdoor_adjustment(
            mapping.DEFAULT_OUTDOOR_ADJUSTMENT
        )

    def _positions(
        self, **overrides: object
    ) -> tuple[int, int, float | None, float | None]:
        values: dict[str, object] = {
            "current": 20.7,
            "target": 21.0,
            "emergency": 14,
            "hvac_off": False,
            "manual": False,
            "manual_position": 15,
            "outdoor": 2,
            "outdoor_mapping": self.outdoor,
            "max_position": 100,
        }
        values.update(overrides)
        return mapping.valve_positions(self.indoor, **values)  # type: ignore[arg-type]

    def test_deadband_holds_the_at_target_opening(self) -> None:
        command, calculated, difference, adjustment = self._positions()
        self.assertEqual(difference, 0.3)
        self.assertAlmostEqual(adjustment, 6)
        self.assertEqual(calculated, 18)
        self.assertEqual(command, 14)

    def test_deadband_keeps_an_existing_opening(self) -> None:
        command, calculated, _, _ = self._positions(previous=22, current=20.8, target=21.0)
        self.assertEqual(calculated, 17)
        self.assertEqual(command, 22)

    def test_warm_room_closes_to_the_curve_in_one_move(self) -> None:
        command, calculated, difference, _ = self._positions(
            current=21.1,
            target=21.0,
            previous=40,
        )
        self.assertEqual(difference, -0.1)
        self.assertEqual(calculated, 10)
        self.assertEqual(command, 10)

    def test_large_deficit_starts_from_the_holding_opening(self) -> None:
        command, calculated, difference, adjustment = self._positions(
            current=19.0,
            target=21.0,
            outdoor=-8,
        )
        self.assertEqual(difference, 2.0)
        self.assertAlmostEqual(adjustment, 29)
        self.assertEqual(calculated, 100)
        self.assertEqual(command, 42)

    def test_cold_room_opens_by_one_step(self) -> None:
        command, calculated, difference, _ = self._positions(
            current=20.5,
            target=21.0,
            previous=10,
        )
        self.assertEqual(difference, 0.5)
        self.assertEqual(calculated, 26)
        self.assertEqual(command, 15)

    def test_cold_room_closes_fully_when_the_curve_falls(self) -> None:
        command, calculated, _, _ = self._positions(
            current=20.5,
            target=21.0,
            previous=40,
        )
        self.assertEqual(calculated, 26)
        self.assertEqual(command, 26)

    def test_calculated_position_stays_above_the_ceiling(self) -> None:
        command, calculated, _, adjustment = self._positions(
            current=19.0,
            target=21.0,
            outdoor=-8,
            previous=40,
            max_position=30,
        )
        self.assertAlmostEqual(adjustment, 29)
        self.assertEqual(calculated, 100)
        self.assertEqual(command, 30)

    def test_calculated_position_stays_visible_during_manual_hold(self) -> None:
        command, calculated, difference, adjustment = self._positions(manual=True)
        self.assertEqual(command, 15)
        self.assertEqual(calculated, 18)
        self.assertEqual(difference, 0.3)
        self.assertAlmostEqual(adjustment, 6)

    def test_manual_hold_on_a_mild_day_keeps_the_closed_calculation(self) -> None:
        command, calculated, _, adjustment = self._positions(
            manual=True,
            manual_position=15,
            current=20.0,
            target=20.0,
            outdoor=12,
        )
        self.assertEqual(calculated, 0)
        self.assertAlmostEqual(adjustment, -25)
        self.assertEqual(command, 15)

    def test_manual_hold_cannot_pass_the_ceiling(self) -> None:
        command, calculated, _, adjustment = self._positions(
            manual=True,
            manual_position=80,
            current=18.0,
            target=21.0,
            outdoor=-8,
            max_position=60,
        )
        self.assertAlmostEqual(adjustment, 29)
        self.assertEqual(calculated, 100)
        self.assertEqual(command, 60)

    def test_off_closes_the_valve_and_still_reports_the_calculation(self) -> None:
        command, calculated, difference, adjustment = self._positions(hvac_off=True)
        self.assertEqual(command, 0)
        self.assertEqual(calculated, 18)
        self.assertEqual(difference, 0.3)
        self.assertAlmostEqual(adjustment, 6)

    def test_off_and_manual_still_closes_the_valve(self) -> None:
        command, calculated, _, _ = self._positions(hvac_off=True, manual=True)
        self.assertEqual(command, 0)
        self.assertEqual(calculated, 18)

    def test_missing_indoor_temperature_uses_emergency_in_the_calculation(self) -> None:
        command, calculated, difference, adjustment = self._positions(
            current=None,
            outdoor=None,
            max_position=40,
        )
        self.assertIsNone(difference)
        self.assertIsNone(adjustment)
        self.assertEqual(calculated, 14)
        self.assertEqual(command, 14)

    def test_off_with_a_missing_sensor_closes_instead_of_using_emergency(self) -> None:
        command, calculated, difference, _ = self._positions(
            current=None,
            hvac_off=True,
            outdoor=None,
        )
        self.assertIsNone(difference)
        self.assertEqual(calculated, 14)
        self.assertEqual(command, 0)


if __name__ == "__main__":
    unittest.main()
