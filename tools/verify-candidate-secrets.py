"""Check local candidate artifacts against known private credentials without printing them."""
import argparse
import json
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
import zipfile

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--manifest', default='p2-local/MANIFEST.json')
args = parser.parse_args()
artifacts = (root / 'artifacts').resolve()
manifest_path = (artifacts / args.manifest).resolve()
if not manifest_path.is_relative_to(artifacts):
    raise SystemExit('manifest must stay inside artifacts')
manifest = json.loads(manifest_path.read_text(encoding='utf-8-sig'))
terms = set()
private = root / 'private/transport-test'
secret_fields = {'key', 'dnsKey', 'uuid', 'clientId', 'token', 'password', 'storePassword', 'keyPassword', 'links'}


def collect(value, sensitive=False):
    if isinstance(value, dict):
        for key, item in value.items():
            collect(item, sensitive or key in secret_fields)
    elif isinstance(value, list):
        for item in value:
            collect(item, sensitive)
    elif sensitive and isinstance(value, str) and len(value) >= 8:
        terms.add(value.encode())


for filename in ['dns-production.json', 'vk-production.json', 'xray-production-client.json']:
    collect(json.loads((private / filename).read_text()))
for name in ['windows', 'emulator']:
    query = parse_qs(urlsplit((private / f'{name}-production-invitation.txt').read_text().strip()).query)
    terms.add(query['token'][0].encode())
collect(json.loads((root / 'private/signing/android-release.json').read_text()))
if not terms:
    raise SystemExit('no private scan terms available')
entries = 0
for name in manifest['files']:
    path = (manifest_path.parent / name).resolve()
    if not path.is_relative_to(artifacts):
        raise SystemExit('unsafe artifact path')
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as archive:
            for member in archive.infolist():
                if member.is_dir():
                    continue
                data = archive.read(member)
                if any(term in data for term in terms):
                    raise SystemExit('private value in candidate archive: ' + name)
                entries += 1
    else:
        data = path.read_bytes()
        if any(term in data for term in terms):
            raise SystemExit('private value in candidate file: ' + name)
        entries += 1
print(json.dumps({'knownPrivateValuesAbsent': True, 'artifactCount': len(manifest['files']), 'entriesScanned': entries}))
