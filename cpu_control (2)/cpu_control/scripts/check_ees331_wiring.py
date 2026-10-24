"""Audit the implemented peer connections against the frozen draw.io signals."""
import json,re,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def main():
    manifest=ROOT/'deliverables/ees331_ddr_io/io_manifest.json'
    top=ROOT/'rtl/soc/ees331/face_soc_ees331_top.sv'
    text=top.read_text(encoding='utf-8');links=json.loads(manifest.read_text(encoding='utf-8'))['after']
    peers={'cpu':'u_cpu_core','imem':'u_imem','cnn':'u_cnn','ram':'u_datasram','bridge':'u_image_bridge','clock':'u_clock_unit','ps':'u_ps'}
    # Check the actual named connections, not just whether signal names occur.
    connections={}
    for key,instance in peers.items():
        start=text.index(instance+' (')+len(instance)+2
        level=1;i=start
        while level:
            i+=1
            if text[i]=='(':level+=1
            elif text[i]==')':level-=1
        connections[key]=dict(re.findall(r'\.(\w+)\(\s*(\w+)\s*\)',text[start:i]))
    declared={}
    for hi,lo,name in re.findall(r'\bwire\s+(?:\[(\d+):(\d+)\]\s*)?(\w+)\s*(?=[,;\n])',text):
        width=abs(int(hi)-int(lo))+1 if hi else 1
        assert name not in declared or declared[name]==width,'Conflicting widths '+name
        declared[name]=width
    checked=[]
    for link in links:
        if link['id'] in ['U','K']:continue
        for group in ['address','data','control']:
            for s in link[group]:
                name=s['name'];assert declared.get(name)==s['width'],f'Diagram width differs: {name}'
                for endpoint in [link['source'],link['target']]:
                    if endpoint in peers:
                        assert connections[endpoint].get(name)==name,f'{endpoint} misconnected {name}'
                checked.append(dict(interface=link['id'],group=group,**s))
    for p in ['cpu','imem','cnn','ram','bridge']:
        assert connections[p]['clk']=='clk' and connections[p]['rst_n']=='rst_n',p+' clock/reset'
    assert 'assign sys_clk=FCLK_CLK0;' in text
    assert 'assign rst_n_in=FCLK_RESET0_N;' in text
    assert 'assign M_AXI_GP0_ACLK=clk;' in text and 'assign S_AXI_HP0_ACLK=clk;' in text
    assert 'mobilefacenet_accelerator_top' not in text and 'datasram_banked' not in text
    assert "#(.IMEM_SIZE(32'h2000)" in text
    assert 'CPU_RAM_BYTES(16384)' in text and 'CACHE_BYTES=131072' in text
    listing=(ROOT/'rtl/filelists/system_ees331.f').read_text()
    assert 'partners/cnn/' not in listing and 'rtl/soc/face_soc_top.sv' not in listing
    ps=(ROOT/'scripts/create_ees331_bd.tcl').read_text()
    assert 'CONFIG.PCW_UART1_UART1_IO {MIO 48 .. 49}' in ps
    assert 'CONFIG.PCW_S_AXI_HP0_DATA_WIDTH {64}' in ps
    assert 'CONFIG.PCW_FPGA0_PERIPHERAL_FREQMHZ {50.000000}' in ps
    result=dict(status='PASS',signals=len(checked),peer_instances=peers,
        top_sha256=hashlib.sha256(top.read_bytes()).hexdigest(),diagram_manifest_sha256=hashlib.sha256(manifest.read_bytes()).hexdigest(),
        signals_checked=checked,clock='PS FCLK0 to shared clk; synchronous reset release',uart='PS UART1 MIO48 TX / MIO49 RX; no PL UART pins',
        boundary='Static names/widths/endpoint check plus separate actual top RTL simulation; not board validation')
    out=ROOT/'build/ees331_wiring_check.json';out.parent.mkdir(exist_ok=True);out.write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    print(f'PASS: {len(checked)} diagram signals, six PL peers plus PS7, clock/reset and UART1 route')
if __name__=='__main__':main()
