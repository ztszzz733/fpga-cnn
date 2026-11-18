from pathlib import Path
import json,subprocess
import simulate
root=Path(__file__).resolve().parent
out=root/'k3_planned_test'
out.mkdir(exist_ok=True)
native=simulate.native_tools(simulate.REFERENCE/'.tools/verilator-native/verilator',Path('D:/visual studio2'))
sources=[root.parent/'source/rtl/cnn_self'/name for name in ('self_conv_spatial4_engine.sv','compact_word_ram.sv','planned_read_adapter.sv')]
exe=native.build_native(sources,'self_conv_spatial4_engine',out/'compile',main=root/'k3_planned_test.cpp',jobs=2,
                       verilator_args=['--no-timing','--assert'])
result=subprocess.run([str(exe)],capture_output=True,text=True,timeout=120)
(out/'simulation.log').write_text(result.stdout+result.stderr)
(out/'result.json').write_text(json.dumps(dict(status='PASS' if result.returncode==0 else 'FAIL',
 sources_sha256={str(p.relative_to(root.parent/'source')):simulate.sha(p) for p in sources},
 test_sha256=simulate.sha(root/'k3_planned_test.cpp'),output=result.stdout+result.stderr),indent=2)+'\n')
print(result.stdout+result.stderr);result.check_returncode()
