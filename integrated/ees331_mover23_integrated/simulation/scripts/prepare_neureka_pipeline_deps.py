"""Fetch only the pinned RTL dependency closure used by the pipeline filelist.
No shell-based recursive git-submodule command; works on native Windows.
"""
import os,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
PINS=[
 ('third_party/vicuna2_tests','vproc/vicuna2_unit_testing','1574ca9c8bbebadb683a7142b5b5d3688bfff655'),
 ('third_party/vicuna2_tests/rtl/cv32e40x','ParkerJones567/cv32e40x_f_zhf','e898ef54f3ea88aef6b1537db9b0102517da5984'),
 ('third_party/vicuna2_tests/rtl/fpu_ss','ParkerJones567/fpu_ss','823a7fc1cca17ce4238cc460bdbb6a442bf9bec8'),
 ('third_party/vicuna2_tests/rtl/vicuna2_core','vproc/vicuna2_core','6409dd155419c57959178a263e450a935f8d3cb7'),
 ('third_party/vicuna2_tests/rtl/vicuna2_core/cvfpu','openhwgroup/cvfpu','2c7947726a0859c08cc27cbbd45662424dedb41e'),
 ('third_party/vicuna2_tests/rtl/vicuna2_core/pulp_common_cells','pulp-platform/common_cells','9ca8a7655f741e7dd5736669a20a301325194c28'),
 ('third_party/vicuna2_tests/rtl/vicuna2_core/cvfpu/src/common_cells','pulp-platform/common_cells','6aeee85d0a34fedc06c14f04fd6363c9f7b4eeea'),
 ('third_party/vicuna2_tests/rtl/vicuna2_core/cvfpu/src/fpu_div_sqrt_mvp','pulp-platform/fpu_div_sqrt_mvp','86e1f558b3c95e91577c41b2fc452c86b04e85ac')]

def main():
    git=['git']+(['-c','http.sslBackend=openssl'] if os.name=='nt' else [])
    for relative,repo,pin in PINS:
        dest=ROOT/relative
        if not (dest/'.git').exists():
            subprocess.run([*git,'clone','--filter=blob:none','--no-checkout','https://github.com/'+repo+'.git',str(dest)],check=True)
            subprocess.run([*git,'-C',str(dest),'checkout',pin],check=True)
        actual=subprocess.check_output([*git,'-C',str(dest),'rev-parse','HEAD'],text=True).strip()
        if actual!=pin:raise RuntimeError(str(dest)+' has a different HEAD; preserve it and resolve explicitly')
        print(relative,actual)
if __name__=='__main__':main()
