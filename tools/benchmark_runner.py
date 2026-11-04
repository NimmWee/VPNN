"""Bounded, explicit-proxy measurements; manages only processes created by this run."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import time

import psutil


def run_owned(command, private_log, timeout=720, companion=None):
    started = time.monotonic()
    owned = []
    max_rss = 0
    cpu = {}
    timed_out = False
    companion_failed = False
    flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
    with Path(private_log).open('wb') as log:
        try:
            if companion:
                owned.append(subprocess.Popen(companion, stdout=log, stderr=log, creationflags=flags))
            child = subprocess.Popen(command, stdout=log, stderr=log, creationflags=flags)
            owned.append(child)
            while child.poll() is None:
                if companion and owned[0].poll() is not None:
                    companion_failed = True
                    break
                total_rss = 0
                for process in owned:
                    try:
                        observed = psutil.Process(process.pid)
                        total_rss += observed.memory_info().rss
                        times = observed.cpu_times()
                        cpu[process.pid] = times.user + times.system
                    except psutil.Error:
                        pass
                max_rss = max(max_rss, total_rss)
                if time.monotonic() - started >= timeout:
                    timed_out = True
                    break
                time.sleep(.05)
        finally:
            for process in reversed(owned):
                if process.poll() is None:
                    process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
    return {'exitCode': child.returncode, 'timedOut': timed_out, 'companionFailed': companion_failed,
            'maxRssBytes': max_rss, 'cpuSeconds': sum(cpu.values()),
            'durationMs': round((time.monotonic() - started) * 1000, 3)}


def main():
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--private-log', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--xray-config', type=Path)
    parser.add_argument('bench_args', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    companion = None
    if args.xray_config:
        config = json.loads(args.xray_config.read_text())
        if not config.get('inbounds') or any(x.get('listen') != '127.0.0.1' or x.get('protocol') != 'socks' for x in config['inbounds']):
            parser.error('Xray must expose only explicit loopback SOCKS listeners')
        companion = [str(root / 'artifacts/xray-test.exe'), 'run', '-config', str(args.xray_config.resolve())]
    options = args.bench_args
    if options[:1] == ['--']:
        options = options[1:]
    if any(value == '-output' or value.startswith('-output=') for value in options):
        parser.error('use --report instead of -output')
    if args.report.exists() or args.report.with_suffix('.resources.json').exists():
        parser.error('report already exists; use a new name')
    resources = run_owned([str(root / 'artifacts/vpnn-bench.exe'), '-output', str(args.report.resolve()), *options],
                          args.private_log, companion=companion)
    resources_path = args.report.with_suffix('.resources.json')
    resources_path.write_text(json.dumps(resources, indent=2), encoding='utf-8')
    print(json.dumps(resources))
    raise SystemExit(0 if resources['exitCode'] == 0 and not resources['timedOut'] and not resources['companionFailed'] else 1)


if __name__ == '__main__':
    main()
