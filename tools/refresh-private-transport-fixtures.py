"""Refresh explicit diagnostics from signed production settings, without printing keys."""
import base64
import json
from pathlib import Path
from urllib.parse import parse_qs,urlsplit
from urllib.request import Request,urlopen
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

root=Path(__file__).resolve().parents[1]
private=root/'private/transport-test'
query=parse_qs(urlsplit((private/'windows-production-invitation.txt').read_text().strip()).query)
request=Request('https://vpn.chichy.space/api/device/config',headers={'Authorization':'Bearer '+query['token'][0]})
with urlopen(request,timeout=25) as response: envelope=json.load(response)
def raw(text): return base64.urlsafe_b64decode(text+'='*(-len(text)%4))
payload=raw(envelope['payload'])
Ed25519PublicKey.from_public_bytes(raw(query['key'][0])).verify(raw(envelope['signature']),payload)
data=json.loads(payload)
assert data['deviceId']==query['device'][0]
for profile in data['profiles']:
    config=json.loads(profile['config'])
    proxy=next(item for item in config['proxies'] if 'x-vpnn' in item)
    meta=proxy['x-vpnn']
    if profile['id']=='dns':
        (private/'dns-production.json').write_text(json.dumps(meta))
    elif profile['id']=='vk':
        (private/'vk-production.json').write_text(json.dumps(meta))
        client=json.loads((private/'xray-client.json').read_text())
        for outbound in client['outbounds']:
            if outbound.get('protocol')=='vless':
                for server in outbound['settings']['vnext']:
                    for user in server['users']: user['id']=proxy['uuid']
        (private/'xray-production-client.json').write_text(json.dumps(client))
print('Pinned production profiles and individual diagnostic access refreshed')
