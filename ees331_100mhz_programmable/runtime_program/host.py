"""Send user images, tasks and DDR data to EES331 over the PS UART."""

import argparse
from pathlib import Path
import struct
import zlib

TASK_ARGS = 14
MAX_TRANSFER = 16384
DDR_LIMIT = 0x01000000
STATES = {1: "QUEUED", 2: "RUNNING", 3: "DONE", 4: "CANCELLED", 5: "FAILED"}

def integer(text):
    return int(text, 0)

def words(*items):
    return struct.pack("<" + "I" * len(items), *(item & 0xffffffff for item in items))

def read_exact(port, count):
    data = port.read(count)
    if len(data) != count:
        raise TimeoutError(f"UART replied with {len(data)} of {count} bytes")
    return data

def receive(port, count):
    return struct.unpack("<" + "I" * count, read_exact(port, count * 4))

def upload_image(path):
    image = path.read_bytes()
    if len(image) < 16:
        raise ValueError("Truncated program image")
    magic, text, data, crc = struct.unpack_from("<4I", image)
    if (magic != 0x31505652 or not 0 < text <= 8192 or data > 8192 or
            (text | data) & 3 or len(image) != 16 + text + data or
            zlib.crc32(image[16:]) != crc):
        raise ValueError("Invalid RV32 program image")
    return image

def upload_range(address, size):
    if not 0 <= address < DDR_LIMIT or not 0 < size <= min(MAX_TRANSFER, DDR_LIMIT - address):
        raise ValueError("Expected 1–16384 bytes within the 16 MiB application DDR window")
    return words(address, size)

def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("port", help="For example COM6")
    sub = cli.add_subparsers(dest="command", required=True)
    load = sub.add_parser("load")
    load.add_argument("image", type=Path)
    load.add_argument("--policy", choices=("drain", "cancel"), default="drain")
    submit = sub.add_parser("submit")
    submit.add_argument("id", type=integer)
    submit.add_argument("values", nargs="*", type=integer)
    result = sub.add_parser("result")
    result.add_argument("epoch", type=integer)
    result.add_argument("id", type=integer)
    sub.add_parser("status")
    write = sub.add_parser("write-ddr")
    write.add_argument("address", type=integer)
    write.add_argument("source", type=Path)
    read = sub.add_parser("read-ddr")
    read.add_argument("address", type=integer)
    read.add_argument("size", type=integer)
    read.add_argument("output", type=Path)
    args = cli.parse_args()

    import serial

    with serial.Serial(args.port, 115200, timeout=45, write_timeout=20) as port:
        if args.command == "load":
            image = upload_image(args.image)
            port.write(b"L" + words(1 if args.policy == "drain" else 2) + image)
            status, epoch = receive(port, 2)
            if status:
                raise RuntimeError(f"Board rejected load (status {status}, epoch {epoch})")
            print(f"Program ready, epoch {epoch}")
        elif args.command == "submit":
            if len(args.values) > TASK_ARGS:
                cli.error(f"At most {TASK_ARGS} task arguments are supported")
            values = args.values + [0] * (TASK_ARGS - len(args.values))
            port.write(b"T" + words(args.id, *values))
            status, epoch, task = receive(port, 3)
            if status:
                raise RuntimeError(f"Task rejected (status {status})")
            print(f"Task accepted, epoch {epoch}, ID {task}")
        elif args.command == "result":
            port.write(b"R" + words(args.epoch, args.id))
            status, = receive(port, 1)
            if status:
                raise RuntimeError(f"Task not found or request rejected (status {status})")
            state, reason, *data = receive(port, 6)
            signed = [value if value < 0x80000000 else value - 0x100000000 for value in data]
            print(f"{STATES.get(state, state)} ({reason}), result {signed}")
        elif args.command == "status":
            port.write(b"S")
            status, control, epoch, ready = receive(port, 4)
            if status:
                raise RuntimeError(f"Status request rejected ({status})")
            print(f"epoch={epoch} control=0x{control:08x} ready=0x{ready:08x}")
        elif args.command == "write-ddr":
            data = args.source.read_bytes()
            port.write(b"W" + upload_range(args.address, len(data)) + data)
            status, = receive(port, 1)
            if status:
                raise RuntimeError(f"DDR write rejected ({status})")
            print(f"Wrote {len(data)} bytes")
        elif args.command == "read-ddr":
            port.write(b"M" + upload_range(args.address, args.size))
            status, = receive(port, 1)
            if status:
                raise RuntimeError(f"DDR read rejected ({status})")
            args.output.write_bytes(read_exact(port, args.size))
            print(f"Saved {args.size} bytes to {args.output}")

if __name__ == "__main__":
    main()
