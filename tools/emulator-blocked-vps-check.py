"""Temporarily reject direct VPS access only inside our test emulator; always remove our rule."""
from pathlib import Path
import subprocess

root=Path(__file__).resolve().parents[1]
adb=str(root/'.toolchains'/'android-sdk'/'platform-tools'/'adb.exe')
base=[adb,'-s','emulator-5554','shell']
rules=[
    ['OUTPUT','-d','89.125.120.163/32','-m','comment','--comment','VPNN-transport-validation','-j','REJECT'],
    ['OUTPUT','!','-o','tun0','-p','tcp','--dport','443','-m','comment','--comment','VPNN-no-direct-https','-j','REJECT'],
]
def firewall(action,rule):
    return subprocess.run(base+['su','0','iptables',action]+rule,capture_output=True,text=True)

if subprocess.run(base+['su','0','ip','link','show','tun0'],capture_output=True).returncode:
    raise SystemExit('Our emulator VPN must be active before this test')
for rule in rules:
    if firewall('-C',rule).returncode==0:
        raise SystemExit('A validation rule already exists; inspect its owner before changing it')
inserted=[]
try:
    for rule in rules:
        insert=firewall('-I',rule)
        if insert.returncode:
            raise SystemExit('Could not insert emulator-only test rule: '+insert.stderr)
        inserted.append(rule)
    p=subprocess.run(base+['env','SSL_CERT_DIR=/apex/com.android.conscrypt/cacerts',
        '/data/local/tmp/vpnn-http-egress-check','-blocked-peer','89.125.120.163:22','-expect-ip','89.125.120.163'],
        capture_output=True,text=True,timeout=75)
    print(p.stdout.strip())
    if p.stderr:
        print(p.stderr.strip())
    result=p.returncode
finally:
    failures=[]
    for rule in reversed(inserted):
        removed=firewall('-D',rule)
        if removed.returncode:
            failures.append(removed.stderr)
    if failures:
        raise SystemExit('Could not remove our emulator test rule: '+str(failures))
    print('EMULATOR_TEST_RULE_REMOVED')
raise SystemExit(result)
