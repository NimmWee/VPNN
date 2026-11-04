"""Inspect/onboard only our isolated Android release package; redact invitation text."""
import argparse
from pathlib import Path
import re
import subprocess
import time
import xml.etree.ElementTree as ET

root=Path(__file__).resolve().parents[1]
adb=str(root/'.toolchains/android-sdk/platform-tools/adb.exe')
base=[adb,'-s','emulator-5554','shell']
parser=argparse.ArgumentParser()
parser.add_argument('action',choices=['inspect','agree','statement','enroll','dns','vk','connect','disconnect','allow-vpn','bootstrap','fallback','scroll-down','scroll-up'])
args=parser.parse_args()

def command(*values):
    for attempt in range(3):
        result=subprocess.run(base+list(values),capture_output=True,text=True,timeout=25)
        if result.returncode==0: return result.stdout
        if values[0]!='uiautomator' or attempt==2: result.check_returncode()
        time.sleep(1)

def observe():
    command('uiautomator','dump','/sdcard/vpnn-release-ui.xml')
    text=command('cat','/sdcard/vpnn-release-ui.xml')
    if 'package="space.chichy.vpnn"' not in text and not(args.action=='allow-vpn' and 'package="com.android.vpndialogs"' in text and 'VPNN' in text):
        raise RuntimeError('unexpected foreground application')
    return ET.fromstring(text)

def tap(node):
    bounds=[int(value) for value in re.findall(r'\d+',node.get('bounds',''))]
    if len(bounds)!=4: raise RuntimeError('missing bounds')
    command('input','tap',str((bounds[0]+bounds[2])//2),str((bounds[1]+bounds[3])//2))

tree=observe()
if args.action in ['scroll-down','scroll-up']:
    scroll=next((node for node in tree.iter('node') if node.get('scrollable')=='true'),None)
    if scroll is not None:
        x1,y1,x2,y2=[int(value) for value in re.findall(r'\d+',scroll.get('bounds'))]
        top=y1+(y2-y1)//3
        bottom=y1+2*(y2-y1)//3
        start,end=(bottom,top) if args.action=='scroll-down' else (top,bottom)
        command('input','swipe',str((x1+x2)//2),str(start),str((x1+x2)//2),str(end),'400')
        tree=observe()
elif args.action in ['agree','bootstrap','fallback']:
    labels={'agree':'Agree','bootstrap':'Import connection file','fallback':'Try backup modes automatically'}
    candidates=[node for node in tree.iter('node') if (node.get('content-desc') or node.get('text') or '').split('\n')[0]==labels[args.action] and node.get('enabled')=='true']
    if len(candidates)!=1: raise RuntimeError('requested test control is not uniquely visible')
    tap(candidates[0])
    if args.action=='bootstrap':
        print('Bootstrap file picker requested; inspect its next state separately')
        raise SystemExit(0)
    tree=observe()
elif args.action=='statement':
    statement=next(node.get('text') for node in tree.iter('node') if node.get('text','').startswith('The Software itself'))
    if "'" in statement: raise RuntimeError('unexpected quoting')
    field=next(node for node in tree.iter('node') if node.get('class')=='android.widget.EditText')
    tap(field)
    command('input','text',"'"+statement.replace(' ','%s')+"'")
    command('input','keyevent','4')
    tree=observe()
    button=next(node for node in tree.iter('node') if node.get('content-desc')=='Confirm' and node.get('enabled')=='true')
    tap(button)
    tree=observe()
elif args.action=='enroll':
    fields=[node for node in tree.iter('node') if node.get('class')=='android.widget.EditText']
    if len(fields)!=1: raise RuntimeError('invitation field is not uniquely visible')
    invitation=(root/'private/transport-test/emulator-production-invitation.txt').read_text().strip()
    if "'" in invitation: raise RuntimeError('unexpected invitation quoting')
    tap(fields[0])
    command('input','text',"'"+invitation+"'")
    command('input','keyevent','4')
    tree=observe()
    button=next(node for node in tree.iter('node') if node.get('content-desc')=='Add device' and node.get('enabled')=='true')
    tap(button)
    tree=observe()
elif args.action in ['dns','vk','connect','disconnect','allow-vpn']:
    labels={'dns':'Via DNS','vk':'Via VK','connect':'Connect','disconnect':'Disconnect'}
    if args.action=='allow-vpn':
        candidates=[node for node in tree.iter('node') if node.get('resource-id')=='android:id/button1' and node.get('text')=='OK']
    else:
        label=labels[args.action]
        candidates=[node for node in tree.iter('node') if (node.get('content-desc') or '').split('\n')[0]==label and node.get('enabled')=='true']
    if len(candidates)!=1: raise RuntimeError('requested test control is not uniquely visible')
    tap(candidates[0])
    if args.action=='connect':
        print('Connect requested in isolated emulator; inspect VPN permission next')
        raise SystemExit(0)
    tree=observe()
for node in tree.iter('node'):
    text=node.get('content-desc') or node.get('text')
    if text:
        if 'vpnn://' in text or 'token=' in text: text='[private invitation hidden]'
        print(node.get('class','')+' '+text[:180]+' '+node.get('bounds',''))
