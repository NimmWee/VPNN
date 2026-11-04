import json
from pathlib import Path
import shutil
import urllib.request
from bootstrap_toolchains import ROOT, DOWNLOADS, install

version = '9.8.0'
url = f'https://downloads.gradle.org/distributions/gradle-{version}-all.zip'
lock_path = ROOT / 'gradle.lock.json'
if lock_path.exists():
    checksum = json.loads(lock_path.read_text())['checksum']
else:
    with urllib.request.urlopen(f'https://downloads.gradle.org/distributions/gradle-{version}-all.zip.sha256', timeout=30) as response:
        checksum = response.read().decode().split()[0]
item = {'name':'Gradle', 'version':version, 'url':url, 'filename':f'gradle-{version}-all.zip', 'algorithm':'sha256', 'checksum':checksum, 'destination':'.toolchains/gradle', 'extract':False}
(ROOT/'gradle.lock.json').write_text(json.dumps(item,indent=2))
install(item)
distribution = ROOT / '.cache/gradle/wrapper/dists' / f'gradle-{version}-all'
for directory in distribution.iterdir():
    if directory.is_dir():
        shutil.copyfile(DOWNLOADS/item['filename'], directory/item['filename'])
        print('Cached Gradle in ' + str(directory), flush=True)
