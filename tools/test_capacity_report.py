import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('capacity_report', Path(__file__).with_name('capacity-report.py'))
report = importlib.util.module_from_spec(spec)
spec.loader.exec_module(report)


class CapacityReportTests(unittest.TestCase):
    def test_memory_uses_binary_units_and_keeps_historical_source(self):
        result = report.summarize({'memoryKiB': {'MemTotal': 984568, 'MemAvailable': 453528}, 'token': 'secret'})
        self.assertAlmostEqual(result['memoryMiB']['used'], 518.59375)
        self.assertEqual(result['sourceKind'], 'historical-not-live')
        self.assertNotIn('secret', str(result))
        self.assertIsNone(result['inventory']['vCPU'])

    def test_goodput_uses_shared_wall_interval(self):
        self.assertEqual(report.aggregate_goodput([1000000, 2000000], 4), 6)
        with self.assertRaises(ValueError):
            report.aggregate_goodput([1], 0)


if __name__ == '__main__':
    unittest.main()
