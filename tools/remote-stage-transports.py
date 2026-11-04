from pathlib import Path
path = Path('/root/vpnn-transport-stage')
path.mkdir(mode=0o700, exist_ok=True)
print('STAGE_READY')
