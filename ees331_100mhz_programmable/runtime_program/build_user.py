"""Compile an RV32I C task and pack its code and initialized data."""

import argparse
import os
from pathlib import Path
import struct
import subprocess
import zlib

HERE = Path(__file__).resolve().parent
DEFAULT_GCC = Path("D:/vivado/2026.1/Vitis/gnu/riscv/nt/bin/riscv64-unknown-elf-gcc.exe")

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("c_source", type=Path)
    parser.add_argument("image", type=Path)
    parser.add_argument("--gcc", type=Path, default=DEFAULT_GCC)
    args = parser.parse_args()
    source = args.c_source.resolve(strict=True)
    out = args.image.resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    gcc = args.gcc.resolve(strict=True)
    tool_root = gcc.parent.parent
    env = dict(os.environ)
    library_dirs = [gcc.parent, tool_root / "x86_64-w64-mingw32/lib",
                    tool_root / "x86_64-w64-mingw32/bin"]
    if os.name == "nt":
        install_root = DEFAULT_GCC.parents[5]
        library_dirs.append(install_root / "Vitis/tps/win64")
    env["PATH"] = os.pathsep.join([*map(str, library_dirs), env["PATH"]])
    objcopy = gcc.with_name(gcc.name.replace("gcc", "objcopy"))
    elf = out.with_suffix(".elf")
    flags = ["-march=rv32i", "-mabi=ilp32", "-mno-relax", "-msmall-data-limit=0",
             "-Os", "-ffreestanding", "-fno-builtin", "-fno-stack-protector",
             "-ffunction-sections", "-fdata-sections", "-Wall", "-Wextra", "-Werror"]
    subprocess.run([str(gcc), *flags, "-nostdlib", "-I", str(HERE),
                    "-I", str(HERE.parent / "simple_cnn_bank256_page_write/software"),
                    "-T", str(HERE / "rv32.ld"),
                    "-Wl,--gc-sections,--no-relax", str(HERE / "rv32_start.S"),
                    str(HERE / "rv32_runtime.c"), str(source), "-lgcc", "-o", str(elf)],
                   env=env, check=True)
    sections = []
    for section in ("text", "data"):
        binary = out.with_suffix("." + section + ".bin")
        subprocess.run([str(objcopy), "-O", "binary", "-j", "." + section,
                        str(elf), str(binary)], env=env, check=True)
        sections.append(binary.read_bytes())
    text, data = sections
    if not text or len(text) > 8192 or len(data) > 8192 or (len(text) | len(data)) & 3:
        raise ValueError("RV32 image exceeds or misaligns IMEM/DMEM")
    payload = text + data
    out.write_bytes(struct.pack("<4I", 0x31505652, len(text), len(data), zlib.crc32(payload)) + payload)
    print(f"{out}: {len(text)} code bytes, {len(data)} initialized data bytes")

if __name__ == "__main__":
    main()
