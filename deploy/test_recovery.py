import io
from pathlib import Path
import tarfile
import tempfile
import unittest
from cryptography.exceptions import InvalidTag
import recovery

class RecoveryTest(unittest.TestCase):
    def test_wrong_key_and_tampering_are_rejected(self):
        sealed=recovery.seal(b'private state',bytes(32))
        with self.assertRaises(InvalidTag):
            recovery.open_snapshot(sealed,b'1'*32)
        changed=sealed[:-1]+bytes([sealed[-1]^1])
        with self.assertRaises(InvalidTag):
            recovery.open_snapshot(changed,bytes(32))
        self.assertEqual(recovery.open_snapshot(sealed,bytes(32)),b'private state')

    def test_archive_traversal_is_rejected_before_writing(self):
        data=io.BytesIO()
        with tarfile.open(fileobj=data,mode='w:gz') as archive:
            member=tarfile.TarInfo('../escape')
            member.size=1
            archive.addfile(member,io.BytesIO(b'x'))
        with tempfile.TemporaryDirectory() as directory:
            target=Path(directory)/'staged'
            with self.assertRaises(ValueError):
                recovery.unpack(data.getvalue(),target)
            self.assertFalse(target.exists())

    def test_valid_snapshot_is_staged_without_overwriting(self):
        data=io.BytesIO()
        with tarfile.open(fileobj=data,mode='w:gz') as archive:
            member=tarfile.TarInfo('etc/vpnn-control/admin.secret')
            member.size=3
            archive.addfile(member,io.BytesIO(b'key'))
        with tempfile.TemporaryDirectory() as directory:
            target=Path(directory)/'staged'
            recovery.unpack(data.getvalue(),target)
            self.assertEqual((target/'etc/vpnn-control/admin.secret').read_bytes(),b'key')
            with self.assertRaises(ValueError):
                recovery.unpack(data.getvalue(),target)

if __name__=='__main__':
    unittest.main()
