"""Audit upstream RTL byte identity and the current six-block compile boundary."""
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def audit_zip(path, folder, prefix):
    results = {}
    with zipfile.ZipFile(path) as archive:
        for local in sorted(folder.glob("*.sv")):
            member = prefix + local.name
            data = local.read_bytes()
            assert data == archive.read(member), f"Upstream changed: {local}"
            results[str(local.relative_to(ROOT))] = hashlib.sha256(data).hexdigest()
    assert results, f"No source files: {folder}"
    return results


def main():
    result = {}
    result["cnn"] = audit_zip(Path("D:/QQ/FPGA1.zip"), ROOT / "partners/cnn/FPGA1/rtl", "FPGA1/rtl/")
    result["datapath"] = audit_zip(Path("D:/QQ/face_recognition_soc_datapath_complete.zip"),
                                   ROOT / "partners/datapath/delivery/rtl/cpu_datapath", "rtl/cpu_datapath/")
    original = (ROOT / "partners/cnn/FPGA1/rtl/tensor_operator_engine.sv").read_text()
    compatible = (ROOT / "rtl/compat/tensor_operator_engine.sv").read_text()
    result["compat_diff"] = compatible == original.replace(
        "wire signed [31:0] pool_next,pool_sample=rsp_data;",
        "wire signed [31:0] pool_next, pool_sample;\n    assign pool_sample = rsp_data;")
    assert result["compat_diff"], "Unexpected compatibility edits"
    top = (ROOT / "rtl/soc/face_soc_top.sv").read_text()
    instances = re.findall(r"\b(u_\w+)\s*\(", top)
    assert sorted(instances) == sorted(["u_clock_unit", "u_image_bridge", "u_cpu_core", "u_imem", "u_datasram", "u_cnn"])
    result["board_instances"] = instances
    files = [s.strip() for s in (ROOT / "rtl/filelists/system_cnn.f").read_text().splitlines()
             if s.strip() and not s.lstrip().startswith("#")]
    assert len(files) == len(set(files)) and all((ROOT / s).is_file() for s in files)
    banned = ["sram_b_arbiter.sv", "cnn_memory_adapter.sv", "datapath_memory_subsystem.sv",
              "face_soc_cpu_memory_top.sv", "cnn_mmio_regs.sv", "data_sram_tdp.sv"]
    assert not any(Path(s).name in banned for s in files)
    result["compile_sources"] = len(files)
    result["status"] = "PASS"
    run = ROOT / "build/runs" / (datetime.now().strftime("%Y%m%d_%H%M%S_%f") + "_soc_source_audit")
    run.mkdir(parents=True)
    (run / "result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"PASS CNN={len(result['cnn'])}, Datapath={len(result['datapath'])}, six instances, sources={len(files)}")
    print(f"RUN_DIR={run}")


if __name__ == "__main__":
    main()
