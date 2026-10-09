"""Transfer raw image/data bytes through image_bridge (IMIO v1, UART 8N1)."""
from __future__ import annotations

import argparse
from pathlib import Path
import struct
import zlib

MAX_PAYLOAD = 256
HEADER = struct.Struct("<4sBBHI")


def make_request(op: int, tag: int, address: int, length: int, payload: bytes = b"") -> bytes:
    if op not in (1, 2) or not 1 <= length <= MAX_PAYLOAD:
        raise ValueError("operation or length out of range")
    if not 0 <= address <= 0xFFFFFFFF or address + length > 0x100000000:
        raise ValueError("32-bit address overflow")
    if len(payload) != (length if op == 1 else 0):
        raise ValueError("incorrect payload length")
    packet = HEADER.pack(b"IMIO", op, tag, length, address) + payload
    return packet + struct.pack("<I", zlib.crc32(packet))


def read_exact(port, count: int) -> bytes:
    result = bytearray()
    while len(result) < count:
        part = port.read(count - len(result))
        if not part:
            raise TimeoutError("UART response incomplete; reset/reconnect before retrying a write")
        result.extend(part)
    return bytes(result)


def transaction(port, op: int, tag: int, address: int, length: int, payload: bytes = b"") -> bytes:
    request = make_request(op, tag, address, length, payload)
    if port.write(request) != len(request):
        raise IOError("UART short write; transaction outcome unknown")
    port.flush()
    head = read_exact(port, HEADER.size)
    magic, status, response_tag, size, response_address = HEADER.unpack(head)
    if magic != b"IMOR" or response_tag != tag or response_address != address or size > MAX_PAYLOAD:
        raise ValueError("unexpected UART response header; reset/reconnect before retrying")
    tail = read_exact(port, size + 4)
    if zlib.crc32(head + tail[:-4]) != struct.unpack("<I", tail[-4:])[0]:
        raise ValueError("UART response CRC mismatch; write outcome may be unknown")
    if status:
        errors = {1: "request CRC", 2: "command/length", 3: "SRAM range",
                  4: "SRAM access (earlier bytes may have been written)",
                  5: "SRAM timeout (reset required; earlier bytes may have been written)"}
        raise RuntimeError(f"bridge error {status}: {errors.get(status, 'unknown')}")
    if size != (length if op == 2 else 0):
        raise ValueError("incorrect response payload length")
    return tail[:-4]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", required=True, help="e.g. COM5")
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--timeout", type=float, default=3.0)
    parser.add_argument("--address", type=lambda v: int(v, 0), required=True)
    sub = parser.add_subparsers(dest="command", required=True)
    write = sub.add_parser("write")
    write.add_argument("file", type=Path)
    write.add_argument("--verify", action="store_true")
    read = sub.add_parser("read")
    read.add_argument("file", type=Path)
    read.add_argument("--length", type=lambda v: int(v, 0), required=True)
    args = parser.parse_args()
    data = args.file.read_bytes() if args.command == "write" else None
    size = len(data) if data is not None else args.length
    if size <= 0 or args.address < 0 or args.address + size > 0x100000000:
        parser.error("invalid length or 32-bit address range")
    try:
        import serial
    except ImportError:
        parser.error("pyserial is required: python -m pip install pyserial")
    result = bytearray()
    tag = 0
    with serial.Serial(args.port, args.baud, timeout=args.timeout, write_timeout=args.timeout) as port:
        port.reset_input_buffer()
        for offset in range(0, size, MAX_PAYLOAD):
            count = min(MAX_PAYLOAD, size - offset)
            address = args.address + offset
            if data is None:
                result.extend(transaction(port, 2, tag, address, count))
            else:
                part = data[offset:offset + count]
                transaction(port, 1, tag, address, count, part)
                if args.verify:
                    tag = (tag + 1) & 255
                    if transaction(port, 2, tag, address, count) != part:
                        raise RuntimeError(f"readback mismatch at 0x{address:08x}")
            tag = (tag + 1) & 255
    if data is None:
        args.file.write_bytes(result)
    print(f"{args.command}: {size} bytes at 0x{args.address:08x} complete")


if __name__ == "__main__":
    main()
