"""Approved revocation of the pinned emulator identity only, through the admin API."""
import hashlib
import json
from pathlib import Path
import subprocess
import time
import urllib.parse
import urllib.request

TARGET_SHA256 = '7b11359b3e73716573bda940b13b059202d5bba230af2912420945a55cfa4283'
state_path = Path('/var/lib/vpnn-control/state.json')
before = json.loads(state_path.read_text())
matches = [device for device in before['devices'].values()
           if hashlib.sha256(device['id'].encode()).hexdigest() == TARGET_SHA256]
if len(matches) != 1 or matches[0]['name'] != 'Android Emulator · transports' or not matches[0]['enabled']:
    raise RuntimeError('Pinned enabled emulator identity not found')
target = matches[0]['id']


def stable(device):
    return {key: value for key, value in device.items() if key not in ['lastSeen', 'ackVersion']}


def invocation(unit):
    return subprocess.check_output(['systemctl', 'show', unit, '--property=InvocationID', '--value'], text=True, timeout=10).strip()


units = ['vpnn-control', 'vpnn-node-sync', 'vpnn-dns', 'vpnn-vk', 'vpnn-egress', 'x-ui', 'vps-vk', 'nginx', 'fail2ban']
old_invocations = {unit: invocation(unit) for unit in units}
secret = Path('/etc/vpnn-control/admin.secret').read_text().strip()
request = urllib.request.Request('http://127.0.0.1:8098/api/admin/devices/' + urllib.parse.quote(target, safe='') + '/revoke',
                                 data=b'{}', method='POST',
                                 headers={'Authorization': 'Bearer ' + secret, 'Content-Type': 'application/json'})
with urllib.request.urlopen(request, timeout=10) as response:
    if response.status != 200:
        raise RuntimeError('Revocation rejected')
del secret, request
after = json.loads(state_path.read_text())
if after['devices'][target]['enabled'] or set(after['devices']) != set(before['devices']):
    raise RuntimeError('Unexpected device mutation')
if any(stable(value) != stable(after['devices'][key]) for key, value in before['devices'].items() if key != target):
    raise RuntimeError('Unrelated identity changed')
if before['groups'] != after['groups'] or {key: stable(value) for key, value in before['nodes'].items()} != {key: stable(value) for key, value in after['nodes'].items()}:
    raise RuntimeError('Groups or nodes changed')
for _ in range(60):
    node = json.loads(Path('/run/vpnn-node/status.json').read_text())
    if node.get('healthy') and node.get('appliedVersion') == after['version']:
        break
    time.sleep(1)
else:
    raise RuntimeError('Revocation did not converge')
new_invocations = {unit: invocation(unit) for unit in units}
active = {unit: subprocess.check_output(['systemctl', 'is-active', unit], text=True, timeout=10).strip() for unit in units}
print(json.dumps({'ok': True, 'targetFingerprint': TARGET_SHA256[:12], 'testIdentityRevoked': True,
                  'otherIdentitiesUnchanged': True, 'version': after['version'], 'nodeHealthy': True,
                  'dnsDevices': node.get('dnsDevices'), 'vkDevices': node.get('vkDevices'),
                  'serviceInvocationsChanged': [unit for unit in units if old_invocations[unit] != new_invocations[unit]],
                  'services': active, 'targetLeftRevoked': True}))
