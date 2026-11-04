import io
import json
import os
from pathlib import Path
import sys
import tarfile

root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root/'deploy'))
import recovery

private=root/'private/recovery'
private.mkdir(exist_ok=True)
keyfile=private/'recovery.key'
if not keyfile.exists():
    keyfile.write_bytes(os.urandom(32))
key=keyfile.read_bytes()
buffer=io.BytesIO()
source=private/'server-snapshot.tar.gz'
with tarfile.open(fileobj=buffer,mode='w:gz') as target:
    with tarfile.open(source,'r:gz') as archive:
        for member in archive.getmembers():
            target.addfile(member,archive.extractfile(member) if member.isfile() else None)
    target.add(root/'private/signing',arcname='client-signing',recursive=True)
output=root/'artifacts/VPNN-Recovery-Backup.enc'
output.write_bytes(recovery.seal(buffer.getvalue(),key))
data=recovery.open_snapshot(output.read_bytes(),key)
with tarfile.open(fileobj=io.BytesIO(data),mode='r:gz') as verified:
    count=len(verified.getmembers())
source.unlink()
print(json.dumps({'encryptedBackup':str(output),'recoveryKey':str(keyfile),'verifiedEntries':count}))
