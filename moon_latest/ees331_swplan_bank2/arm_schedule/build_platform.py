"""Build the matching FreeRTOS platform and four-PW8 scheduler using Vitis."""
from pathlib import Path
import hashlib
import os
import shutil
import subprocess
import re
import json
import vitis

# Vitis 2026.1 assumes every Windows batch startup diagnostic is UTF-8.
# A GBK diagnostic can otherwise abort client creation before the JSON port
# announcement. Adapt decoding in this process without editing the SDK.
from vitis import _server
def start_server_windows(self):
    command = str(Path(os.environ['XILINX_VITIS']) / 'bin/vitis-server.bat')
    if self.serverPort is not None:
        command += ' -p ' + str(self.serverPort)
    self.cp = subprocess.Popen(command, shell=True, start_new_session=True,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
    if self.serverPort is None:
        for raw in iter(self.cp.stdout.readline, b''):
            try:
                line = raw.decode('utf-8')
            except UnicodeDecodeError:
                line = raw.decode('gbk', errors='replace')
            print('VITIS_SERVER', line.rstrip(), flush=True)
            if 'serverPort' in line:
                self.serverPort = int(json.loads(re.search(r'\{.*?\}', line).group())['serverPort'])
                break
        if self.serverPort is None:
            raise RuntimeError('Vitis server exited before announcing a port')
    return True
_server.Server.startServer = start_server_windows

source = Path(__file__).resolve().parent
xsa = Path(os.environ['EES331_XSA']).resolve(strict=True)
work = Path(os.environ['EES331_VITIS_WORK']).resolve()
client = vitis.create_client()
try:
    client.set_workspace(work.as_posix())
    client.add_embedded_sw_repo(level='LOCAL', path='D:/vivado/2026.1/Vivado/data/embeddedsw')
    directory = work / 'ees331_platform'
    if (directory / 'vitis-comp.json').is_file():
        if not any(p.read_bytes() == xsa.read_bytes() for p in (directory / 'hw').glob('*.xsa')):
            raise RuntimeError('Platform XSA differs from this hardware build')
        platform = client.get_component('ees331_platform')
    else:
        platform = client.create_platform_component(
            name='ees331_platform', hw_design=xsa.as_posix(), cpu='ps7_cortexa9_0',
            os='freertos', domain_name='rtos_a9')
    domain = platform.get_domain('rtos_a9')
    domain.set_config('os', 'freertos_stdin', 'ps7_uart_1')
    domain.set_config('os', 'freertos_stdout', 'ps7_uart_1')
    if 'xilffs' not in {lib['name'] for lib in domain.get_libs()}:
        domain.set_lib('xilffs')
    domain.set_config('lib', 'XILTIMER_en_interval_timer', 'true', 'xiltimer')
    domain.set_config('lib', 'XILTIMER_tick_timer', 'ps7_ttc_0', 'xiltimer')
    platform.build()
    name = 'ees331_arm_schedule'
    app_dir = work / name
    if (app_dir / 'vitis-comp.json').is_file():
        app = client.get_component(name)
    else:
        app = client.create_app_component(name=name,
            platform=(work / 'ees331_platform/export/ees331_platform/ees331_platform.xpfm').as_posix(),
            domain='rtos_a9', template='empty_application')
        with (app_dir / 'src/UserConfig.cmake').open('a') as config:
            config.write('\nlist(APPEND USER_LINK_LIBRARIES freertos xiltimer xilffs)\n')
    for name in ('main.c', 'schedule.c', 'schedule.h'):
        shutil.copy2(source / name, app_dir / 'src' / name)
    app.build()
    elf = app_dir / 'build/ees331_arm_schedule.elf'
    if not elf.is_file():
        raise FileNotFoundError(elf)
    print('EES331_K1X4_FREERTOS_ELF', elf, flush=True)
finally:
    vitis.dispose()
