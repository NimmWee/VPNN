"""Authenticated encryption and safe staging of a private VPNN recovery snapshot."""
import argparse
import io
import os
from pathlib import Path,PurePosixPath
import tarfile
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

MAGIC=b'VPNN-RECOVERY-1\n'
LIMIT=64*1024*1024

def seal(data,key):
    nonce=os.urandom(12)
    return MAGIC+nonce+AESGCM(key).encrypt(nonce,data,MAGIC)

def open_snapshot(data,key):
    if not data.startswith(MAGIC) or len(data)>LIMIT:
        raise ValueError('invalid or oversized recovery file')
    nonce=data[len(MAGIC):len(MAGIC)+12]
    return AESGCM(key).decrypt(nonce,data[len(MAGIC)+12:],MAGIC)

def unpack(data,destination):
    destination=Path(destination).resolve()
    if destination.exists():
        raise ValueError('restore staging directory must not exist')
    with tarfile.open(fileobj=io.BytesIO(data),mode='r:gz') as archive:
        members=archive.getmembers()
        total=0
        names=set()
        for member in members:
            name=PurePosixPath(member.name)
            if name.is_absolute() or '..' in name.parts or not name.parts or not(member.isfile() or member.isdir()):
                raise ValueError('unsafe recovery archive member')
            if name in names:
                raise ValueError('duplicate recovery archive member')
            names.add(name)
            total+=member.size
            if total>LIMIT:
                raise ValueError('recovery contents are too large')
        destination.mkdir(parents=True,mode=0o700)
        for member in members:
            path=destination.joinpath(*PurePosixPath(member.name).parts)
            if member.isdir():
                path.mkdir(parents=True,exist_ok=True,mode=0o700)
            else:
                path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
                with archive.extractfile(member) as source,path.open('xb') as target:
                    target.write(source.read())
                path.chmod(0o600)

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--backup',required=True)
    parser.add_argument('--key-file',required=True)
    parser.add_argument('--destination',required=True)
    args=parser.parse_args()
    key=Path(args.key_file).read_bytes()
    unpack(open_snapshot(Path(args.backup).read_bytes(),key),args.destination)
    print('Recovery snapshot authenticated and staged; no system files or services were changed')
