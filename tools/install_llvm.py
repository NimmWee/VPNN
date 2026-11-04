"""Install the pinned Windows libclang needed by Android bindgen."""
import json
import tarfile
from pathlib import Path

from bootstrap_toolchains import DOWNLOADS, ROOT, install, read_json


def main():
    lock = ROOT / 'llvm.lock.json'
    if lock.exists():
        item = json.loads(lock.read_text(encoding='utf-8'))
    else:
        release = read_json('https://api.github.com/repos/llvm/llvm-project/releases/tags/llvmorg-20.1.8')
        asset = next(x for x in release['assets'] if x['name'] == 'clang+llvm-20.1.8-x86_64-pc-windows-msvc.tar.xz')
        algorithm, checksum = asset['digest'].split(':', 1)
        item = {'name': 'LLVM Windows bindgen', 'version': '20.1.8',
                'url': asset['browser_download_url'], 'filename': asset['name'],
                'algorithm': algorithm, 'checksum': checksum,
                'destination': '.toolchains/llvm', 'extract': False}
        lock.write_text(json.dumps(item, indent=2), encoding='utf-8')
    DOWNLOADS.mkdir(exist_ok=True)
    install(item)
    destination = ROOT / item['destination']
    marker = destination / '.vpnn-llvm.json'
    if marker.exists() and json.loads(marker.read_text())['checksum'] == item['checksum']:
        print('LLVM bindgen files already installed', flush=True)
        return
    destination.mkdir(parents=True, exist_ok=True)
    with tarfile.open(DOWNLOADS / item['filename'], 'r|xz') as bundle:
        for member in bundle:
            relative = Path(*Path(member.name).parts[1:])
            if not member.isfile() or not ((relative.parent == Path('bin') and relative.suffix == '.dll') or relative.parts[:3] == ('lib', 'clang', '20')):
                continue
            target = (destination / relative).resolve()
            if not target.is_relative_to(destination.resolve()):
                raise RuntimeError('Unsafe LLVM archive member')
            target.parent.mkdir(parents=True, exist_ok=True)
            with bundle.extractfile(member) as source, target.open('wb') as output:
                while block := source.read(1024 * 1024):
                    output.write(block)
    if not (destination / 'bin/libclang.dll').is_file():
        raise RuntimeError('Official LLVM archive did not contain bin/libclang.dll')
    marker.write_text(json.dumps(item, indent=2), encoding='utf-8')
    print('Installed LLVM bindgen DLLs and resource files', flush=True)


if __name__ == '__main__':
    main()
