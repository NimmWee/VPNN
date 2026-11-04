import unittest
import install

class RenderTest(unittest.TestCase):
    def test_stream_keeps_existing_routes_and_is_repeatable(self):
        original='stream {\n map $ssl_preread_server_name $kit_upstream {\n example.org 127.0.0.1:10443;\n default 127.0.0.1:10446;\n }\n}\n'
        updated=install.add_stream_include(original)
        self.assertIn('example.org 127.0.0.1:10443;',updated)
        self.assertEqual(install.add_stream_include(updated),updated)
        self.assertEqual(updated.count('include /etc/nginx/vpnn-stream-map.conf;'),1)

    def test_unknown_nginx_layout_is_refused(self):
        with self.assertRaises(ValueError):
            install.add_stream_include('stream { server { listen 443; } }')

    def test_hostname_cannot_inject_nginx_directives(self):
        for domain in ['example.org;include /tmp/x;', 'https://example.org', '*.example.org', 'localhost']:
            with self.assertRaises(ValueError):
                install.validate_domain(domain)
        install.validate_domain('vpn.chichy.space')

if __name__=='__main__':
    unittest.main()
