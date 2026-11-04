import json
from pathlib import Path
import unittest

from report import summarize


class ReportTest(unittest.TestCase):
    def setUp(self):
        path = Path(__file__).with_name("synthetic.json")
        self.data = json.loads(path.read_text(encoding="utf-8"))

    def test_common_window_and_units(self):
        report = summarize(self.data)
        self.assertEqual(report["goodput_mbps"], 3)
        self.assertEqual(report["cpu_cores"], 0.5)
        self.assertEqual(report["ram_delta_mib"], 32)
        self.assertEqual(report["egress"], "synthetic")
        self.assertEqual(report["field_verdict"], "NOT TESTED")

    def test_extra_field_is_rejected(self):
        self.data["endpoint"] = "fixture.invalid"
        with self.assertRaises(ValueError):
            summarize(self.data)

    def test_fixture_cannot_claim_field_result(self):
        self.data["source"] = "field"
        with self.assertRaises(ValueError):
            summarize(self.data)

    def test_zero_duration_is_rejected(self):
        self.data["seconds"] = 0
        with self.assertRaises(ValueError):
            summarize(self.data)

    def test_negative_counter_is_rejected(self):
        self.data["payload_bytes"][0] = -1
        with self.assertRaises(ValueError):
            summarize(self.data)


if __name__ == "__main__":
    unittest.main()
