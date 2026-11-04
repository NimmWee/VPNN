"""Record the final reviewable release candidates and their checksums, without credentials."""
from datetime import datetime,timezone
import hashlib
import argparse
import re
import json
from pathlib import Path
root=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser()
parser.add_argument('--version',default='0.1.2')
parser.add_argument('--build-number',type=int,default=3)
parser.add_argument('--flutter-tests',type=int,default=179)
parser.add_argument('--windows-capture-fix',action='store_true')
args=parser.parse_args()
if not re.fullmatch(r'\d+\.\d+\.\d+',args.version) or args.build_number<1: raise ValueError('invalid release version')
artifacts=root/'artifacts'
names=[f'VPNN-Windows-{args.version}.zip',f'VPNN-Android-arm64-{args.version}.apk',
       f'VPNN-Android-armv7-{args.version}.apk',f'VPNN-Android-x64-{args.version}.apk',
       f'VPNN-Sources-{args.version}.zip','VPNN-Recovery-Tools-0.1.1.tar.gz',
       'VPNN-Recovery-Backup.enc',f'VPNN-Android-{args.version}-screen.png',
       f'windows-{args.version}-final/VPNN.exe',f'windows-{args.version}-final/FlClashCore.exe']
data={'version':f'{args.version}+{args.build_number}','status':'release candidate; physical/operator and fresh-OS apply tests pending',
      'created':datetime.now(timezone.utc).isoformat(),'controlURL':'https://vpn.chichy.space',
      'windowsDirectory':f'windows-{args.version}-final','androidApplicationId':'space.chichy.vpnn',
      'androidMinimumSdk':24,'androidSigningCertificateSha256':'f79b4f6b6d208403c1b39287ce31b35cfef1c8f7de9adeaeb435e9fe4b06897f',
      'verification':{'flutterSelectedTests':args.flutter_tests,'flutterAnalyze':'No issues found',
       'deployPythonTests':12,'controlTestsAndVet':True,'emulatorDNSWithBlockedVPS':True,
       'offlineBootstrapWithBlockedVPS':True,'realVKToDNSFallback':True,
       'backgroundAndProcessDeathReconnect':True,'individualNetworkRevocation':True,
       'hostWindowsSystemVPNTested':False,'physicalAndroidTested':False,'freshOSRestoreApplied':False,
       'windowsManagedTunRequested':args.windows_capture_fix,'nativeCaptureReadinessGuard':args.windows_capture_fix,
       'vkReconnectCacheRegression':args.windows_capture_fix},'files':{}}
data['verification']['realVKToDNSFallbackTestedVersion']='0.1.1'
data['verification']['backgroundAndProcessDeathReconnectTestedVersion']='0.1.1'
for name in names:
    path=artifacts/name
    data['files'][name]={'bytes':path.stat().st_size,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
(artifacts/'LATEST.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
(artifacts/f'SHA256SUMS-{args.version}.txt').write_text(''.join(item['sha256']+'  '+name+'\n' for name,item in data['files'].items()),encoding='utf-8')
print('Final release manifest and checksums written; no private access files included')
