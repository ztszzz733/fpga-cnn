"""Host protocol tests without pyserial or a physical board."""
import struct
import sys
import unittest
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from uart_image_transfer import HEADER, make_request, transaction


class Port:
    def __init__(self, data):
        self.data = data
        self.sent = b""

    def write(self, data):
        self.sent += data
        return len(data)

    def flush(self):
        pass

    def read(self, count):
        part, self.data = self.data[:min(count, 3)], self.data[min(count, 3):]
        return part


def reply(status=0, tag=7, address=65, payload=b"abc"):
    body = HEADER.pack(b"IMOR", status, tag, len(payload), address) + payload
    return body + struct.pack("<I", zlib.crc32(body))


class ProtocolTests(unittest.TestCase):
    def test_write_crc(self):
        packet = make_request(1, 7, 65, 3, b"abc")
        self.assertEqual(packet[:12], b"IMIO\x01\x07\x03\x00A\x00\x00\x00")
        self.assertEqual(struct.unpack("<I", packet[-4:])[0], zlib.crc32(packet[:-4]))

    def test_read_fragmented(self):
        self.assertEqual(transaction(Port(reply()), 2, 7, 65, 3), b"abc")

    def test_write_ack(self):
        self.assertEqual(transaction(Port(reply(payload=b"")), 1, 7, 65, 3, b"abc"), b"")

    def test_bad_crc(self):
        bad = bytearray(reply()); bad[-1] ^= 1
        with self.assertRaises(ValueError):
            transaction(Port(bytes(bad)), 2, 7, 65, 3)

    def test_error(self):
        with self.assertRaises(RuntimeError):
            transaction(Port(reply(status=4, payload=b"")), 2, 7, 65, 3)

    def test_timeout(self):
        with self.assertRaises(TimeoutError):
            transaction(Port(b""), 2, 7, 65, 3)

    def test_invalid(self):
        for args in [(1, 0, 0, 0), (2, 0, 0, 257), (2, 0, 0xffffffff, 2), (1, 0, 0, 1)]:
            with self.assertRaises(ValueError):
                make_request(*args)


if __name__ == "__main__":
    unittest.main()
