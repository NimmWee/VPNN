"""Check background VPN and process-death cleanup in the owned emulator only."""
from pathlib import Path
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
root=Path(__file__).resolve().parents[1]
base=[str(root/'.toolchains/android-sdk/platform-tools/adb.exe'),'-s','emulator-5554','shell']
def adb(*args,check=True):
    return subprocess.run(base+list(args),capture_output=True,text=True,timeout=40,check=check)
def helper(action):
    return subprocess.run([sys.executable,str(root/'tools/emulator-release-onboard.py'),action],capture_output=True,text=True,timeout=60,check=True).stdout
def check_egress():
    result=subprocess.run([sys.executable,str(root/'tools/emulator-blocked-vps-check.py')],capture_output=True,text=True,timeout=90)
    print(result.stdout.strip(),flush=True)
    if result.returncode: raise RuntimeError('background/restarted DNS egress failed')
if adb('su','0','ip','link','show','tun0',check=False).returncode:
    raise SystemExit('the isolated DNS VPN must be active')
adb('input','keyevent','KEYCODE_HOME')
time.sleep(20)
check_egress()
print('BACKGROUND_DNS_HTTPS_OK',flush=True)
adb('am','force-stop','space.chichy.vpnn')
for _ in range(20):
    if adb('su','0','ip','link','show','tun0',check=False).returncode: break
    time.sleep(1)
else: raise RuntimeError('owned VPN interface survived force-stop')
adb('monkey','-p','space.chichy.vpnn','-c','android.intent.category.LAUNCHER','1')
time.sleep(2)
ui=helper('inspect')
if 'Disconnected' not in ui or 'Settings version:' not in ui:
    raise RuntimeError('restart did not recover disconnected state and saved settings')
helper('scroll-down')
helper('dns')
helper('connect')
for _ in range(35):
    if adb('su','0','ip','link','show','tun0',check=False).returncode==0: break
    time.sleep(2)
else: raise RuntimeError('DNS did not reconnect after process death')
check_egress()
print('PROCESS_DEATH_CLEANUP_AND_CACHED_RECONNECT_OK',flush=True)
