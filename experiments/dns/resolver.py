"""Loopback UDP forwarder with independently scheduled query and reply legs."""
import heapq
import itertools
import select
import socket
import threading
import time
from collections import Counter, deque
from dataclasses import dataclass

HOST = "127.0.0.1"


@dataclass(frozen=True)
class Profile:
    delay: float = 0
    drop_every: int = 0
    hold_every: int = 0
    hold: float = 0
    qps: int = 1500

    def drop(self, ordinal):
        return self.drop_every and ordinal % self.drop_every == 0

    def latency(self, ordinal):
        return self.delay + (self.hold if self.hold_every and ordinal % self.hold_every == 0 else 0)


class FakeResolver:
    def __init__(self, upstream_port, profile):
        if upstream_port <= 1024:
            raise ValueError("lab requires a high UDP port")
        self.profile = profile
        self.down = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.down.bind((HOST, 0))
        self.up = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.up.connect((HOST, upstream_port))
        self.address = self.down.getsockname()
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.lock = threading.Lock()
        self.counts = Counter()
        self.rtt = []
        self.questions = set()
        self.pending = {}
        self.rate = deque()
        self.events = []
        self.sequence = itertools.count()
        self.txids = itertools.cycle(range(65536))
        self.latest_reply = 0
        self.error = None

    def __enter__(self):
        self.thread.start()
        return self

    def quiesce(self):
        self.stop.set()
        self.thread.join()

    def __exit__(self, *args):
        self.quiesce()
        self.up.close()
        self.down.close()
        if self.error and args[0] is None:
            raise self.error

    def snapshot(self):
        with self.lock:
            return self.counts.copy(), self.rtt.copy()

    def schedule(self, when, sock, packet, address, ordinal=0, arrival=0):
        heapq.heappush(self.events, (when, next(self.sequence), sock, packet, address, ordinal, arrival))

    def run(self):
        try:
            while not self.stop.is_set():
                now = time.perf_counter()
                while self.events and self.events[0][0] <= now:
                    _, _, sock, packet, address, ordinal, arrival = heapq.heappop(self.events)
                    if address is None:
                        sock.send(packet)
                    else:
                        sock.sendto(packet, address)
                        with self.lock:
                            self.counts["replies_delivered"] += 1
                            self.counts["reordered_replies"] += ordinal < self.latest_reply
                            self.latest_reply = max(self.latest_reply, ordinal)
                            self.rtt.append(time.perf_counter() - arrival)
                timeout = min(.01, max(0, self.events[0][0] - now)) if self.events else .01
                for sock in select.select([self.down, self.up], [], [], timeout)[0]:
                    packet, address = sock.recvfrom(65535)
                    if len(packet) >= 12:
                        with self.lock:
                            if sock is self.down:
                                self.query(packet, address, time.perf_counter())
                            else:
                                self.reply(packet, time.perf_counter())
        except Exception as error:
            self.error = error

    def query(self, packet, address, now):
        self.counts["queries"] += 1
        ordinal = self.counts["queries"]
        # Tunnel questions are uncompressed and contain one QNAME. Ignore ID and EDNS.
        end = packet.find(b"\0", 12)
        if end >= 12 and end + 5 <= len(packet):
            question = packet[12:end + 5].lower()
            self.counts["question_repeat"] += question in self.questions
            self.questions.add(question)
        while self.rate and self.rate[0] <= now - 1:
            self.rate.popleft()
        if len(self.rate) >= self.profile.qps:
            self.counts["rate_drop"] += 1
            return
        self.rate.append(now)
        if self.profile.drop(ordinal):
            self.counts["query_drop"] += 1
            return
        # A connected upstream socket filters foreign replies. Map transaction IDs
        # across client worker sockets and restore the original on the way back.
        token = next(self.txids)
        while token in self.pending and now - self.pending[token][2] < 15:
            token = next(self.txids)
        self.pending[token] = (packet[:2], address, now, ordinal)
        self.schedule(now + self.profile.latency(ordinal), self.up,
                      token.to_bytes(2, "big") + packet[2:], None)

    def reply(self, packet, now):
        request = self.pending.pop(int.from_bytes(packet[:2], "big"), None)
        if request is None:
            self.counts["unmatched_reply"] += 1
            return
        original, address, arrival, ordinal = request
        self.counts["upstream_replies"] += 1
        response_number = self.counts["upstream_replies"]
        if self.profile.drop(response_number):
            self.counts["reply_drop"] += 1
            return
        self.schedule(now + self.profile.latency(response_number), self.down,
                      original + packet[2:], address, ordinal, arrival)
