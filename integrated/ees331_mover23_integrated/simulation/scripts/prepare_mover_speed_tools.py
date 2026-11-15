from pathlib import Path
SIM=Path(__file__).resolve().parents[1]
r=(SIM/'scripts/run_reduced_soc.py').read_text(encoding='utf-8')
r=r.replace("'_reduced_single_soc'","'_mover_speed_soc'").replace('reduced_soc_active.json','mover_speed_soc_active.json')
r=r.replace("'clock_reference':", "'optimization':'aligned local word accesses, response/request overlap, up to 16 AXI3 beats; same CNN and 392 KiB shared RAM','baseline_run':'20261112_203157_reduced_single_soc','clock_reference':")
(SIM/'scripts/run_mover_speed_soc.py').write_text(r,encoding='utf-8')
print('prepared mover speed SoC runner and metrics')
