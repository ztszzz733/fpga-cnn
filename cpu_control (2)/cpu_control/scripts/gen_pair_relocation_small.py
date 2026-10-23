"""Exercise the full-network address planner on existing small numeric fixtures."""
import json,struct
from pathlib import Path
from gen_network_parallel import small_source,ROOT
from plan_full_buffered import compile_plan
def main():
 root=ROOT/'build/pair_relocation_small';assert not root.exists();root.mkdir()
 paths=[]
 for f in range(2):
  chain=ROOT/f'build/network_parallel_data/face{f}'
  m,g,jobs,ranges=small_source(chain,ROOT/'build/dw7_cached_data/real512',f)
  src=root/f'face{f}';src.mkdir();paths.append(src)
  for n,b in [('memory.bin',m),('golden.bin',g),('jobs.bin',b''.join(struct.pack('<16I',*j) for j in jobs)),('mutable.bin',b''.join(struct.pack('<II',a,n) for a,n in sorted(set(ranges))))]:
   (src/n).write_bytes(b)
  w=json.loads((chain/'workload.json').read_text());w['layers']=[l | {'scale':l['output_scale']} for l in w['layers']]
  (src/'workload.json').write_text(json.dumps(w,indent=2))
 compile_plan(paths,root/'plan',small=True)
if __name__=='__main__':main()
