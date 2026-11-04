"""Build a sanitized historical baseline; never connects to the VPS."""
import argparse
import json
from pathlib import Path


def aggregate_goodput(byte_counts, interval_seconds):
    if interval_seconds <= 0 or any(value < 0 for value in byte_counts):
        raise ValueError('Invalid measurement interval or byte count')
    return sum(byte_counts) * 8 / interval_seconds / 1000000


def summarize(snapshot):
    memory = snapshot.get('memoryKiB', {})
    total = memory.get('MemTotal')
    available = memory.get('MemAvailable')
    return {
        'schema': 1,
        'sourceKind': 'historical-not-live',
        'source': 'logs/production-health-final.json',
        'memoryMiB': {
            'total': total / 1024 if total is not None else None,
            'available': available / 1024 if available is not None else None,
            'used': (total - available) / 1024 if total is not None and available is not None else None,
        },
        'inventory': dict.fromkeys([
            'cpuModel', 'vCPU', 'cpuQuota', 'swapTotal', 'disk', 'inodes',
            'networkCapacity', 'cgroups', 'servicePSS', 'serviceFD',
            'nicDrops', 'conntrack', 'idleTenMinutes',
        ]),
        'pilotGates': {'availableReserveMiB': 200, 'belowReserveSeconds': 30,
                       'stopOnOOMOrRestart': True, 'p95RatioLimit': 2,
                       'eightUsersValidated': False},
    }


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot', type=Path, default=Path('logs/production-health-final.json'))
    parser.add_argument('--output', type=Path, default=Path('logs/capacity-baseline.json'))
    args = parser.parse_args()
    args.output.write_text(json.dumps(summarize(json.loads(args.snapshot.read_text())), indent=2) + '\n')
