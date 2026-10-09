open_vcd {add_vivado_all_signals.vcd}
log_vcd [get_objects -r /tb_add_vivado/*]
run all
close_vcd
quit
