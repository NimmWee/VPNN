"""Package the built release candidate without launching it or including credentials."""
import hashlib
import argparse
import re
import json
from pathlib import Path
import shutil
from datetime import datetime,timezone

root=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser()
parser.add_argument('--version',default='0.1.2')
parser.add_argument('--build-number',type=int,default=3)
args=parser.parse_args()
if not re.fullmatch(r'\d+\.\d+\.\d+',args.version) or args.build_number<1: raise ValueError('invalid release version')
source=root/'client/build/windows/x64/runner/Release'
target=root/f'artifacts/windows-{args.version}-final'
if target.exists():
    raise SystemExit('candidate directory already exists; inspect before replacing it')
if not (source/'VPNN.exe').exists():
    raise SystemExit('build the Windows release first')
shutil.copytree(source,target)
active=json.loads((root/'artifacts/LATEST.json').read_text())
shutil.copytree(root/'artifacts'/active['windowsDirectory']/'licenses',target/'licenses')
shutil.copy2(root/'transports/xray/LICENSE',target/'licenses/Xray-MPL-2.0.txt')
shutil.copy2(root/'client/core/Clash.Meta/LICENSE',target/'licenses/mihomo-GPL-3.0.txt')
shutil.copy2(root/'NOTICES.md',target/'NOTICES.md')
shutil.copy2(root/'docs/OPERATOR-GUIDE.md',target/'README-RU.md')
metadata={'version':f'{args.version}+{args.build_number}','platform':'windows-x64','build':'release','safeMode':False,'status':'release candidate; system routing requires separate user test','controlURL':'https://vpn.chichy.space','coreSha256':hashlib.sha256((target/'FlClashCore.exe').read_bytes()).hexdigest(),'created':datetime.now(timezone.utc).isoformat()}
(target/'VPNN-build.json').write_text(json.dumps(metadata,indent=2))
(target/'README.txt').write_text('''VPNN — Windows release candidate

Keep this entire directory together. Run VPNN.exe manually when ready.
Do not enable VPNN simultaneously with another system VPN during initial testing.
The agent has not launched this normal VPN build on the working computer.

Configuration/admin: https://vpn.chichy.space
Existing test invitations with 127.0.0.1 must be replaced by the private
Windows production invitation supplied separately. Invitations and keys
are deliberately absent from this archive.

Windows socket startup is fixed and verified through explicit SOCKS HTTPS;
DNS startup has a 90-second deadline and transport errors stop the tunnel.
The administrator can export a signed offline bootstrap file; import it in
VPNN to begin even when the control address is initially unreachable.
Optional automatic fallback tries other assigned modes through the same owner.
Full Windows system routing and physical Android/operator tests remain required.
Managed Windows connections now request TUN and IPv6 capture; allow the
administrator prompt. Capture failure is reported instead of showing connected.
Valid temporary VK TURN credentials can survive a mode switch in memory;
their original expiry and server rejection still require fresh authentication.

This is a GPL-3.0 FlClash-based client, with embedded FreeTurn, MasterDnsVPN
and ANet components. See licenses/ and the local sources.lock.json.
''',encoding='utf-8')
archive=shutil.make_archive(str(root/f'artifacts/VPNN-Windows-{args.version}'),'zip',target)
(root/'Start-VPNN-Release.cmd').write_bytes(f'@echo off\r\nstart "" "%~dp0artifacts\\windows-{args.version}-final\\VPNN.exe"\r\n'.encode('ascii'))
print(json.dumps({'directory':str(target),'archive':archive,'coreSha256':metadata['coreSha256']}))
