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


# Inclusive bands of target − current, and the cover position they select.
BANDS = (
    (-1.0, -0.1, 0),
    (0.0, 0.0, 8),
    (0.1, 0.1, 14),
    (0.2, 0.2, 19),
    (0.3, 0.4, 28),
    (0.5, 0.7, 44),
    (0.8, 1.0, 50),
    (1.1, 1.3, 56),
    (1.4, 1.7, 67),
    (1.8, 1.9, 83),
    (2.0, 3.0, 100),
)


class MappingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.mapping = mapping.parse_position_mapping(mapping.DEFAULT_POSITION_MAPPING)

    def test_default_spans_closed_to_open(self) -> None:
        self.assertEqual(mapping.DEFAULT_POSITION_MAPPING["-0.2"], 0)
        self.assertEqual(mapping.DEFAULT_POSITION_MAPPING["2.0"], 100)
        self.assertEqual(mapping.DEFAULT_EMERGENCY_POSITION, 14)

    def test_bands_match_the_published_table(self) -> None:
        for start, end, expected in BANDS:
            difference = start
            while difference <= end + 1e-9:
                with self.subTest(difference=round(difference, 1)):
                    self.assertEqual(
                        mapping.position_for_difference(self.mapping, round(difference, 1)),
                        expected,
                    )
                difference += 0.1

    def test_small_indoor_gap_opens_the_valve_partway(self) -> None:
        # Target 21.0 °C, current 20.7 °C. Difference 0.3 selects 28%.
        position, difference = mapping.cover_position(
            self.mapping,
            current=20.7,
            target=21.0,
            emergency=14,
            hvac_off=False,
        )
        self.assertEqual(difference, 0.3)
        self.assertEqual(position, 28)

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

    def test_below_the_first_key_uses_the_lowest_position_not_the_first_key(self) -> None:
        parsed = mapping.parse_position_mapping({"-0.2": 10, "0.0": 0, "1.0": 50})
        self.assertEqual(mapping.position_for_difference(parsed, -0.2), 0)
        self.assertEqual(mapping.position_for_difference(parsed, -1), 0)
        self.assertEqual(mapping.position_for_difference(parsed, 1), 50)
        self.assertEqual(mapping.position_for_difference(parsed, 0.0), 10)

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

    def test_outdoor_brackets(self) -> None:
        cases = (
            (-20, 35),
            (-10, 35),
            (-8, 35),
            (-5, 20),
            (-1, 20),
            (0, 10),
            (2, 10),
            (5, 0),
            (9.9, 0),
            (10, -15),
            (12, -15),
            (15, -40),
            (20, -40),
        )
        for outdoor, expected in cases:
            with self.subTest(outdoor=outdoor):
                self.assertEqual(
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
        self.assertEqual(adjustment, -15)
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
        self.assertEqual(indoor, 28)
        self.assertEqual(adjustment, 10)
        self.assertEqual(position, 38)

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
        self.assertEqual(adjustment, 35)
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


if __name__ == "__main__":
    unittest.main()
