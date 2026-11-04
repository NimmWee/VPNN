"""Exercise the real opt-in VK -> DNS fallback only in the isolated emulator."""
from pathlib import Path
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
root=Path(__file__).resolve().parents[1]
base=[str(root/'.toolchains/android-sdk/platform-tools/adb.exe'),'-s','emulator-5554','shell']
def helper(action):
    return subprocess.run([sys.executable,str(root/'tools/emulator-release-onboard.py'),action],capture_output=True,text=True,timeout=60,check=True).stdout
helper('connect')
end=time.monotonic()+170
seen=set()
while time.monotonic()<end:
    subprocess.run(base+['uiautomator','dump','/sdcard/vpnn-fallback-ui.xml'],capture_output=True,timeout=30,check=True)
    result=subprocess.run(base+['cat','/sdcard/vpnn-fallback-ui.xml'],capture_output=True,text=True,timeout=10,check=True)
    tree=ET.fromstring(result.stdout)
    texts=[n.get('content-desc') or n.get('text') or '' for n in tree.iter('node')]
    for value in ['Working…','Transport ready','Establishing transport…','Using a backup connection mode.','Internet check passed']:
        if value in texts and value not in seen:
            seen.add(value)
            print(value,flush=True)
    if 'Using a backup connection mode.' in texts and 'Transport ready' in texts:
        result=subprocess.run([sys.executable,str(root/'tools/emulator-blocked-vps-check.py')],capture_output=True,text=True,timeout=90)
        print(result.stdout.strip(),flush=True)
        if result.returncode: raise RuntimeError('fallback egress check failed')
        print('REAL_VK_TO_DNS_FALLBACK_HTTPS_OK',flush=True)
        break
    time.sleep(3)
else:
    raise RuntimeError('real backup connection did not reach ready state')
