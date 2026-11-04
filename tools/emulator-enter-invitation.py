import pathlib
import subprocess

root=pathlib.Path(__file__).resolve().parents[1]
adb=str(root/'.toolchains'/'android-sdk'/'platform-tools'/'adb.exe')
invitation=(root/'private'/'transport-test'/'emulator-invitation.txt').read_text().strip()
if "'" in invitation:
    raise SystemExit('invalid invitation quoting')
subprocess.run([adb,'-s','emulator-5554','shell','input','tap','500','1770'],check=True)
subprocess.run([adb,'-s','emulator-5554','shell','input','text',"'"+invitation+"'"],check=True)
subprocess.run([adb,'-s','emulator-5554','shell','input','keyevent','4'],check=True)
print('Invitation entered into emulator; credential not printed.')
