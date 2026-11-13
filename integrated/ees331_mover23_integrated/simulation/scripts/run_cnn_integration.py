"""Run real CPU + FPGA1 + dual-port SRAM tests using the existing XSim setup."""
from __future__ import annotations
import hashlib
import json
import re
from datetime import datetime
from run_tests import ROOT, tools, tool_env, execute


def sources():
    baseline = ROOT / "rtl/filelists/system_cnn.f"
    result = [ROOT / s.strip() for s in baseline.read_text().splitlines()
              if s.strip() and not s.lstrip().startswith("#")]
    return result


def main():
    run = ROOT / "build/runs" / (datetime.now().strftime("%Y%m%d_%H%M%S_%f") + "_cnn_integration")
    run.mkdir(parents=True)
    print(f"RUN_DIR={run}", flush=True)
    found = tools()
    env = tool_env(found)
    src = sources()
    benches = ["tb_cnn_native_memory", "tb_cpu_cnn_integration", "tb_soc_uart"]
    src += [ROOT / "tb/integration" / (b + ".sv") for b in benches]
    result = {"status": "RUNNING", "run_dir": str(run), "tests": {},
              "source_hashes": {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in src}}
    try:
        execute([found["xvlog"], "-sv", *src], run, env, run / "compile.log")
        for bench in benches:
            execute([found["xelab"], bench, "-s", bench, "-debug", "typical", "-mt", "2"],
                    run, env, run / "compile.log", timeout=240)
            tcl = run / (bench + ".tcl")
            tcl.write_text(f"open_vcd {{{bench}.vcd}}\nlog_vcd [get_objects /{bench}/*]\nrun all\nclose_vcd\nquit\n")
            log = run / (bench + ".log")
            execute([found["xsim"], bench, "-tclbatch", tcl.name, "-onerror", "quit"],
                    run, env, log, timeout=240)
            content = log.read_text(encoding="utf-8", errors="replace")
            if f"PASS {bench}" not in content or re.search(r"^(?:Error:|Fatal:|ERROR:|FAIL)", content, re.M):
                raise RuntimeError(f"Test failed: {log}")
            result["tests"][bench] = "PASS"
            print(f"PASS {bench}", flush=True)
        result["status"] = "PASS"
    except Exception as exc:
        result.update(status="FAIL", error=str(exc))
        print(str(exc), flush=True)
    (run / "result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return int(result["status"] != "PASS")


if __name__ == "__main__":
    raise SystemExit(main())
