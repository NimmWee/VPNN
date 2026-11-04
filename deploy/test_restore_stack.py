import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import restore_stack
from test_node_sync import state

class RestorePlanTest(unittest.TestCase):
    def fixture(self,root):
        snapshot=root/'snapshot'
        bundle=root/'bundle'
        bundle.mkdir()
        def write(name,data):
            path=snapshot/name
            path.parent.mkdir(parents=True,exist_ok=True)
            path.write_bytes(data)
        write('var/lib/vpnn-control/state.json',json.dumps(state()).encode())
        write('var/lib/vpnn-control/state.json.signing',b'x'*32)
        write('etc/vpnn-control/admin.secret',b'a'*32)
        write('etc/vpnn-transports/xray.json',b'{}')
        write('etc/vpnn-transports/clients.json',b'{}')
        write('etc/vpnn-transports/freeturn.env',b'VPNN_OBF_KEY='+b'a'*32)
        for name in restore_stack.UNITS:
            write(f'etc/systemd/system/{name}.service',b'[Service]\nExecStart=/opt/vpnn-control/test -listen 89.125.120.163:53\n')
        for name in ['fullchain.pem','privkey.pem']:
            write('etc/letsencrypt/live/vpn.chichy.space/'+name,b'certificate')
        manifest={}
        for name in [*restore_stack.BINARIES,'node_sync.py']:
            (bundle/name).write_bytes(name.encode())
            manifest[name]=hashlib.sha256(name.encode()).hexdigest()
        (bundle/'sha256.json').write_text(json.dumps(manifest))
        return snapshot,bundle

    def test_dry_plan_preserves_individual_access_and_updates_address(self):
        with tempfile.TemporaryDirectory() as directory:
            snapshot,bundle=self.fixture(Path(directory))
            with patch.object(restore_stack,'run',side_effect=AssertionError('dry plan mutated system')):
                wanted=restore_stack.plan(snapshot,bundle,'89.125.120.164','vpn.chichy.space')
            self.assertEqual(wanted['dnsDevices'],2)
            self.assertEqual(wanted['state']['devices'],state()['devices'])
            self.assertGreater(wanted['state']['version'],state()['version'])
            self.assertIn('89.125.120.164:53',wanted['units']['vpnn-dns'])

    def test_bundle_tampering_and_private_addresses_fail(self):
        with tempfile.TemporaryDirectory() as directory:
            snapshot,bundle=self.fixture(Path(directory))
            for address in ['127.0.0.1','10.0.0.1','invalid']:
                with self.assertRaises(ValueError): restore_stack.plan(snapshot,bundle,address,'vpn.chichy.space')
            (bundle/'vpnn-control').write_bytes(b'tampered')
            with self.assertRaises(ValueError): restore_stack.plan(snapshot,bundle,'89.125.120.163','vpn.chichy.space')

    def test_readdress_does_not_change_embedded_secrets_or_domain(self):
        previous='89.125.120.163'
        value={'server':previous,'peer':previous+':56010','secret':'abc'+previous+'xyz','domain':'v.chichy.space'}
        self.assertEqual(restore_stack.readdress(value,previous,'89.125.120.164'),
                         {**value,'server':'89.125.120.164','peer':'89.125.120.164:56010'})

if __name__=='__main__': unittest.main()
