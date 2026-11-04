import json
import os
from pathlib import Path
import subprocess

root = Path(__file__).resolve().parents[1]
sdk = root / '.toolchains/android-sdk'
manager = sdk / 'cmdline-tools/19.0/bin/sdkmanager.bat'
packages = ['platform-tools', 'emulator', 'platforms;android-37.0', 'build-tools;37.0.0', 'ndk;28.2.13676358', 'system-images;android-35;default;x86_64']
(root / 'android-packages.lock.json').write_text(json.dumps({'packages': packages, 'image': 'system-images;android-35;default;x86_64'}, indent=2))
for label, arguments in [('licenses', ['--licenses']), ('packages', packages)]:
    print('Android SDK: ' + label, flush=True)
    with (root / 'logs' / ('android-' + label + '.log')).open('w', encoding='utf-8') as log:
        subprocess.run(['cmd.exe', '/d', '/c', str(manager), '--sdk_root=' + str(sdk), *arguments], input='y\n' * 200, text=True, stdout=log, stderr=subprocess.STDOUT, check=True)
    print('Android SDK: ' + label + ' complete', flush=True)
