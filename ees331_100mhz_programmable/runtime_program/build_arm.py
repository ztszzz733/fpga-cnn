"""Vitis CLI entry to build the Cortex-A9 UART service for a matching XSA."""

import json
import os
from pathlib import Path
import re
import shutil
import subprocess

import vitis

HERE = Path(__file__).resolve().parent
XSA = Path(os.environ["EES331_XSA"]).resolve(strict=True)
WORK = Path(os.environ["EES331_VITIS_WORK"]).resolve()

def start_server_windows(server):
    # Vitis can print Windows startup diagnostics using the local code page.
    command = Path(os.environ["XILINX_VITIS"]) / "bin/vitis-server.bat"
    arguments = [str(command)]
    if server.serverPort is not None:
        arguments.extend(["-p", str(server.serverPort)])
    server.cp = subprocess.Popen(arguments, stdout=subprocess.PIPE,
                                 stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
    if server.serverPort is None:
        for line in iter(server.cp.stdout.readline, b""):
            message = line.decode("utf-8", errors="replace")
            print(message.rstrip(), flush=True)
            if "serverPort" in message:
                server.serverPort = int(json.loads(re.search(r"\{.*\}", message).group())["serverPort"])
                break
        if server.serverPort is None:
            raise RuntimeError("Vitis server exited before announcing its port")
    return True

if os.name == "nt":
    from vitis import _server
    _server.Server.startServer = start_server_windows

client = vitis.create_client()
try:
    client.set_workspace(WORK.as_posix())
    if embedded_sw := os.environ.get("EES331_EMBEDDED_SW"):
        repo = Path(embedded_sw).resolve(strict=True)
        client.add_embedded_sw_repo(level="LOCAL", path=repo.as_posix())
    platform_name = "ees331_runtime_platform"
    app_name = "ees331_uart_loader"
    platform_dir = WORK / platform_name
    if (platform_dir / "vitis-comp.json").is_file():
        if not any(p.read_bytes() == XSA.read_bytes() for p in (platform_dir / "hw").glob("*.xsa")):
            raise RuntimeError("The existing platform is for another XSA")
        platform = client.get_component(platform_name)
    else:
        platform = client.create_platform_component(
            name=platform_name, hw_design=XSA.as_posix(), cpu="ps7_cortexa9_0",
            os="standalone", domain_name="arm_loader")
    platform.build()
    app_dir = WORK / app_name
    if (app_dir / "vitis-comp.json").is_file():
        app = client.get_component(app_name)
    else:
        xpfm = platform_dir / "export" / platform_name / f"{platform_name}.xpfm"
        app = client.create_app_component(name=app_name, platform=xpfm.as_posix(),
                                          domain="arm_loader", template="empty_application")
    shutil.copy2(HERE / "arm_main.c", app_dir / "src/main.c")
    shutil.copy2(HERE / "protocol.h", app_dir / "src/protocol.h")
    app.build()
    elf = app_dir / "build" / (app_name + ".elf")
    if not elf.is_file():
        raise FileNotFoundError(elf)
    print(elf)
finally:
    vitis.dispose()
