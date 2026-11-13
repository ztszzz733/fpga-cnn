"""Read selected signals from the original VCD without changing it."""
from pathlib import Path
import collections,json

ROOT=Path(__file__).resolve().parent
PREFIX='TOP.ees331_soc_mover23_sim_top.'
META=['debug_unit_start','debug_unit_active','debug_completion','debug_completed','debug_error','debug_fault',
      'debug_page_misses','debug_mover_read_bytes','debug_mover_write_bytes']
DUT=['clk','rst_n','cnn_valid','cnn_ready','cnn_response','cnn_write','cnn_byte','cnn_addr','cnn_rdata','cnn_wdata','cnn_cancel','cnn_mem_fault',
     'cnn_mmio_we','cnn_mmio_ready','cnn_mmio_addr','cnn_mmio_wdata','cache_csr_we','cache_csr_ready','cache_csr_addr','cache_csr_wdata']
DUT += ['S_AXI_HP0_'+s for s in ['ARVALID','ARREADY','ARADDR','ARSIZE','ARLEN','RVALID','RREADY','RRESP','RLAST',
    'AWVALID','AWREADY','AWADDR','AWSIZE','AWLEN','WVALID','WREADY','WSTRB','BVALID','BREADY','BRESP']]
PATHS={PREFIX+n:n for n in META+['debug_work','debug_node']}
PATHS.update({PREFIX+'dut.'+n:n for n in DUT})
PARAMS={'K3_UNITS','K1_UNITS','POST_UNITS','UNITS','PAGE_BYTES'}

def main():
    codes=collections.defaultdict(list);scope=[];state={};events=collections.defaultdict(list);changes=collections.Counter()
    parameter_codes=collections.defaultdict(list);widths={};clock_edges=[];handshakes=collections.Counter();samples=collections.defaultdict(list)
    unit_launches=[0]*23;cnn_accepts=[0]*23;cnn_responses=[0]*23;bad_responses=[]
    unknowns=collections.Counter();t=0;old_clock=None;end=0
    def finish_timestamp():
        nonlocal old_clock
        clk=state.get('clk')
        if clk!=old_clock and len(clock_edges)<12:clock_edges.append([t,clk])
        rising=old_clock==0 and clk==1;old_clock=clk
        if not rising or not state.get('rst_n'):return
        accepted=(state.get('cnn_valid',0) or 0)&(state.get('cnn_ready',0) or 0)
        response=state.get('cnn_response',0) or 0
        if response and len(samples['cnn_response'])<8:samples['cnn_response'].append(dict(time_ps=t,mask=hex(response)))
        for u in range(23):
            cnn_accepts[u]+=bool(accepted&(1<<u));cnn_responses[u]+=bool(response&(1<<u))
        if accepted and len(samples['cnn_accept'])<12:
            address=state.get('cnn_addr',0) or 0
            for u in range(23):
                if accepted&(1<<u):samples['cnn_accept'].append(dict(time_ps=t,unit=u,address=(address>>(32*u))&0xffffffff,write=bool((state.get('cnn_write',0) or 0)&(1<<u))))
        for channel in ('AR','R','AW','W','B'):
            valid=state.get('S_AXI_HP0_'+channel+'VALID');ready=state.get('S_AXI_HP0_'+channel+'READY')
            if valid and ready:
                handshakes[channel]+=1
                if len(samples['HP0_'+channel])<5:
                    samples['HP0_'+channel].append(dict(time_ps=t,address=state.get('S_AXI_HP0_'+channel+'ADDR'),
                        response=state.get('S_AXI_HP0_'+channel+'RESP')))
                if channel in ('R','B') and state.get('S_AXI_HP0_'+channel+'RESP')!=0:bad_responses.append([t,channel,state.get('S_AXI_HP0_'+channel+'RESP')])
        if state.get('cnn_mmio_we') and state.get('cnn_mmio_ready') and 500000<t<520000:
            samples['start_mmio'].append(dict(time_ps=t,address=state.get('cnn_mmio_addr'),data=state.get('cnn_mmio_wdata')))
    with (ROOT/'mover23_top_raw.vcd').open('rb',buffering=1024*1024) as f:
        for line in f:
            a=line.split()
            if not a:continue
            token=a[0]
            if token==b'$scope':scope.append(a[2].decode('ascii'))
            elif token==b'$upscope':scope.pop()
            elif token==b'$var':
                path='.'.join(scope+[a[4].decode('ascii')]);code=a[3]
                if path in PATHS:
                    if PATHS[path] not in codes[code]:codes[code].append(PATHS[path])
                    widths[PATHS[path]]=int(a[2])
                if path.startswith(PREFIX+'dut.') and a[4].decode('ascii') in PARAMS:
                    parameter_codes[code].append(path)
            elif token==b'$enddefinitions':break
        for line in f:
            lead=line[:1]
            if lead==b'#':finish_timestamp();t=int(line[1:]);end=t;continue
            if lead in (b'b',b'B'):
                value,_,code=line.strip().partition(b' ')
                if code not in codes and code not in parameter_codes:continue
                bits=value[1:]
            elif lead in (b'0',b'1',b'x',b'X',b'z',b'Z'):
                code=line[1:].strip()
                if code not in codes and code not in parameter_codes:continue
                bits=lead
            else:continue
            try:value=int(bits,2)
            except ValueError:value=None
            for path in parameter_codes.get(code,[]):state[path]=value
            if code not in codes:continue
            for name in codes[code]:
                if value is None:unknowns[name]+=1
                if name not in state or state[name]!=value:
                    changes[name]+=1
                    if name in META or name in ('S_AXI_HP0_ARADDR','S_AXI_HP0_AWADDR','S_AXI_HP0_ARSIZE','S_AXI_HP0_AWSIZE','rst_n'):
                        events[name].append([t,value])
                    if name=='debug_unit_start' and value:
                        for u in range(23):unit_launches[u]+=bool(value&(1<<u))
                    if name=='debug_unit_active' and value and value.bit_count()>=4 and len(samples['four_active'])<5:
                        samples['four_active'].append(dict(time_ps=t,mask=hex(value),units=[u for u in range(23) if value&(1<<u)]))
                state[name]=value
        finish_timestamp()
    metrics=json.loads((ROOT/'metrics.json').read_text(encoding='utf-8'))
    assert unit_launches==metrics['unit_starts'] and sum(unit_launches)==44
    assert max(v for _,v in events['debug_completed'] if v is not None)==44
    assert state['debug_mover_read_bytes']==metrics['ddr_read_bytes']==27648
    assert state['debug_mover_write_bytes']==metrics['ddr_write_bytes']==23552
    report=dict(status='SELECTED_SIGNALS_CHECKED',timescale='1ps',last_timestamp_ps=end,
        clock_first_edges=clock_edges,parameters={k:v for k,v in state.items() if k.startswith(PREFIX)},
        unit_launches=unit_launches,active_unit_count=sum(v>0 for v in unit_launches),
        cnn_accepted_requests_by_unit=cnn_accepts,cnn_responses_by_unit=cnn_responses,
        hp0_observed_post_edge_valid_ready=dict(handshakes),hp0_nonzero_response_samples=bad_responses,
        signal_change_counts=dict(changes),unknown_value_records=dict(unknowns),milestone_events=dict(events),samples=dict(samples),
        note='Selected-signal observation, not a new RTL simulation or full AXI protocol proof. Post-edge valid/ready observations must not be used as accepted transaction counts.')
    (ROOT/'波形阅读核对.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:report[k] for k in ('last_timestamp_ps','clock_first_edges','parameters','active_unit_count','hp0_nonzero_response_samples')},ensure_ascii=False))
    print('HP0 address first/last',events['S_AXI_HP0_ARADDR'][:3],events['S_AXI_HP0_ARADDR'][-2:])
    print('START writes',samples['start_mmio']);print('FIRST CNN accesses',samples['cnn_accept'])
    print('FOUR ACTIVE',samples['four_active'])
    print('FIRST RESPONSES',samples['cnn_response'])

if __name__=='__main__':main()
