import concurrent.futures
import copy
import json
from pathlib import Path
import urllib.request
import xml.dom.minidom as DOM
import xml.etree.ElementTree as ET

from bootstrap_toolchains import ROOT, install

SDK = ROOT / '.toolchains/android-sdk'
REPO = 'https://dl.google.com/android/repository/'
PACKAGES = ['platform-tools', 'emulator', 'platforms;android-37.0', 'build-tools;37.0.0', 'ndk;28.2.13676358', 'system-images;android-35;default;x86_64']

def fetch(url):
    with urllib.request.urlopen(url, timeout=45) as response:
        return response.read()

def resolve_packages():
    lock = ROOT / 'android-downloads.lock.json'
    if lock.exists():
        stored = json.loads(lock.read_text())['packages']
        if all('metadata_file' in x and (ROOT / x['metadata_file']).exists() for x in stored):
            for item in stored:
                item['local_package_xml'] = (ROOT / item['metadata_file']).read_text(encoding='utf-8')
            return stored
    documents = [(REPO, fetch(REPO + 'repository2-4.xml')),
                 (REPO + 'sys-img/android/', fetch(REPO + 'sys-img/android/sys-img2-3.xml'))]
    items = []
    for path in PACKAGES:
        for base, xml in documents:
            root = ET.fromstring(xml)
            candidates = [x for x in root.iter('remotePackage') if x.attrib['path'] == path and x.find('obsolete') is None and (x.find('channelRef') is None or x.find('channelRef').get('ref') == 'channel-0')]
            if not candidates:
                continue
            package = candidates[0]
            archive = next(x for x in package.iter('archive') if x.findtext('host-os') in (None, 'windows') and x.find('complete') is not None)
            item = {'name': 'SDK ' + path.replace(';', '-'), 'version': '.'.join(x.text for x in package.find('revision')), 'package': path,
                    'url': base + archive.findtext('complete/url'), 'filename': archive.findtext('complete/url').split('/')[-1],
                    'algorithm': 'sha1', 'checksum': archive.findtext('complete/checksum'), 'size': int(archive.findtext('complete/size')),
                    'destination': str((SDK / Path(*path.split(';'))).relative_to(ROOT)).replace('\\', '/'), 'strip_prefix': '__first__'}
            document = DOM.parseString(xml)
            repo = document.documentElement
            document.renameNode(repo, 'http://schemas.android.com/repository/android/common/02', 'common:repository')
            repo.setAttribute('xmlns:common', 'http://schemas.android.com/repository/android/common/02')
            original = next(x for x in repo.childNodes if x.nodeType == x.ELEMENT_NODE and x.localName == 'remotePackage' and x.getAttribute('path') == path)
            local = document.createElement('localPackage')
            local.setAttribute('path', path)
            local.setAttribute('obsolete', 'false')
            for child in original.childNodes:
                if child.nodeType == child.ELEMENT_NODE and child.localName in ['type-details', 'revision', 'display-name', 'uses-license', 'dependencies']:
                    local.appendChild(child.cloneNode(True))
            for child in list(repo.childNodes):
                if child.nodeType != child.ELEMENT_NODE or child.localName != 'license':
                    repo.removeChild(child)
            repo.appendChild(local)
            item['local_package_xml'] = document.toxml()
            metadata = ROOT / 'tools/sdk-metadata' / (path.replace(';', '-') + '.xml')
            metadata.parent.mkdir(parents=True, exist_ok=True)
            metadata.write_text(item['local_package_xml'], encoding='utf-8')
            item['metadata_file'] = str(metadata.relative_to(ROOT)).replace('\\', '/')
            items.append(item)
            break
        else:
            raise RuntimeError('No stable package: ' + path)
    (ROOT / 'android-downloads.lock.json').write_text(json.dumps({'packages': [{k:v for k,v in x.items() if k != 'local_package_xml'} for x in items]}, indent=2))
    return items

def main():
    items = resolve_packages()
    def install_package(item):
        install(item)
        (ROOT / item['destination'] / 'package.xml').write_text(item['local_package_xml'], encoding='utf-8')
        print('Registered ' + item['package'], flush=True)

    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        list(pool.map(install_package, items))

if __name__ == '__main__':
    main()
