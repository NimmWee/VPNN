import copy
import unittest
import node_sync

def state():
    return {'version':5,'groups':[{'id':'g','profiles':{'vk':{},'dns':{}}}], 'devices':{
        'device-a':{'id':'device-a','group':'g','enabled':True,'uuid':'11111111-1111-4111-8111-111111111111','dnsKey':'a'*32,'dnsPort':54001},
        'device-b':{'id':'device-b','group':'g','enabled':True,'uuid':'22222222-2222-4222-8222-222222222222','dnsKey':'b'*32,'dnsPort':54002}}}

class DesiredStateTest(unittest.TestCase):
    def test_individual_keys_and_disabled_device_removal(self):
        source=state()
        wanted=node_sync.desired(source,'v.example.org')
        self.assertEqual(len(wanted['dns']),2)
        self.assertEqual(len(wanted['vk']),2)
        self.assertNotEqual(wanted['dns'][0]['key'],wanted['dns'][1]['key'])
        source['devices']['device-b']['enabled']=False
        wanted=node_sync.desired(source,'v.example.org')
        self.assertEqual([item['id'] for item in wanted['vk']],['device-a'])
        self.assertEqual(len(wanted['dns']),1)

    def test_unsafe_values_and_duplicate_ports_are_rejected(self):
        for field,value in [('id','../../etc/shadow'),('uuid','not-a-uuid'),('dnsPort',53),('dnsKey','short')]:
            source=state()
            source['devices']['device-a'][field]=value
            with self.assertRaises(ValueError):
                node_sync.desired(source,'v.example.org')
        source=state()
        source['devices']['device-b']['dnsPort']=54001
        with self.assertRaises(ValueError):
            node_sync.desired(source,'v.example.org')

    def test_profile_assignment_limits_network_access(self):
        source=state()
        source['groups'][0]['profiles']={'dns':{}}
        wanted=node_sync.desired(source,'v.example.org')
        self.assertFalse(wanted['vk'])
        self.assertEqual(len(wanted['dns']),2)

if __name__=='__main__':
    unittest.main()
