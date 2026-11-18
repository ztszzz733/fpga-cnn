from pathlib import Path
import re

root = Path(__file__).resolve().parent
p = root / 'source/rtl/cnn_ddr/cnn_paged_mover.sv'
s = p.read_text()
start = s.index(' function automatic logic [1:0] bank_of_slot')
end = s.index(' typedef enum', start)
s = s[:start] + ''' // 392 KiB remains resident: two banks of 196 one-KiB slots.
 function automatic logic [1:0] bank_of_slot(input logic [SB-1:0] slot);
  if(LOCAL_BYTES==401408 && PAGE_BYTES==1024)bank_of_slot=slot>=SB'(196)?2'd1:2'd0;
  else bank_of_slot=2'd0;
 endfunction
 function automatic logic [SB-1:0] slot_from_turn(input logic [SB-1:0] turn);
  if(LOCAL_BYTES==401408 && PAGE_BYTES==1024)
   slot_from_turn=turn[0]?SB'(196+(int'(turn)>>1)):SB'(turn>>1);
  else slot_from_turn=turn;
 endfunction
''' + s[end:]
for marker in ('issue_', 'reply_', 'fast_', 'grant_tree', 'grant_index_tree', 'comp_', 'bank_reply_', 'read_byte'):
    lines = s.splitlines(True)
    s = ''.join(line.replace('[3:0]', '[1:0]', 1) if re.match(r'\s*(wire|logic) \[3:0\]', line) and marker in line else line for line in lines)
s = s.replace('bank_round_robin[4]', 'bank_round_robin[2]')
s = s.replace('bank_eligible[4],bank_after[4],bank_candidates[4]', 'bank_eligible[2],bank_after[2],bank_candidates[2]')
s = s.replace('b<4', 'b<2').replace('a<4', 'a<2')
s = s.replace('tile_local_ram_bank4 #', 'tile_local_ram_bank2 #')
s = s.replace('// Four independent compute banks', '// Two independent compute banks')
s = s.replace('Four request entries per client', 'Four request entries per client')
p.write_text(s)
p = root / 'source/rtl/filelists/system_ees331_reduced.f'
p.write_text(p.read_text().replace('tile_local_ram_bank4.sv', 'tile_local_ram_bank2.sv'))
p = root / 'arm_schedule/check_pager.py'
p.write_text(p.read_text().replace('tile_local_ram_bank4.sv', 'tile_local_ram_bank2.sv'))
p = root / 'arm_schedule/pager_regression.cpp'
s = p.read_text().replace('b < 4; ++b', 'b < 2; ++b')
s = s.replace('unsigned parallel = 0;', 'unsigned parallel = 0;\n            unsigned bank_mask = d.rootp->cnn_paged_mover__DOT__comp_req;\n            unsigned bank_parallel = (bank_mask & 1u) + ((bank_mask >> 1) & 1u);')
s = s.replace('std::max(maximum_parallel, parallel)', 'std::max(maximum_parallel, bank_parallel)')
s = s.replace('maximum_parallel == 4, "four-bank parallel grants missing"', 'maximum_parallel == 2, "two-bank concurrent physical requests missing"')
s = s.replace('four-bank', 'two-bank').replace('four simultaneous bank grants', 'two simultaneous physical bank requests')
p.write_text(s)
print('Adapted shared cache and regression for two physical banks')
