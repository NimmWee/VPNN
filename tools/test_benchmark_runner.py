import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('benchmark_runner', Path(__file__).with_name('benchmark_runner.py'))
runner = importlib.util.module_from_spec(spec)
if spec.loader and Path(spec.origin).exists():
    spec.loader.exec_module(runner)


class RunnerTests(unittest.TestCase):
    def test_private_output_and_resource_sampling(self):
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / 'private.log'
            result = runner.run_owned([sys.executable, '-c', "import time;print('secret');time.sleep(.2)"], log, timeout=2)
            self.assertEqual(result['exitCode'], 0)
            self.assertGreater(result['maxRssBytes'], 0)
            self.assertNotIn('secret', str(result))
            self.assertIn('secret', log.read_text())

    def test_deadline_reaps_only_owned_child(self):
        with tempfile.TemporaryDirectory() as directory:
            result = runner.run_owned([sys.executable, '-c', 'import time;time.sleep(20)'], Path(directory) / 'private.log', timeout=.2)
            self.assertTrue(result['timedOut'])
            self.assertLess(result['durationMs'], 3000)

    def test_failed_companion_stops_measurement(self):
        with tempfile.TemporaryDirectory() as directory:
            result = runner.run_owned([sys.executable, '-c', 'import time;time.sleep(20)'],
                                      Path(directory) / 'private.log', timeout=2,
                                      companion=[sys.executable, '-c', 'raise SystemExit(7)'])
            self.assertTrue(result['companionFailed'])
            self.assertLess(result['durationMs'], 1500)


if __name__ == '__main__':
    unittest.main()
