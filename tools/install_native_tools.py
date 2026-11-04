import json
import os
from pathlib import Path
import subprocess
import urllib.request

from bootstrap_toolchains import ROOT, DOWNLOADS, install, sha, read_json

metadata_path = DOWNLOADS / 'go-metadata.json'
if not metadata_path.exists():
    release = next(x for x in read_json('https://go.dev/dl/?mode=json&include=all') if x['version'] == 'go1.27.3')
    metadata = next(x for x in release['files'] if x.get('os') == 'windows' and x.get('arch') == 'amd64' and x.get('kind') == 'archive')
    metadata_path.write_text(json.dumps(metadata))
metadata = json.loads(metadata_path.read_text())
item = {
    'name': 'Go', 'version': metadata['version'],
    'url': 'https://go.dev/dl/' + metadata['filename'],
    'filename': metadata['filename'], 'algorithm': 'sha256',
    'checksum': metadata['sha256'], 'destination': '.toolchains',
}
install(item)
(ROOT / 'native-toolchains.lock.json').write_text(json.dumps({'go': item, 'rust': '1.99.0'}, indent=2))

rustup = DOWNLOADS / 'rustup-init.exe'
checksum_path = DOWNLOADS / 'rustup-checksum.txt'
if not checksum_path.exists():
    with urllib.request.urlopen('https://static.rust-lang.org/rustup/dist/x86_64-pc-windows-msvc/rustup-init.exe.sha256', timeout=30) as response:
        checksum_path.write_text(response.read().decode())
expected = checksum_path.read_text().split()[0]
if not rustup.exists() or sha(rustup, 'sha256') != expected:
    with urllib.request.urlopen('https://static.rust-lang.org/rustup/dist/x86_64-pc-windows-msvc/rustup-init.exe', timeout=90) as response, rustup.open('wb') as stream:
        for block in iter(lambda: response.read(1024 * 1024), b''):
            stream.write(block)
if sha(rustup, 'sha256') != expected:
    raise RuntimeError('Rustup checksum mismatch')
env = dict(os.environ)
env['CARGO_HOME'] = str(ROOT / '.toolchains/cargo')
env['RUSTUP_HOME'] = str(ROOT / '.toolchains/rustup')
env['RUSTUP_INIT_SKIP_PATH_CHECK'] = 'yes'
subprocess.run([str(rustup), '-y', '--no-modify-path', '--profile', 'minimal', '--default-host', 'x86_64-pc-windows-msvc', '--default-toolchain', '1.99.0'], env=env, check=True)
subprocess.run([str(ROOT / '.toolchains/cargo/bin/rustup.exe'), 'target', 'add', 'x86_64-linux-android', '--toolchain', '1.99.0'], env=env, check=True)
