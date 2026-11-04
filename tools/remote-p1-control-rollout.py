"""Approved P1: replace only control, retain state/key, binary rollback on failure."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
import urllib.request

EXPECTED = 'c76c8f6c3ad6a0e33e752d6c829be5e0f4644db00a5f04bd464ffa546c30e456'
binary = Path('/opt/vpnn-control/vpnn-control')
candidate = binary.with_name('.vpnn-control.p1-candidate')
state = Path('/var/lib/vpnn-control/state.json')
signing = Path(str(state) + '.signing')
units = ['vpnn-node-sync', 'vpnn-dns', 'vpnn-vk', 'vpnn-egress', 'x-ui', 'vps-vk', 'nginx', 'fail2ban']


def run(*args):
    result = subprocess.run(args, capture_output=True, text=True, timeout=30)
    if result.returncode:
        raise RuntimeError('Command failed: ' + args[0])
    return result.stdout.strip()


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def health():
    with urllib.request.urlopen('http://127.0.0.1:8098/health', timeout=3) as response:
        return response.status == 200 and json.load(response).get('status') == 'ok'


def invocations():
    return {unit: run('systemctl', 'show', unit, '--property=InvocationID', '--value') for unit in units}


if os.geteuid() != 0 or not state.is_file() or not signing.is_file():
    raise RuntimeError('Expected existing root-owned production layout')
if binary.is_symlink() or candidate.is_symlink() or digest(candidate) != EXPECTED:
    raise RuntimeError('Candidate integrity or target check failed')
entry = run('systemctl', 'show', 'vpnn-control', '--property=ExecStart', '--value')
if not all(value in entry for value in [str(binary), str(state), '/etc/vpnn-control/admin.secret', 'https://vpn.chichy.space']):
    raise RuntimeError('Unexpected control service arguments')
for unit in ['vpnn-control', *units]:
    if run('systemctl', 'is-active', unit) != 'active':
        raise RuntimeError('Preflight service not active')
node = json.loads(Path('/run/vpnn-node/status.json').read_text())
old_state = json.loads(state.read_text())
if not node.get('healthy') or node.get('appliedVersion') != old_state['version']:
    raise RuntimeError('Node not converged before rollout')
before = invocations()
old_hash = digest(binary)
key_hash = digest(signing)
permissions = binary.stat()
backup = Path('/var/backups/vpnn-control') / ('p1-' + time.strftime('%Y%m%d-%H%M%S', time.gmtime()))
backup.mkdir(mode=0o700, parents=True, exist_ok=False)
shutil.copy2(binary, backup / 'vpnn-control')
os.chmod(backup / 'vpnn-control', 0o700)
started = time.monotonic()
replaced = False
stopped = False
try:
    run('systemctl', 'stop', 'vpnn-control')
    stopped = True
    for source, name in [(state, 'state.json'), (signing, 'state.json.signing')]:
        shutil.copy2(source, backup / name)
        os.chmod(backup / name, 0o600)
    os.chown(candidate, permissions.st_uid, permissions.st_gid)
    os.chmod(candidate, permissions.st_mode & 0o777)
    os.replace(candidate, binary)
    replaced = True
    run('systemctl', 'start', 'vpnn-control')
    for _ in range(60):
        try:
            current = json.loads(state.read_text())
            node = json.loads(Path('/run/vpnn-node/status.json').read_text())
            if health() and node.get('healthy') and node.get('appliedVersion') == current['version']:
                break
        except (OSError, ValueError):
            pass
        time.sleep(1)
    else:
        raise RuntimeError('Control/node health did not converge')
    after = invocations()
    if before != after or digest(signing) != key_hash or digest(binary) != EXPECTED:
        raise RuntimeError('Unexpected service invocation or key/integrity change')
    if current['devices'] != old_state['devices'] or current['groups'] != old_state['groups']:
        raise RuntimeError('Device/group state changed unexpectedly')
    result = {'ok': True, 'backupDirectory': str(backup), 'oldBinarySha256': old_hash,
              'newBinarySha256': EXPECTED, 'oldVersion': old_state['version'], 'newVersion': current['version'],
              'signingKeyUnchanged': True, 'otherServiceInvocationsUnchanged': True,
              'nodeHealthy': True, 'elapsedSeconds': round(time.monotonic() - started, 2), 'rolledBack': False}
except Exception as error:
    if replaced:
        restore = binary.with_name('.vpnn-control.p1-rollback')
        shutil.copy2(backup / 'vpnn-control', restore)
        os.chown(restore, permissions.st_uid, permissions.st_gid)
        os.chmod(restore, permissions.st_mode & 0o777)
        os.replace(restore, binary)
    if stopped:
        run('systemctl', 'restart', 'vpnn-control')
    result = {'ok': False, 'errorType': type(error).__name__, 'backupDirectory': str(backup),
              'rolledBack': replaced, 'stateRestored': False}
(backup / 'result.json').write_text(json.dumps(result, indent=2))
print(json.dumps(result))
if not result['ok']:
    raise SystemExit(1)
