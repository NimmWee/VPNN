"""Remove only the temporary plaintext snapshot already encrypted and verified locally."""
from pathlib import Path
import json
stage=Path('/root/vpnn-control-stage').resolve()
path=stage/'recovery.tar.gz'
if path.exists():
    if path.is_symlink() or path.resolve().parent!=stage:
        raise RuntimeError('unexpected temporary snapshot path')
    path.unlink()
print(json.dumps({'ownedPlaintextSnapshotRemoved':True,'productionServicesChanged':False}))
