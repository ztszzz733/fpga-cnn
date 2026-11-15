"""Compile and simulate the isolated partner Datapath B1 memory additions."""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from pathlib import Path

from run_tests import ROOT, execute, tool_env, tools


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    delivery = ROOT / "partners/datapath/delivery"
    run = ROOT / "build/runs" / (
        datetime.now().strftime("%Y%m%d_%H%M%S_%f") + "_partner_datapath_b1"
    )
    run.mkdir(parents=True)
    print(f"RUN_DIR={run}", flush=True)

    filelist = delivery / "rtl/filelists/datapath_b1.f"
    sources = [
        delivery / line.strip()
        for line in filelist.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    tb = delivery / "tb/unit/tb_b1_memory_subsystem.sv"
    sources.append(tb)
    system_filelist = ROOT / "rtl/filelists/system_partner_datapath_b1.f"
    system_sources = [
        ROOT / line.strip()
        for line in system_filelist.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    protected_sources = list(dict.fromkeys(sources + system_sources))
    before = {str(path): digest(path) for path in protected_sources}
    (run / "sources.json").write_text(
        json.dumps([str(path) for path in sources], indent=2), encoding="utf-8"
    )

    found = tools()
    env = tool_env(found)
    result = {
        "status": "RUNNING",
        "run_dir": str(run),
        "sources": [str(path) for path in sources],
        "system_sources": [str(path) for path in system_sources],
        "source_hashes_before": before,
    }
    try:
        execute([found["xvlog"], "-sv", *sources], run, env, run / "compile.log")
        execute(
            [found["xelab"], "tb_b1_memory_subsystem", "-s", "b1_memory", "-debug", "all", "-mt", "2"],
            run,
            env,
            run / "compile.log",
        )
        (run / "run.tcl").write_text(
            "open_vcd {waves.vcd}\n"
            "log_vcd [get_objects -r /tb_b1_memory_subsystem/*]\n"
            "run all\nclose_vcd\nquit\n",
            encoding="utf-8",
        )
        execute(
            [found["xsim"], "b1_memory", "-tclbatch", "run.tcl", "-onerror", "quit"],
            run,
            env,
            run / "simulation.log",
        )
        log = (run / "simulation.log").read_text(encoding="utf-8", errors="replace")
        if "PASS: partner Datapath B1 memory subsystem" not in log:
            raise RuntimeError("simulation did not print the expected PASS marker")
        issues = [
            line
            for line in log.splitlines()
            if re.search(r"^(?:Error:|Fatal:|ERROR:|FAIL:)|assertion.*fail", line, re.I)
        ]
        if issues:
            raise RuntimeError("; ".join(issues))
        summary = re.search(r"^B1_MEMORY_RESULT (.*)$", log, re.M).group(1)
        integration_run = run / "integration_elaboration"
        integration_run.mkdir()
        execute(
            [found["xvlog"], "-sv", *system_sources],
            integration_run,
            env,
            integration_run / "compile.log",
        )
        execute(
            [found["xelab"], "face_soc_cpu_memory_top", "-s", "face_soc_cpu_memory", "-mt", "2"],
            integration_run,
            env,
            integration_run / "compile.log",
        )
        result.update(
            status="PASS",
            summary=summary,
            waves=str(run / "waves.vcd"),
            integration_top="PASS: face_soc_cpu_memory_top compiled and elaborated",
        )
        print(f"PASS {summary}", flush=True)
    except Exception as exc:
        result.update(status="FAIL", error=str(exc))
        print(f"FAIL {exc}", flush=True)
    finally:
        after = {str(path): digest(path) for path in protected_sources}
        result["sources_unchanged"] = before == after
        result["source_hashes_after"] = after
        (run / "result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        if before != after:
            raise RuntimeError("test modified a protected source file")
    return int(result["status"] != "PASS")


if __name__ == "__main__":
    raise SystemExit(main())
