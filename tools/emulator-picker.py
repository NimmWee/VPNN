"""Select only the administrator bootstrap in the emulator's Android file picker."""
import argparse
import re
from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET
parser=argparse.ArgumentParser()
parser.add_argument('action', choices=['inspect','roots','downloads','file'])
args=parser.parse_args()
root=Path(__file__).resolve().parents[1]
base=[str(root/'.toolchains/android-sdk/platform-tools/adb.exe'),'-s','emulator-5554','shell']
def command(*values):
    return subprocess.run(base+list(values),capture_output=True,text=True,timeout=20,check=True).stdout
command('uiautomator','dump','/sdcard/vpnn-picker.xml')
tree=ET.fromstring(command('cat','/sdcard/vpnn-picker.xml'))
if not any(node.get('package')=='com.android.documentsui' for node in tree.iter('node')):
    raise RuntimeError('the expected Android file picker is not in front')
if args.action!='inspect':
    text={'roots':'Show roots','downloads':'Downloads','file':'VPNN-bootstrap.json'}[args.action]
    candidates=[n for n in tree.iter('node') if n.get('text')==text or n.get('content-desc')==text]
    if args.action=='downloads': candidates=[n for n in candidates if n.get('resource-id')=='android:id/title']
    if len(candidates)!=1: raise RuntimeError('the requested picker control is not uniquely visible')
    x1,y1,x2,y2=map(int,re.findall(r'\d+',candidates[0].get('bounds')))
    command('input','tap',str((x1+x2)//2),str((y1+y2)//2))
    print('Observed picker control selected: '+args.action)
else:
    for node in tree.iter('node'):
        if node.get('text') or node.get('content-desc'):
            print(node.get('text') or node.get('content-desc'))
