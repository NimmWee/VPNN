"""Ten-minute read-only memory/CPU sample; no claim that other users are idle."""
import json
from pathlib import Path
import time


def sample():
    memory = {line.split(':')[0]: int(line.split()[1])
              for line in Path('/proc/meminfo').read_text().splitlines()
              if line.startswith(('MemTotal:', 'MemAvailable:', 'SwapFree:'))}
    return {'elapsedSeconds': round(time.monotonic() - started, 2), 'memoryKiB': memory,
            'cpuTicks': [int(value) for value in Path('/proc/stat').read_text().splitlines()[0].split()[1:]],
            'loadAverage': Path('/proc/loadavg').read_text().split()[:3]}


started = time.monotonic()
samples = []
for index in range(21):
    if index:
        time.sleep(max(0, started + index * 30 - time.monotonic()))
    samples.append(sample())
print(json.dumps({'schema': 1, 'sourceKind': 'live-read-only', 'idleConfirmed': False,
                  'intervalSeconds': 30, 'samples': samples}))
