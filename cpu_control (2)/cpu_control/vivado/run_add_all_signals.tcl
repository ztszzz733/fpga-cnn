# Vivado GUI script: compile the real Control + production Datapath, run ADD,
# and place the documented ADD-flow signals into grouped waveform sections.
# No Python is used.

set script_dir [file dirname [file normalize [info script]]]
set root_dir [file normalize [file join $script_dir ".."]]
set project_dir [file normalize [file join $root_dir "build" "vivado_add_all_signals"]]

if {[llength $argv] >= 1 && [lindex $argv 0] ne ""} {
    set fpga_part [lindex $argv 0]
} else {
    # This part is used only to create the behavioral-simulation project.
    # Pass the actual board part as the first Tcl argument when known.
    set fpga_part "xc7a35tcpg236-1"
}

create_project -force add_all_signals $project_dir -part $fpga_part
set_property target_language Verilog [current_project]
set_property simulator_language Mixed [current_project]

set design_sources [list \
    "partners/datapath/delivery/rtl/common/cpu_control_pkg.sv" \
    "rtl/cpu_control/main_decoder.sv" \
    "rtl/cpu_control/alu_decoder.sv" \
    "rtl/cpu_control/hazard_unit.sv" \
    "rtl/cpu_control/branch_control.sv" \
    "rtl/cpu_control/pipeline_control.sv" \
    "rtl/cpu_control/cpu_control.sv" \
    "partners/datapath/delivery/rtl/cpu_datapath/alu.sv" \
    "partners/datapath/delivery/rtl/cpu_datapath/imm_gen.sv" \
    "partners/datapath/delivery/rtl/cpu_datapath/pc.sv" \
    "partners/datapath/delivery/rtl/cpu_datapath/regfile.sv" \
    "partners/datapath/delivery/rtl/cpu_datapath/if_id_reg.sv" \
    "partners/datapath/delivery/rtl/cpu_datapath/id_ex_reg.sv" \
    "partners/datapath/delivery/rtl/cpu_datapath/ex_mem_reg.sv" \
    "partners/datapath/delivery/rtl/cpu_datapath/mem_wb_reg.sv" \
    "partners/datapath/delivery/rtl/cpu_datapath/address_decoder.sv" \
    "partners/datapath/delivery/rtl/cpu_datapath/lsu.sv" \
    "partners/datapath/delivery/rtl/cpu_datapath/fetch_adapter.sv" \
    "partners/datapath/delivery/rtl/cpu_datapath/cpu_datapath.sv" \
    "partners/datapath/delivery/rtl/soc_memory/imem_rom.sv" \
    "partners/datapath/delivery/rtl/soc_memory/data_sram_tdp.sv" \
    "partners/datapath/delivery/rtl/soc_memory/sram_b_arbiter.sv" \
    "partners/datapath/delivery/rtl/soc_memory/cnn_mmio_regs.sv" \
    "partners/datapath/delivery/rtl/soc_memory/datapath_memory_subsystem.sv" \
    "partners/datapath/delivery/rtl/soc_memory/face_soc_cpu_memory_top.sv"]

foreach relative_path $design_sources {
    set absolute_path [file normalize [file join $root_dir $relative_path]]
    add_files -fileset sources_1 -norecurse $absolute_path
    set_property file_type SystemVerilog [get_files $absolute_path]
}

set tb_path [file normalize [file join $root_dir "tb/integration/tb_add_vivado.v"]]
add_files -fileset sim_1 -norecurse $tb_path
set_property file_type Verilog [get_files $tb_path]
set_property top tb_add_vivado [get_filesets sim_1]
set_property top_lib xil_defaultlib [get_filesets sim_1]
set_property xsim.simulate.runtime 0ns [get_filesets sim_1]
update_compile_order -fileset sources_1
update_compile_order -fileset sim_1

launch_simulation

proc add_signal_group {title paths} {
    add_wave -divider $title
    foreach path $paths {
        set objects [get_objects -quiet $path]
        if {[llength $objects] > 0} {
            add_wave -noupdate $objects
        } else {
            puts "WARNING: waveform object not found: $path"
        }
    }
}

set tb "/tb_add_vivado"
set dp "$tb/dut/u_cpu_datapath"
set ctl "$tb/dut/u_control"

add_signal_group "00 Clock and stage valid" [list \
    "$tb/clk" "$tb/rst_n" "$dp/valid_d" "$dp/valid_e" \
    "$dp/valid_m" "$dp/valid_w" "$tb/rf_writes"]

add_signal_group "01 IF fetch and IF_ID" [list \
    "$dp/pc_q" "$dp/next_pc" "$dp/pc4_seq" "$dp/pc_sel" "$dp/pc_en" \
    "$dp/imem_addr" "$dp/imem_re" "$dp/imem_rdata" "$dp/fetch_valid" \
    "$dp/fetch_instr" "$dp/fetch_pc" "$dp/fetch_pc4" \
    "$dp/if_id_en" "$dp/if_id_flush"]

add_signal_group "02 ID decode and ID_EX input" [list \
    "$dp/instr_d" "$dp/pc_d" "$dp/pc4_d" "$dp/rs1_d" "$dp/rs2_d" \
    "$dp/rd_d" "$dp/rd1_d" "$dp/rd2_d" "$dp/imm_d" \
    "$dp/uses_rs1_d" "$dp/uses_rs2_d" "$ctl/legal_main" "$ctl/legal_alu" \
    "$dp/alu_ctrl" "$dp/alu_src_a_sel" "$dp/alu_src_b_sel" \
    "$dp/regwrite_d" "$dp/memread_d" "$dp/memwrite_d" "$dp/wb_sel_d" \
    "$dp/branch_type_d" "$dp/jump_d" "$dp/imm_type_d" "$dp/id_ex_flush"]

add_signal_group "03 Pipeline hazard and forwarding" [list \
    "$ctl/load_use" "$ctl/operand_unready" "$dp/fwd_a" "$dp/fwd_b" \
    "$dp/fwd_store" "$ctl/redirect" "$dp/pc_sel" "$dp/pc_en" \
    "$dp/if_id_en" "$dp/if_id_flush" "$dp/id_ex_flush"]

add_signal_group "04 EX execute and EX_MEM input" [list \
    "$dp/valid_e" "$dp/pc_e" "$dp/pc4_e" "$dp/rs1_e" "$dp/rs2_e" \
    "$dp/rd_e" "$dp/rd1_e" "$dp/rd2_e" "$dp/uses_rs1_e" "$dp/uses_rs2_e" \
    "$dp/alu_ctrl_e" "$dp/alu_src_a_sel_e" "$dp/alu_src_b_sel_e" \
    "$dp/regwrite_e" "$dp/memread_e" "$dp/memwrite_e" "$dp/wb_sel_e" \
    "$dp/branch_type_e" "$dp/jump_e" "$dp/fwd_a" "$dp/fwd_b" "$dp/fwd_store" \
    "$dp/src1_fwd_e" "$dp/src2_fwd_e" "$dp/store_data_fwd_e" \
    "$dp/alu_a_e" "$dp/alu_b_e" "$dp/alu_result_e" \
    "$dp/cmp_eq_e" "$dp/cmp_lt_e" "$dp/cmp_ltu_e" "$ctl/redirect" \
    "$dp/branch_target" "$dp/jalr_target"]

add_signal_group "05 MEM memory path and MEM_WB input" [list \
    "$dp/valid_m" "$dp/alu_result_m" "$dp/write_data_m" "$dp/rd_m" \
    "$dp/regwrite_m" "$dp/memread_m" "$dp/memwrite_m" "$dp/wb_sel_m" \
    "$dp/mem_forward_m" "$dp/dmem_addr" "$dp/dmem_wdata" "$dp/dmem_wstrb" \
    "$dp/dmem_re" "$dp/dmem_we" "$dp/dmem_rdata" "$dp/mmio_addr" \
    "$dp/mmio_wdata" "$dp/mmio_re" "$dp/mmio_we" "$dp/mmio_rdata" \
    "$dp/mmio_ready" "$dp/read_data_m"]

add_signal_group "06 WB writeback and register commit" [list \
    "$dp/valid_w" "$dp/read_data_w" "$dp/alu_result_w" "$dp/pc4_w" \
    "$dp/wb_sel_w" "$dp/wb_data_w" "$dp/rd_w" "$dp/regwrite_w" \
    "$dp/rf_we" "$tb/x1_value" "$tb/x2_value" "$tb/x6_value" "$tb/rf_writes"]

update_wave_config
set wave_path [file normalize [file join $project_dir "add_all_signals.wcfg"]]
save_wave_config $wave_path
run all
wave zoom full
puts "ADD waveform configuration: $wave_path"
puts "Expected result: PASS: Vivado Verilog testbench + real Control + production Datapath ADD"
