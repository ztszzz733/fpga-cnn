import importlib.util
import sys
from pathlib import Path
import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from plot_waveforms import read_vcd, segments, choose, render

def fixture(tmp_path,scale='10 ps'):
    p=tmp_path/'tiny.vcd'
    p.write_text(f'''$timescale {scale} $end
$scope module top $end
$var wire 1 ! clk $end
$var wire 4 # bus [3:0] $end
$var wire 4 # alias [3:0] $end
$var wire 1 & constant $end
$upscope $end
$enddefinitions $end
$dumpvars
0!
bx #
1&
$end
#5
1!
b10xz #
b0011 #
#10
0!
bz #
#20
''',encoding='utf-8')
    return p

@pytest.mark.parametrize('scale,factor',[('10 ps',.01),('1 ns',1),('100 fs',.0001),('1 us',1000)])
def test_scale_initial_alias_and_same_timestamp(tmp_path,scale,factor):
    v=read_vcd(fixture(tmp_path,scale))
    assert v.end_ns==pytest.approx(20*factor)
    assert v.signals['top.bus'].width==4
    assert v.signals['top.bus'].events is v.signals['top.alias'].events
    assert v.signals['top.bus'].events==[(0,'xxxx'),(5*factor,'0011'),(10*factor,'zzzz')]
    assert v.signals['top.constant'].events==[(0,'1')]

def test_window_inherits_and_extends(tmp_path):
    v=read_vcd(fixture(tmp_path,'1 ns'))
    assert list(segments(v.signals['top.bus'],7,19))==[(7,10,'0011'),(10,19,'zzzz')]
    assert list(segments(v.signals['top.constant'],7,19))==[(7,19,'1')]

def test_exact_paths_missing_and_optional(tmp_path):
    v=read_vcd(fixture(tmp_path));c={'groups':{'g':[{'path':'bus'}]}}
    with pytest.raises(ValueError,match='必选信号'): choose(v,c,'g')
    c['groups']['g']=[{'path':'missing','optional':True},{'path':'top.bus'}]
    with pytest.warns(UserWarning): assert len(choose(v,c,'g'))==1

@pytest.mark.parametrize('start,end',[(1,1),(2,1),(25,30),(-1,1)])
def test_bad_windows(tmp_path,start,end):
    import json
    p=fixture(tmp_path,'1 ns');c=tmp_path/'signals.json';c.write_text(json.dumps({'groups':{'g':[{'path':'top.bus'}]}}))
    with pytest.raises(ValueError): render(p,c,tmp_path/'plots',start_ns=start,end_ns=end)

def test_unknown_and_constant_plot(tmp_path):
    import json
    p=fixture(tmp_path,'1 ns');c=tmp_path/'signals.json';c.write_text(json.dumps({'groups':{'g':[{'path':'top.bus'},{'path':'top.clk'},{'path':'top.constant'}]}}))
    render(p,c,tmp_path/'plots',start_ns=0,end_ns=20)
    svg=(tmp_path/'plots/waveforms.svg').read_text()
    assert 'XXXX' in svg and 'ZZZZ' in svg and 'Source:' in svg and 'Time (ns)' in svg

def test_partial_unknown_not_zeroed(tmp_path):
    p=fixture(tmp_path,'1 ns');p.write_text(p.read_text().replace('b0011 #\n',''))
    assert read_vcd(p).signals['top.bus'].events[1]==(5,'10xz')
