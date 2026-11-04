"""Create a private Android release signing key; never print key passwords."""
import json
import os
from pathlib import Path
import secrets
import subprocess

root=Path(__file__).resolve().parents[1]
directory=root/'private/signing'
directory.mkdir(exist_ok=True)
record=directory/'android-release.json'
if record.exists():
    state=json.loads(record.read_text())
    if not Path(state['storeFile']).exists():
        raise SystemExit('signing record exists but key is missing; restore it from backup')
    print('Existing release signing key retained')
else:
    store=directory/'vpnn-release.p12'
    if store.exists():
        raise SystemExit('unmanaged signing key exists; refusing replacement')
    password=secrets.token_urlsafe(32)
    java=next((root/'.toolchains/java').glob('*/bin/keytool.exe'))
    environment=dict(os.environ,VPNN_SIGNING_PASSWORD=password)
    command=[str(java),'-genkeypair','-keystore',str(store),'-storetype','PKCS12','-alias','vpnn-release','-keyalg','RSA','-keysize','3072','-validity','10000','-dname','CN=VPNN Local Release','-storepass:env','VPNN_SIGNING_PASSWORD','-keypass:env','VPNN_SIGNING_PASSWORD','-noprompt']
    result=subprocess.run(command,env=environment,text=True,capture_output=True,timeout=60)
    if result.returncode:
        raise SystemExit('keytool failed; signing record was not created')
    record.write_text(json.dumps({'storeFile':str(store),'storePassword':password,'keyAlias':'vpnn-release','keyPassword':password}))
    print('Private release signing key created; back up private/signing securely')
