"""Build a FreeRTOS inference application against the existing EES331 XSA."""

from pathlib import Path
import os
import shutil

import vitis


src = Path(__file__).resolve().parent
work = Path(os.environ.get("EES331_VITIS_WORK", str(src.parent / "sw"))).resolve()
platform = work / "ees331_platform/export/ees331_platform/ees331_platform.xpfm"
name = "ees331_arm_schedule"
app_dir = work / name
client = vitis.create_client()
try:
    client.set_workspace(work.as_posix())
    if (app_dir / "vitis-comp.json").is_file():
        app = client.get_component(name)
    else:
        app = client.create_app_component(
            name=name, platform=platform.as_posix(), domain="rtos_a9", template="empty_application",
        )
        with (app_dir / "src/UserConfig.cmake").open("a", encoding="utf-8") as config:
            config.write("\nlist(APPEND USER_LINK_LIBRARIES freertos xiltimer xilffs)\n")
    for filename in ("main.c", "schedule.c", "schedule.h", "k3_plan.h"):
        shutil.copy2(src / filename, app_dir / "src" / filename)
    app.build()
    elf = app_dir / "build" / f"{name}.elf"
    if not elf.is_file():
        raise FileNotFoundError(elf)
    print(f"EES331_SCHEDULE_ELF {elf}", flush=True)
finally:
    vitis.dispose()
