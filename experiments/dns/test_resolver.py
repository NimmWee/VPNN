import socket
import time
import unittest

from resolver import FakeResolver, Profile


def query(number):
    return number.to_bytes(2, "big") + b"\x01\x00\x00\x01" + bytes(6) + b"\x01x\x00\x00\x10\x00\x01"


class ResolverTest(unittest.TestCase):
    def test_delays_drops_reorders_and_restores_ids(self):
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as upstream, socket.socket(
            socket.AF_INET, socket.SOCK_DGRAM
        ) as client:
            upstream.bind(("127.0.0.1", 0))
            upstream.settimeout(2)
            client.settimeout(2)
            profile = Profile(delay=.02, drop_every=4, hold_every=2, hold=.15)
            with FakeResolver(upstream.getsockname()[1], profile) as resolver:
                for number in range(1, 6):
                    client.sendto(query(number), resolver.address)
                for _ in range(4):
                    packet, sender = upstream.recvfrom(512)
                    upstream.sendto(packet[:2] + b"\x81" + packet[3:], sender)
                received = [int.from_bytes(client.recv(512)[:2], "big") for _ in range(3)]
                self.assertEqual(received, [1, 5, 3])
                deadline = time.monotonic() + 1
                counters, samples = resolver.snapshot()
                while counters["replies_delivered"] < 3 and time.monotonic() < deadline:
                    time.sleep(.001)
                    counters, samples = resolver.snapshot()
                self.assertEqual(counters["replies_delivered"], 3)
                self.assertEqual(counters["query_drop"], 1)
                self.assertEqual(counters["reply_drop"], 1)
                self.assertEqual(counters["reordered_replies"], 1)
                self.assertEqual(counters["question_repeat"], 4)
                self.assertGreaterEqual(min(samples), .04)

    def test_qps_cap(self):
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as upstream, socket.socket(
            socket.AF_INET, socket.SOCK_DGRAM
        ) as client:
            upstream.bind(("127.0.0.1", 0))
            upstream.settimeout(2)
            with FakeResolver(upstream.getsockname()[1], Profile(qps=1)) as resolver:
                client.sendto(query(1), resolver.address)
                client.sendto(query(2), resolver.address)
                upstream.recvfrom(512)
                upstream.settimeout(.1)
                with self.assertRaises(socket.timeout):
                    upstream.recvfrom(512)
                self.assertEqual(resolver.snapshot()[0]["rate_drop"], 1)


if __name__ == "__main__":
    unittest.main()
