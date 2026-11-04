"""Exercise diagnostic export only in the isolated emulator and remove the created guest report."""
import json
import argparse
from pathlib import Path
import re
import subprocess
import time
import xml.etree.ElementTree as ET

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--version', default='0.1.3')
parser.add_argument('--mode', choices=['dns', 'vk'], default='dns')
parser.add_argument('--output-prefix', default='performance-emulator-diagnostics')
args = parser.parse_args()
if not re.fullmatch(r'[a-z0-9-]{1,80}', args.output_prefix):
    parser.error('invalid output prefix')
base = [str(root / '.toolchains/android-sdk/platform-tools/adb.exe'), '-s', 'emulator-5554', 'shell']
guest = '/sdcard/Download/VPNN-diagnostics.json'


def adb(*args, check=True):
    return subprocess.run([*base, *args], capture_output=True, text=True, timeout=25, check=check)


def observe():
    adb('uiautomator', 'dump', '/sdcard/vpnn-diagnostic-ui.xml')
    return ET.fromstring(adb('cat', '/sdcard/vpnn-diagnostic-ui.xml').stdout)


def tap(node):
    x1, y1, x2, y2 = map(int, re.findall(r'\d+', node.get('bounds')))
    adb('input', 'tap', str((x1+x2)//2), str((y1+y2)//2))


if adb('test', '-e', guest, check=False).returncode == 0:
    raise SystemExit('existing guest diagnostic file will not be overwritten')
tree = observe()
if any(n.get('package') == 'space.chichy.vpnn' for n in tree.iter('node')):
    action = next(n for n in tree.iter('node') if n.get('content-desc') == 'Export diagnostics')
    tap(action)
    tree = observe()
title = next(n for n in tree.iter('node') if n.get('resource-id') == 'android:id/title' and n.get('text') == 'VPNN-diagnostics.json')
save = next(n for n in tree.iter('node') if n.get('package') == 'com.android.documentsui' and n.get('resource-id') == 'android:id/button1' and n.get('text') == 'SAVE')
tap(save)
try:
    deadline = time.monotonic() + 12
    report = None
    while time.monotonic() < deadline:
        saved = adb('cat', guest, check=False)
        if saved.returncode == 0:
            try:
                report = json.loads(saved.stdout)
                break
            except ValueError:
                pass
        time.sleep(.2)
    if report is None:
        raise RuntimeError('diagnostic save did not finish before deadline')
    expected = {'schema', 'version', 'platform', 'mode', 'stage', 'stageElapsedMs', 'failure',
                'running', 'suspended', 'captureReady', 'coreProbeReachable', 'systemEgressVerified',
                'automaticFallback', 'usedFallback', 'usingCache', 'configurationVersion', 'counters', 'events'}
    assert set(report) == expected
    assert report['schema'] == 1 and report['version'].startswith(args.version + '+')
    assert report['mode'] == args.mode and report['stage'] == 'ready' and report['captureReady'] is True
    assert report['systemEgressVerified'] is False
    assert len(report['events']) <= 32
    assert all(type(value) is int and value >= 0 for value in report['counters'].values())
    assert report['counters']['dnsDownloadMTU' if args.mode == 'dns' else 'vkStreams'] > 0
    (root / f'logs/{args.output_prefix}.json').write_text(json.dumps(report, indent=2))
    print(json.dumps({'exported': True, 'schema': 1, 'version': report['version'], 'numericCounters': True, 'systemEgressNotClaimed': True}))
finally:
    adb('rm', '-f', guest)
    print('OWNED_GUEST_DIAGNOSTIC_REMOVED')
