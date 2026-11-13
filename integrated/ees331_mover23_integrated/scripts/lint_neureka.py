"""Elaborate the six-module NEureka SoC entry with the pinned source list."""
import os
from pathlib import Path
from run_tests import ROOT, execute

runtime = ROOT / '.tools/verilator-linux/verilator'
env = os.environ.copy()
env['VERILATOR_ROOT'] = str(runtime)
log = ROOT / 'build/neureka_top_lint.log'
log.parent.mkdir(exist_ok=True)
execute([runtime / 'bin/verilator_bin', '--lint-only', '--timing', '--assert',
         '-Wno-fatal', '--top-module', 'face_soc_neureka_top',
         '-f', 'rtl/filelists/system_neureka.f'], ROOT, env, log, timeout=600)
print('PASS six-module SoC elaboration; warnings retained in ' + str(log))
