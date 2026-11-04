"""Package a local candidate without publishing or changing the active release."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import zipfile
import argparse
import re

root = Path(__file__).resolve().parents[1]
artifacts = root / 'artifacts'
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--version', default='0.1.3')
parser.add_argument('--build-number', type=int, default=4)
parser.add_argument('--verification', default='logs/performance-validation.json')
args = parser.parse_args()
version = args.version
if not re.fullmatch(r'\d+\.\d+\.\d+', version) or args.build_number < 1:
    raise SystemExit('invalid version or build number')
full_version = f'{version}+{args.build_number}'
target = artifacts / f'windows-{version}-candidate'
archive_path = artifacts / f'VPNN-Windows-{version}-candidate.zip'
manifest_path = artifacts / f'CANDIDATE-{version}.json'
if any(p.exists() for p in [target, archive_path, manifest_path]):
    raise SystemExit('candidate already exists; inspect it instead of replacing it')
source = root / 'client/build/windows/x64/runner/Release'
core_hash = hashlib.sha256((source / 'FlClashCore.exe').read_bytes()).hexdigest()
if json.loads((source / 'manifest.json').read_text())['coreSha256'] != core_hash:
    raise SystemExit('Core/Helper manifest mismatch')
apks = root / 'client/build/app/outputs/flutter-apk'
abi_files = {'arm64': 'arm64-v8a', 'armv7': 'armeabi-v7a', 'x64': 'x86_64'}
for abi in abi_files.values():
    if not (apks / f'app-{abi}-release.apk').exists():
        raise SystemExit('all signed APK builds are required')
shutil.copytree(source, target)
shutil.copytree(artifacts / 'windows-0.1.2-final/licenses', target / 'licenses')
shutil.copy2(root / 'NOTICES.md', target / 'NOTICES.md')
shutil.copy2(root / f'docs/PERFORMANCE-{version}.md', target / 'README-RU.md')
metadata = {'version': full_version, 'platform': 'windows-x64', 'safeMode': False,
            'status': 'local candidate; host routing, physical Android and operator tests pending',
            'coreSha256': core_hash, 'created': datetime.now(timezone.utc).isoformat()}
(target / 'VPNN-build.json').write_text(json.dumps(metadata, indent=2), encoding='utf-8')
(target / 'README.txt').write_text(f'VPNN {full_version} local candidate. Keep the entire folder together.\n'
    'Run VPNN.exe manually. Host system VPN was not started by the agent.\n'
    'See README-RU.md for verified changes and remaining test requirements.\n'
    'DNS MTU and duplication defaults are unchanged. No operator speed guarantee.\n'
    'Current release launcher and LATEST.json are unchanged. See README-RU.md.\n', encoding='utf-8')
with zipfile.ZipFile(archive_path, 'w', zipfile.ZIP_DEFLATED) as archive:
    for path in sorted(target.rglob('*')):
        if path.is_file():
            archive.write(path, path.relative_to(target).as_posix())
files = [archive_path, target / 'VPNN.exe', target / 'FlClashCore.exe']
for name, abi in abi_files.items():
    output = artifacts / f'VPNN-Android-{name}-{version}-candidate.apk'
    if output.exists():
        raise SystemExit('candidate APK already exists')
    shutil.copy2(apks / f'app-{abi}-release.apk', output)
    files.append(output)
files.append(artifacts / f'VPNN-Sources-{version}.zip')
benchmark = artifacts / f'VPNN-Benchmark-{version}.exe'
if benchmark.exists():
    raise SystemExit('candidate benchmark already exists')
shutil.copy2(artifacts / 'vpnn-bench.exe', benchmark)
files.append(benchmark)
manifest = {'version': full_version, 'status': metadata['status'], 'published': False,
            'windowsDirectory': target.name, 'verificationFile': args.verification,
            'files': {p.relative_to(artifacts).as_posix(): {'bytes': p.stat().st_size,
                     'sha256': hashlib.sha256(p.read_bytes()).hexdigest()} for p in files}}
manifest_path.write_text(json.dumps(manifest, indent=2), encoding='utf-8')
(artifacts / f'SHA256SUMS-{version}-candidate.txt').write_text(
    ''.join(f"{value['sha256']}  {name}\n" for name, value in manifest['files'].items()), encoding='utf-8')
print(json.dumps({'manifest': manifest_path.name, 'files': len(files), 'published': False}))
