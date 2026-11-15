"""Isolated XSim integration review; production sources remain unchanged."""
from __future__ import annotations
import argparse
import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from run_tests import ROOT, execute, tools, tool_env


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def ports(path):
    text = re.sub(r'//[^\n]*|/\*.*?\*/', '', path.read_text(encoding='utf-8'), flags=re.S)
    header = text[:text.index(');')]
    result = {}
    for match in re.finditer(r'\b(input|output)\s+logic\s*(\[\d+:\d+\])?\s*([^\n;]+)', header):
        direction, bus, names = match.groups()
        width = 1 if not bus else abs(int(bus[1:-1].split(':')[0])-int(bus[1:-1].split(':')[1]))+1
        for name in names.split(','):
            name = name.strip().rstrip(')')
            if name:
                assert re.fullmatch(r'\w+', name), name
                result[name] = [direction, width]
    return result


ADD_INITIAL = r'''
    wire [31:0] x6_value = dut.u_regfile.regs[6];
    integer rf_writes;
    always @(posedge clk) begin
        if (!rst_n) rf_writes <= 0;
        else if (dut.rf_we) rf_writes <= rf_writes+1;
    end
    initial begin
        errors=0; completed=0; program_words=1; rst_n=0;
        for (integer i=0;i<65536;i=i+1) u_imem.mem[i]=0;
        for (integer i=0;i<262144;i=i+1) u_dmem.mem[i]=0;
        put(0,32'h00208333);
        repeat(3) @(negedge clk);
        dut.u_regfile.regs[1]=1; dut.u_regfile.regs[2]=2;
        rst_n=1;
        repeat(10) begin
            @(negedge clk);
            $display("ADD_TRACE t=%0t pc=%h instr=%h D=%b E=%b M=%b W=%b a=%h b=%h result=%h result_m=%h wb=%h rd_w=%0d rf_we=%b x6=%0d writes=%0d",
                $time,dut.pc_q,instr_d,valid_d,valid_e,valid_m,valid_w,
                dut.alu_a_e,dut.alu_b_e,dut.alu_result_e,dut.alu_result_m,
                dut.wb_data_w,rd_w,dut.rf_we,dut.u_regfile.regs[6],rf_writes);
            if (valid_d && dut.pc_d==0) begin
                assert(instr_d==32'h00208333 && rs1_d==1 && rs2_d==2)
                    else $fatal(1,"ADD decode failed");
                assert(regwrite_d && !memread_d && !memwrite_d && alu_ctrl==ALU_ADD)
                    else $fatal(1,"ADD control failed");
            end
            if (valid_e && dut.pc_e==0) begin
                assert(dut.alu_a_e==1 && dut.alu_b_e==2 && dut.alu_result_e==3 && rd_e==6)
                    else $fatal(1,"ADD execution failed");
                assert(fwd_a==FWD_REG && fwd_b==FWD_REG && pc_sel==PC_NEXT)
                    else $fatal(1,"ADD forwarding/redirect failed");
            end
            if (valid_m && rd_m==6)
                assert(dut.alu_result_m==3 && !memread_m && !dut.memwrite_m)
                    else $fatal(1,"ADD M stage failed");
            if (valid_w && rd_w==6)
                assert(dut.wb_data_w==3 && regwrite_w)
                    else $fatal(1,"ADD writeback failed");
        end
        check_reg(1,1,"ADD source one"); check_reg(2,2,"ADD source two");
        check_reg(6,3,"ADD final result");
        assert(rf_writes==1 && dmem_reads==0 && dmem_writes==0 && mmio_reads==0 && mmio_writes==0 && load_stalls==0 && redirects==0)
            else $fatal(1,"ADD side-effect counts failed");
        if(errors) $fatal(1,"ADD register checks failed");
        $display("REAL_ADD_RESULT x1=%0d x2=%0d x6=%0d rf_writes=%0d dmem_reads=%0d dmem_writes=%0d stalls=%0d redirects=%0d",
            dut.u_regfile.regs[1],dut.u_regfile.regs[2],dut.u_regfile.regs[6],rf_writes,dmem_reads,dmem_writes,load_stalls,redirects);
        $display("PASS: real Control + production Datapath ADD");
        $finish;
    end
endmodule
'''


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--datapath-root', type=Path, required=True)
    args = parser.parse_args()
    dp = args.datapath_root.resolve()
    run = ROOT / 'build/runs' / (datetime.now().strftime('%Y%m%d_%H%M%S_%f')+'_real_datapath_review')
    run.mkdir(parents=True)
    print('RUN_DIR='+str(run), flush=True)
    dp_sources = [dp/line.strip() for line in (dp/'rtl/filelists/cpu_datapath.f').read_text().splitlines() if line.strip()]
    ctl_sources = [ROOT/line.strip() for line in (ROOT/'rtl/filelists/cpu_control.f').read_text().splitlines() if line.strip()][1:]
    protected = dp_sources + ctl_sources + [ROOT/'rtl/common/cpu_control_pkg.sv']
    before = {str(path): sha(path) for path in protected}
    ctl_ports = ports(ROOT/'rtl/cpu_control/cpu_control.sv')
    dp_ports = ports(dp/'rtl/cpu_datapath/cpu_datapath.sv')
    assert len(ctl_ports)==48, ctl_ports
    interface = []
    for name, (direction, width) in ctl_ports.items():
        wanted = direction if name in ('clk','rst_n') else ('input' if direction=='output' else 'output')
        assert dp_ports[name]==[wanted,width], (name,dp_ports[name],[wanted,width])
        interface.append({'name':name,'control':ctl_ports[name],'datapath':dp_ports[name]})
    local_pkg = (ROOT/'rtl/common/cpu_control_pkg.sv').read_text(encoding='utf-8')
    dp_pkg = (dp/'rtl/common/cpu_control_pkg.sv').read_text(encoding='utf-8')
    strip = lambda s: re.sub(r'\s+', '', re.sub(r'//[^\n]*|/\*.*?\*/', '', s, flags=re.S))
    baseline = strip(local_pkg).removesuffix('endpackage')
    assert strip(dp_pkg).startswith(baseline), 'Datapath package does not preserve Control baseline definitions'
    release_hashes=[]
    for line in (dp/'docs/datapath_release_sha256.txt').read_text().splitlines():
        digest, relative = line.split(' *',1)
        assert sha(dp/relative)==digest, relative
        release_hashes.append(relative)
    package_check={'baseline_sha256':sha(ROOT/'rtl/common/cpu_control_pkg.sv'),
                   'integration_candidate_sha256':sha(dp/'rtl/common/cpu_control_pkg.sv'),
                   'control_definitions_preserved':True,'one_package_compiled':True,
                   'release_files_hash_checked':len(release_hashes)}
    result={'status':'RUNNING','datapath_root':str(dp),'run_dir':str(run),
            'interface':interface,'package':package_check,'tests':{},
            'real_cnn':'NOT_RUN: not provided','memory':'test-only synchronous models',
            'production_hashes_before':before}
    (run/'compatibility_checks.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    text=(dp/'tb/integration/tb_cpu_datapath.sv').read_text(encoding='utf-8')
    assert text.count('control_stub u_control')==1
    text=text.replace('control_stub u_control','cpu_control u_control')
    found=tools();env=tool_env(found)
    try:
        for name in ('add','mixed'):
            job=run/name;job.mkdir();(job/'waves').mkdir()
            # The supplied test-only memories initialize rdata in one process
            # and update it in always_ff. XSim rejects that driver combination.
            # Use plain clocked always in local model copies; NBA read latency
            # and all model statements are preserved. Production RTL is untouched.
            model_dir=job/'models';model_dir.mkdir()
            models=[]
            for model_name in ('imem_model.sv','dmem_model.sv','cnn_mmio_stub.sv'):
                model=(dp/'tb/models'/model_name).read_text(encoding='utf-8')
                if model_name in ('imem_model.sv','dmem_model.sv'):
                    model=model.replace('always_ff @(posedge clk)', 'always @(posedge clk)')
                model_path=model_dir/model_name
                model_path.write_text(model,encoding='utf-8');models.append(model_path)
            result['test_model_adaptation']='Local imem/dmem copies: always_ff -> clocked always for XSim initialization compatibility; synchronous nonblocking read/write semantics preserved'
            tb=text
            if name=='add':
                tb=text[:text.index('    int jalr_setup_index')]+ADD_INITIAL
            else:
                tb=tb.replace('errors=0; completed=0; program_words=0; rst_n=0;',
                    'errors=0; completed=0; program_words=0; rst_n=0;\n'
                    '        for(integer i=0;i<65536;i=i+1) u_imem.mem[i]=0;\n'
                    '        for(integer i=0;i<262144;i=i+1) u_dmem.mem[i]=0;')
                tb=tb.replace('$display("PASS: complete CPU datapath with test stubs");',
                    '$display("REAL_MIXED_RESULT cycles=%0d stalls=%0d redirects=%0d dmem_reads=%0d dmem_writes=%0d mmio_reads=%0d mmio_writes=%0d",cycles,load_stalls,redirects,dmem_reads,dmem_writes,mmio_reads,mmio_writes);\n'
                    '        $display("PASS: real Control + production Datapath mixed program");')
            (job/'tb_real_control_datapath.sv').write_text('`timescale 1ns/1ps\n'+tb,encoding='utf-8')
            sources=dp_sources+ctl_sources+models+[job/'tb_real_control_datapath.sv']
            (job/'sources.json').write_text(json.dumps([str(path) for path in sources],indent=2),encoding='utf-8')
            execute([found['xvlog'],'-sv',*sources],job,env,job/'compile.log')
            execute([found['xelab'],'tb_cpu_datapath','-s','real_control_dp','-debug','all','-mt','2'],job,env,job/'compile.log')
            (job/'run.tcl').write_text('open_vcd {waves/real_control_datapath.vcd}\nlog_vcd [get_objects -r /tb_cpu_datapath/*]\nrun all\nclose_vcd\nquit\n',encoding='utf-8')
            execute([found['xsim'],'real_control_dp','-tclbatch','run.tcl','-onerror','quit'],job,env,job/'simulation.log')
            log=(job/'simulation.log').read_text(encoding='utf-8')
            assert f'PASS: real Control + production Datapath {"ADD" if name=="add" else "mixed program"}' in log
            issues=[line for line in log.splitlines() if re.search(r'^(?:Error:|Fatal:|ERROR:|FAIL:)|assertion.*fail',line,re.I)]
            assert not issues,issues
            summary=re.search(r'^REAL_(?:ADD|MIXED)_RESULT (.*)$',log,re.M).group(1)
            result['tests'][name]={'status':'PASS','summary':summary,'waves':str(job/'waves/real_control_datapath.vcd')}
            print(name.upper()+' PASS '+summary,flush=True)
        result['status']='PASS'
    except Exception as exc:
        result.update(status='FAIL',error=str(exc))
        print('FAIL '+str(exc),flush=True)
    finally:
        after={str(path):sha(path) for path in protected}
        result['production_sources_unchanged']=before==after
        result['production_hashes_after']=after
        assert before==after
        (run/'result.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    return int(result['status']!='PASS')


if __name__=='__main__':
    raise SystemExit(main())
