"""Import a signed file and start DNS while the control VPS is blocked in our emulator."""
import json
import argparse
from pathlib import Path
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
root=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser()
parser.add_argument('--fresh',action='store_true')
args=parser.parse_args()
base=[str(root/'.toolchains/android-sdk/platform-tools/adb.exe'),'-s','emulator-5554','shell']
rule=['OUTPUT','-d','89.125.120.163/32','-m','comment','--comment','VPNN-offline-bootstrap','-j','REJECT']
def adb(*args, check=True):
    return subprocess.run(base+list(args),capture_output=True,text=True,timeout=85,check=check)
def helper(name,*args):
    result=subprocess.run([sys.executable,str(root/'tools'/name),*args],capture_output=True,text=True,timeout=40)
    if result.returncode: raise RuntimeError(name+' failed: '+result.stderr[-500:])
    return result.stdout
def observe():
    adb('uiautomator','dump','/sdcard/vpnn-release-ui.xml')
    return ET.fromstring(adb('cat','/sdcard/vpnn-release-ui.xml').stdout)
if args.fresh:
    adb('pm','clear','space.chichy.vpnn')
    adb('pm','grant','space.chichy.vpnn','android.permission.POST_NOTIFICATIONS')
    adb('monkey','-p','space.chichy.vpnn','-c','android.intent.category.LAUNCHER','1')
    deadline=time.monotonic()+35
    while time.monotonic()<deadline:
        try:
            if 'android.widget.Button Agree ' in helper('emulator-release-onboard.py','inspect'): break
        except RuntimeError: pass
        time.sleep(1)
    else: raise RuntimeError('fresh release did not show its first-use statement')
    helper('emulator-release-onboard.py','agree')
    helper('emulator-release-onboard.py','statement')
    for _ in range(3): helper('emulator-release-onboard.py','scroll-down')
    subprocess.run(base[:3]+['push',str(root/'private/transport-test/emulator-production-bootstrap.json'),'/sdcard/Download/VPNN-bootstrap.json'],check=True,capture_output=True)
    helper('emulator-release-onboard.py','bootstrap')
    helper('emulator-picker.py','roots')
    helper('emulator-picker.py','downloads')
if adb('su','0','ip','link','show','tun0',check=False).returncode==0:
    raise SystemExit('test requires the isolated VPN to be disconnected first')
if adb('su','0','iptables','-C',*rule,check=False).returncode==0:
    raise SystemExit('test rule already exists')
adb('su','0','iptables','-I',*rule)
try:
    helper('emulator-picker.py','file')
    print('SIGNED_BOOTSTRAP_IMPORTED_WITH_DIRECT_VPS_BLOCKED',flush=True)
    time.sleep(2)
    helper('emulator-release-onboard.py','scroll-up')
    helper('emulator-release-onboard.py','scroll-up')
    helper('emulator-release-onboard.py','dns')
    helper('emulator-release-onboard.py','scroll-down')
    helper('emulator-release-onboard.py','connect')
    end=time.monotonic()+110
    while time.monotonic()<end:
        tree=observe()
        if any(n.get('package')=='com.android.vpndialogs' for n in tree.iter('node')):
            helper('emulator-release-onboard.py','allow-vpn')
        if adb('su','0','ip','link','show','tun0',check=False).returncode==0:
            break
        time.sleep(2)
    else: raise RuntimeError('DNS tunnel did not start')
    result=adb('env','SSL_CERT_DIR=/apex/com.android.conscrypt/cacerts','/data/local/tmp/vpnn-http-egress-check','-blocked-peer','89.125.120.163:22','-expect-ip','89.125.120.163',check=False)
    print(result.stdout.strip())
    if result.returncode: raise RuntimeError('HTTPS through DNS failed')
    print(json.dumps({'offlineBootstrapImported':True,'directVPSBlocked':True,'httpsViaDNS':True}))
finally:
    removed=adb('su','0','iptables','-D',*rule,check=False)
    adb('rm','-f','/sdcard/Download/VPNN-bootstrap.json')
    if removed.returncode: raise RuntimeError('could not remove owned emulator-only rule')
    print('EMULATOR_OFFLINE_RULE_REMOVED')
