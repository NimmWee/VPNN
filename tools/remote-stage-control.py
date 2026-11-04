from pathlib import Path
import json

path=Path('/root/vpnn-control-stage')
path.mkdir(mode=0o700,exist_ok=True)
path.chmod(0o700)
print(json.dumps({'stageReady':True}))
