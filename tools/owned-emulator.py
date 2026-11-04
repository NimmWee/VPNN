"""Run only the project test AVD; stop it with a private marker and verify console shutdown."""
import argparse
from pathlib import Path
import re
import subprocess
import time

import psutil


def main():
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tag', required=True)
    args = parser.parse_args()
    if not re.fullmatch(r'[a-z0-9-]{1,48}', args.tag):
        parser.error('invalid tag')
    private = root / 'private/transport-test'
    stop = private / f'{args.tag}-emulator.stop'
    if stop.exists():
        parser.error('stop marker exists; use a fresh tag')
    adb = str(root / '.toolchains/android-sdk/platform-tools/adb.exe')
    if len(subprocess.check_output([adb, 'devices'], text=True, timeout=10).strip().splitlines()) > 1:
        raise RuntimeError('existing device attached; launch refused')
    with (private / f'{args.tag}-emulator.log').open('wb') as log:
        process = subprocess.Popen([str(root / '.toolchains/android-sdk/emulator/emulator.exe'),
                                    '-avd', 'VPNN_API35', '-port', '5554', '-no-window', '-no-audio',
                                    '-gpu', 'swiftshader', '-memory', '2048', '-cores', '2', '-no-snapshot'],
                                   stdout=log, stderr=log, creationflags=subprocess.CREATE_NO_WINDOW)
        (private / f'{args.tag}-emulator.pid').write_text(str(process.pid))
        print('Owned isolated AVD launched', flush=True)
        try:
            deadline = time.monotonic() + 1200
            while process.poll() is None and not stop.exists() and time.monotonic() < deadline:
                time.sleep(.5)
        finally:
            descendants = []
            try:
                descendants = psutil.Process(process.pid).children(recursive=True)
            except psutil.Error:
                pass
            try:
                name = subprocess.check_output([adb, '-s', 'emulator-5554', 'emu', 'avd', 'name'], text=True, timeout=5)
                if name.splitlines()[0].strip() == 'VPNN_API35':
                    subprocess.run([adb, '-s', 'emulator-5554', 'emu', 'kill'], capture_output=True, timeout=10, check=True)
            except (subprocess.SubprocessError, IndexError):
                pass
            for child in reversed(descendants):
                try:
                    child.terminate()
                    child.wait(timeout=5)
                except psutil.NoSuchProcess:
                    pass
                except psutil.TimeoutExpired:
                    child.kill()
                    child.wait(timeout=5)
            if process.poll() is None:
                process.terminate()
            process.wait(timeout=10)
            deadline = time.monotonic() + 10
            while 'emulator-5554' in subprocess.check_output([adb, 'devices'], text=True, timeout=5) and time.monotonic() < deadline:
                time.sleep(.2)
            if 'emulator-5554' in subprocess.check_output([adb, 'devices'], text=True, timeout=5):
                raise RuntimeError('owned emulator shutdown not confirmed')
            print('Owned AVD console and process shutdown confirmed', flush=True)


if __name__ == '__main__':
    main()
