"""Cold-start our emulator app with the config API unreachable, then verify DNS traffic."""
import json
from pathlib import Path
import re
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
import yaml

root=Path(__file__).resolve().parents[1]
adb=str(root/'.toolchains'/'android-sdk'/'platform-tools'/'adb.exe')
base=[adb,'-s','emulator-5554','shell']
package='com.follow.clash.dev'
rule=['OUTPUT','-d','10.0.2.2/32','-p','tcp','--dport','8098','-m','comment','--comment','VPNN-offline-config-test','-j','DROP']

def command(*args,timeout=15):
    return subprocess.run(base+list(args),capture_output=True,text=True,timeout=timeout)

def firewall(action):
    return command('su','0','iptables',action,*rule)

if firewall('-C').returncode==0:
    raise SystemExit('Our API-block rule already exists; inspect before changing it')
command('am','force-stop',package)
added=firewall('-I')
if added.returncode:
    raise SystemExit('Could not insert emulator-only API block: '+added.stderr)
try:
    started=time.monotonic()
    command('am','start','-n',package+'/com.follow.clash.MainActivity')
    button=None
    for attempt in range(8):
        name='/sdcard/vpnn-cached-connect-'+str(attempt)+'.xml'
        dumped=command('uiautomator','dump',name)
        if 'dumped' not in dumped.stdout:
            time.sleep(0.5)
            continue
        xml=command('cat',name).stdout
        tree=ET.fromstring(xml)
        candidates=[n for n in tree.iter('node') if n.get('content-desc')=='Connect' and n.get('enabled')=='true']
        if candidates:
            button=candidates[0]
            break
    if button is None:
        raise RuntimeError('Cached connection screen did not become ready')
    startup=time.monotonic()-started
    bounds=[int(v) for v in re.findall(r'\d+',button.get('bounds',''))]
    if len(bounds)!=4 or not(0<(bounds[1]+bounds[3])//2<2040):
        raise RuntimeError('Connect button is not safely visible')
    command('input','tap',str((bounds[0]+bounds[2])//2),str((bounds[1]+bounds[3])//2))
    deadline=time.monotonic()+20
    while time.monotonic()<deadline:
        if command('su','0','ip','link','show','tun0').returncode==0:
            break
        time.sleep(0.5)
    else:
        raise RuntimeError('Cached DNS VPN did not start')
    config=yaml.safe_load(command('run-as',package,'cat','files/config.yaml').stdout)
    modes=[p['x-vpnn']['mode'] for p in config['proxies'] if 'x-vpnn' in p]
    if modes!=['dns']:
        raise RuntimeError('The cached DNS profile must be selected for this test')
    probe=subprocess.run([sys.executable,str(root/'tools'/'emulator-blocked-vps-check.py')],capture_output=True,text=True,timeout=80)
    print(probe.stdout.strip())
    if probe.returncode:
        raise RuntimeError('HTTPS check failed: '+probe.stderr.strip())
    lines=command('su','0','iptables','-n','-v','-x','-L','OUTPUT').stdout.splitlines()
    counter=next(line for line in lines if 'VPNN-offline-config-test' in line)
    packets=int(counter.split()[0])
    result={'startupSeconds':round(startup,2),'apiPacketsBeforeConnection':packets,'httpsThroughDNS':True}
    print(json.dumps(result))
    (root/'logs'/'android-cached-connect-result.json').write_text(json.dumps(result,indent=2))
    if packets:
        raise RuntimeError('Connection attempted configuration delivery before the tunnel was available')
finally:
    removed=firewall('-D')
    if removed.returncode:
        raise SystemExit('Could not remove our API-block rule: '+removed.stderr)
    print('EMULATOR_API_BLOCK_REMOVED')
