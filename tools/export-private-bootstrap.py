"""Download and verify the administrator's private per-device offline bootstrap files."""
import base64
import json
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from urllib.request import Request, urlopen
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

root = Path(__file__).resolve().parents[1]
directory = root / 'private/transport-test'
def raw(value):
    return base64.urlsafe_b64decode(value + '=' * (-len(value) % 4))

for name in ['windows', 'emulator']:
    query = parse_qs(urlsplit((directory / f'{name}-production-invitation.txt').read_text().strip()).query)
    request = Request('https://vpn.chichy.space/api/device/bootstrap', headers={'Authorization': 'Bearer ' + query['token'][0]})
    with urlopen(request, timeout=30) as response:
        data = response.read()
    outer = json.loads(data)
    assert outer['format'] == 'vpnn-bootstrap-v1'
    envelope = outer['envelope']
    key = Ed25519PublicKey.from_public_bytes(raw(query['key'][0]))
    payload = raw(envelope['payload'])
    key.verify(raw(envelope['signature']), payload)
    content = json.loads(payload)
    assert content['enrollment']['device'] == query['device'][0]
    assert content['enrollment']['token'] == query['token'][0]
    inner = content['configuration']
    key.verify(raw(inner['signature']), raw(inner['payload']))
    assert json.loads(raw(inner['payload']))['deviceId'] == query['device'][0]
    (directory / f'{name}-production-bootstrap.json').write_bytes(data)
print('Two private production bootstraps exported; both signatures and device bindings verified')
