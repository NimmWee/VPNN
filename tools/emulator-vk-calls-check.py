"""Check managed VK in the owned emulator with direct VPS blocked; CAPTCHA remains manual."""
import json
from pathlib import Path
import re
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

root = Path(__file__).resolve().parents[1]
adb_path = str(root / '.toolchains/android-sdk/platform-tools/adb.exe')
base = [adb_path, '-s', 'emulator-5554', 'shell']


def adb(*args, check=True):
    return subprocess.run([*base, *args], capture_output=True, text=True, timeout=85, check=check)


def helper(action):
    result = subprocess.run([sys.executable, str(root / 'tools/emulator-release-onboard.py'), action], capture_output=True, text=True, timeout=40)
    if result.returncode:
        raise RuntimeError('isolated UI action failed: ' + action)


def observe():
    adb('uiautomator', 'dump', '/sdcard/vpnn-vk-check.xml')
    return ET.fromstring(adb('cat', '/sdcard/vpnn-vk-check.xml').stdout)


uid_result = adb('cmd', 'package', 'list', 'packages', '-U', 'space.chichy.vpnn').stdout
uid = re.search(r'package:space\.chichy\.vpnn uid:(\d+)', uid_result)
if not uid:
    raise SystemExit('isolated package UID not found')
rules = [
    ['OUTPUT', '-d', '89.125.120.163/32', '-m', 'comment', '--comment', 'VPNN-vk-calls-direct', '-j', 'REJECT'],
    ['OUTPUT', '!', '-o', 'tun0', '-p', 'tcp', '--dport', '443', '-m', 'owner', '!', '--uid-owner', uid[1],
     '-m', 'comment', '--comment', 'VPNN-vk-calls-probe', '-j', 'REJECT'],
]
for rule in rules:
    if adb('su', '0', 'iptables', '-C', *rule, check=False).returncode == 0:
        raise SystemExit('an owned test rule already exists')
inserted = []
try:
    adb('su', '0', 'iptables', '-I', *rules[0])
    inserted.append(rules[0])
    helper('scroll-up')
    helper('scroll-up')
    helper('vk')
    tree = observe()
    if any((n.get('content-desc') or '').split('\n')[0] == 'Connect' and n.get('enabled') == 'true' for n in tree.iter('node')):
        helper('connect')
    deadline = time.monotonic() + 110
    while time.monotonic() < deadline:
        tree = observe()
        if any(n.get('package') == 'com.android.vpndialogs' for n in tree.iter('node')):
            helper('allow-vpn')
            continue
        labels = [n.get('content-desc') or n.get('text') or '' for n in tree.iter('node')]
        if any('Open verification' in text for text in labels):
            raise RuntimeError('VK requested manual CAPTCHA in the isolated Android run')
        if 'Tunnel enabled' in labels and 'Transport ready' in labels and adb('su', '0', 'ip', 'link', 'show', 'tun0', check=False).returncode == 0:
            break
        time.sleep(1)
    else:
        raise RuntimeError('managed VK did not become ready before deadline')
    exported = subprocess.run([sys.executable, str(root / 'tools/emulator-diagnostics-check.py'), '--version', '0.1.4', '--mode', 'vk', '--output-prefix', 'vk-calls-emulator-before-probe'], capture_output=True, text=True, timeout=40)
    if exported.returncode:
        (root / 'private/transport-test/vk-calls-export-failure.log').write_text(exported.stdout + exported.stderr)
        raise RuntimeError('could not confirm the active VK mode and native counters before the independent probe')
    adb('su', '0', 'iptables', '-I', *rules[1])
    inserted.append(rules[1])
    result = adb('env', 'SSL_CERT_DIR=/apex/com.android.conscrypt/cacerts', '/data/local/tmp/vpnn-http-egress-check',
                 '-blocked-peer', '89.125.120.163:22', '-expect-ip', '89.125.120.163', check=False)
    if result.returncode:
        raise RuntimeError('independent HTTPS through managed VK failed')
    print(result.stdout.strip())
    print(json.dumps({'managedVK': True, 'directVPSBlocked': True, 'independentProbeOutsideTunBlocked': True, 'captchaSolverUsed': False}))
finally:
    failures = []
    for rule in reversed(inserted):
        if adb('su', '0', 'iptables', '-D', *rule, check=False).returncode:
            failures.append('owned test rule removal failed')
    if failures:
        raise RuntimeError('; '.join(failures))
    print('OWNED_VK_TEST_RULES_REMOVED')
