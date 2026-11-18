from pathlib import Path
import subprocess,json
import simulate
root=Path(__file__).resolve().parent
out=root/'planned_reads_test'
out.mkdir(exist_ok=True)
native=simulate.native_tools(simulate.REFERENCE/'.tools/verilator-native/verilator',Path('D:/visual studio2'))
source=root.parent/'source/rtl/cnn_self/planned_read_adapter.sv'
exe=native.build_native([source],'planned_read_adapter',out/'compile',main=root/'planned_reads_test.cpp',jobs=2,
                       verilator_args=['--no-timing','--assert'])
result=subprocess.run([str(exe)],capture_output=True,text=True,timeout=120)
(out/'simulation.log').write_text(result.stdout+result.stderr)
(out/'result.json').write_text(json.dumps(dict(status='PASS' if result.returncode==0 else 'FAIL',
 source_sha256=simulate.sha(source),test_sha256=simulate.sha(root/'planned_reads_test.cpp'),
 output=result.stdout+result.stderr),indent=2)+'\n')
print(result.stdout+result.stderr)
result.check_returncode()
