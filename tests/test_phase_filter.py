"""Tests for phase_filter.py — zero tolerance for noise leakage."""

import sys
import os
import time
import unittest
from unittest.mock import patch

# Add parent to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from services.phase_filter import PhaseDetector, PhaseFilterManager


class TestPhaseDetectorESP32Trust(unittest.TestCase):
    """Layer 1: ESP32 connectedPhases field."""

    def setUp(self):
        self.det = PhaseDetector("TEST-001")

    def test_single_phase_zeroes_others(self):
        """Single phase connected — other phases MUST be zero."""
        data = {
            "deviceId": "TEST-001",
            "voltage": 230.0,
            "totalPower": 900.0,
            "energyTotal": 1.5,
            "connectedPhases": [True, False, False],
            "phases": [
                {"current": 3.14, "power": 721.5},
                {"current": 0.42, "power": 96.6},   # Noise!
                {"current": 0.18, "power": 41.4},   # Noise!
            ],
        }
        out = self.det.filter_data(data)

        self.assertEqual(out["phaseCount"], 1)
        self.assertAlmostEqual(out["phases"][0]["current"], 3.14)
        self.assertAlmostEqual(out["phases"][0]["power"], 721.5)
        self.assertEqual(out["phases"][1]["current"], 0)
        self.assertEqual(out["phases"][1]["power"], 0)
        self.assertEqual(out["phases"][2]["current"], 0)
        self.assertEqual(out["phases"][2]["power"], 0)
        # totalPower recalculated from connected only
        self.assertAlmostEqual(out["totalPower"], 721.5)

    def test_three_phase_passes_all(self):
        """All phases connected — all data passes."""
        data = {
            "deviceId": "TEST-001",
            "voltage": 230.0,
            "totalPower": 2100.0,
            "energyTotal": 5.0,
            "connectedPhases": [True, True, True],
            "phases": [
                {"current": 3.0, "power": 690.0},
                {"current": 3.1, "power": 713.0},
                {"current": 3.0, "power": 697.0},
            ],
        }
        out = self.det.filter_data(data)

        self.assertEqual(out["phaseCount"], 3)
        self.assertAlmostEqual(out["totalPower"], 690.0 + 713.0 + 697.0)

    def test_spike_on_connected_phase_rejected(self):
        """Even connected phase rejects impossible spikes."""
        data = {
            "deviceId": "TEST-001",
            "connectedPhases": [True, False, False],
            "phases": [
                {"current": 95.0, "power": 21850.0},  # Spike!
                {"current": 0, "power": 0},
                {"current": 0, "power": 0},
            ],
        }
        out = self.det.filter_data(data)
        self.assertEqual(out["phases"][0]["current"], 0)
        self.assertEqual(out["phases"][0]["power"], 0)

    def test_below_noise_floor_zeroed(self):
        """Sub-threshold readings on connected phase zeroed."""
        data = {
            "deviceId": "TEST-001",
            "connectedPhases": [True, False, False],
            "phases": [
                {"current": 0.08, "power": 3.2},  # Below floor
                {"current": 0, "power": 0},
                {"current": 0, "power": 0},
            ],
        }
        out = self.det.filter_data(data)
        self.assertEqual(out["phases"][0]["current"], 0)
        self.assertEqual(out["phases"][0]["power"], 0)


class TestPhaseDetectorHeuristic(unittest.TestCase):
    """Layer 2: Heuristic detection (no connectedPhases field)."""

    def setUp(self):
        self.det = PhaseDetector("TEST-002")

    def _feed_readings(self, phase_data_list, count=10):
        """Feed N identical readings."""
        for _ in range(count):
            data = {
                "deviceId": "TEST-002",
                "voltage": 230.0,
                "totalPower": 0,
                "energyTotal": 0,
                "phases": phase_data_list,
            }
            self.det.filter_data(data)

    def test_consistent_single_phase_detected(self):
        """Steady readings on Phase R only → single phase mode."""
        self._feed_readings([
            {"current": 3.0, "power": 690.0},
            {"current": 0.0, "power": 0.0},
            {"current": 0.0, "power": 0.0},
        ], count=10)

        self.assertEqual(self.det.phase_count, 1)
        self.assertEqual(self.det.connected_phases, [True, False, False])

    def test_sporadic_noise_not_detected_as_phase(self):
        """Intermittent noise on Phase Y — should NOT register."""
        for i in range(10):
            noise_y = 0.5 if i % 3 == 0 else 0.0  # Sporadic
            data = {
                "deviceId": "TEST-002",
                "voltage": 230.0,
                "totalPower": 0,
                "energyTotal": 0,
                "phases": [
                    {"current": 3.0, "power": 690.0},
                    {"current": noise_y, "power": noise_y * 230},
                    {"current": 0.0, "power": 0.0},
                ],
            }
            self.det.filter_data(data)

        self.assertFalse(self.det.connected_phases[1])

    def test_all_three_consistent(self):
        """Consistent readings on all three → 3-phase."""
        self._feed_readings([
            {"current": 3.0, "power": 690.0},
            {"current": 2.8, "power": 644.0},
            {"current": 3.1, "power": 713.0},
        ], count=10)

        self.assertEqual(self.det.phase_count, 3)


class TestPhaseFilterManager(unittest.TestCase):
    """Manager auto-creates detectors per device."""

    def test_multi_device_isolation(self):
        """Different devices get separate detectors."""
        mgr = PhaseFilterManager()

        data_1phase = {
            "deviceId": "DEV-A",
            "voltage": 230.0,
            "totalPower": 700.0,
            "energyTotal": 1.0,
            "connectedPhases": [True, False, False],
            "phases": [
                {"current": 3.0, "power": 690.0},
                {"current": 0.3, "power": 69.0},
                {"current": 0.0, "power": 0.0},
            ],
        }
        data_3phase = {
            "deviceId": "DEV-B",
            "voltage": 230.0,
            "totalPower": 2100.0,
            "energyTotal": 5.0,
            "connectedPhases": [True, True, True],
            "phases": [
                {"current": 3.0, "power": 690.0},
                {"current": 3.1, "power": 713.0},
                {"current": 3.0, "power": 697.0},
            ],
        }

        out_a = mgr.filter(data_1phase)
        out_b = mgr.filter(data_3phase)

        self.assertEqual(out_a["phaseCount"], 1)
        self.assertEqual(out_a["phases"][1]["power"], 0)

        self.assertEqual(out_b["phaseCount"], 3)
        self.assertGreater(out_b["phases"][1]["power"], 0)


class TestNoiseLeakageZeroTolerance(unittest.TestCase):
    """Critical: verify NO noise ever reaches output."""

    def test_repeated_noise_never_leaks(self):
        """100 readings with noise on disconnected phases — zero leakage."""
        mgr = PhaseFilterManager()

        for i in range(100):
            # Simulate real-world noise patterns
            import random
            noise_y = random.uniform(0, 2.0) if random.random() < 0.3 else 0.0
            noise_b = random.uniform(0, 1.5) if random.random() < 0.2 else 0.0

            data = {
                "deviceId": "LEAK-TEST",
                "voltage": 230.0,
                "totalPower": 700 + noise_y * 230 + noise_b * 230,
                "energyTotal": 1.0,
                "connectedPhases": [True, False, False],
                "phases": [
                    {"current": 3.0, "power": 700.0},
                    {"current": noise_y, "power": noise_y * 230},
                    {"current": noise_b, "power": noise_b * 230},
                ],
            }
            out = mgr.filter(data)

            # ZERO TOLERANCE — disconnected phases MUST be zero
            self.assertEqual(out["phases"][1]["current"], 0,
                             f"Iteration {i}: Phase Y noise leaked: {out['phases'][1]}")
            self.assertEqual(out["phases"][1]["power"], 0,
                             f"Iteration {i}: Phase Y noise leaked: {out['phases'][1]}")
            self.assertEqual(out["phases"][2]["current"], 0,
                             f"Iteration {i}: Phase B noise leaked: {out['phases'][2]}")
            self.assertEqual(out["phases"][2]["power"], 0,
                             f"Iteration {i}: Phase B noise leaked: {out['phases'][2]}")

            # totalPower must only reflect Phase R
            self.assertAlmostEqual(out["totalPower"], 700.0,
                                   msg=f"Iteration {i}: totalPower includes noise")


if __name__ == "__main__":
    unittest.main(verbosity=2)