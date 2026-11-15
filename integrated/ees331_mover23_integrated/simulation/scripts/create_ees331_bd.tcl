# Usage: vivado -mode batch -source create_ees331_bd.tcl -tclargs ROOT OUT [BOARD_PS_TCL]
# Board source was audited: D:/ees331_ready contains PL JTAG-AXI, no PS7/DDR.
# This PS configuration follows the EES331 manual. PCB delay values still need
# hardware calibration or an authoritative EES331 PS preset; never use ZedBoard.
set root [file normalize [lindex $argv 0]]
set out [file normalize [lindex $argv 1]]
set preset [lindex $argv 2]
if {[file exists [file join $out ees331_ddr.xpr]]} {error "Output already contains a project: $out"}
set_param general.maxThreads 2
create_project ees331_ddr $out -part xc7z020clg484-1
set_property target_language Verilog [current_project]
set_property simulator_language Mixed [current_project]
create_bd_design ees331_ps_bd
set ps [create_bd_cell -type ip -vlnv xilinx.com:ip:processing_system7:5.5 ps7]
set_property -dict [list \
 CONFIG.PCW_USE_M_AXI_GP0 {1} \
 CONFIG.PCW_USE_S_AXI_HP0 {1} \
 CONFIG.PCW_S_AXI_HP0_DATA_WIDTH {64} \
 CONFIG.PCW_EN_CLK0_PORT {1} \
 CONFIG.PCW_EN_RST0_PORT {1} \
 CONFIG.PCW_FPGA0_PERIPHERAL_FREQMHZ {50.000000} \
 CONFIG.PCW_CRYSTAL_PERIPHERAL_FREQMHZ {33.333333} \
 CONFIG.PCW_UART1_PERIPHERAL_ENABLE {1} \
 CONFIG.PCW_UART1_UART1_IO {MIO 48 .. 49} \
 CONFIG.PCW_UART1_GRP_FULL_ENABLE {0} \
 CONFIG.PCW_UIPARAM_DDR_ENABLE {1} \
 CONFIG.PCW_UIPARAM_DDR_MEMORY_TYPE {DDR 3} \
 CONFIG.PCW_UIPARAM_DDR_PARTNO {MT41K256M16 RE-15E} \
 CONFIG.PCW_UIPARAM_DDR_BUS_WIDTH {32 Bit} \
 CONFIG.PCW_UIPARAM_DDR_FREQ_MHZ {533.333333} \
 CONFIG.PCW_UIPARAM_DDR_USE_INTERNAL_VREF {0} \
 CONFIG.PCW_UIPARAM_DDR_TRAIN_WRITE_LEVEL {1} \
 CONFIG.PCW_UIPARAM_DDR_TRAIN_READ_GATE {1} \
 CONFIG.PCW_UIPARAM_DDR_TRAIN_DATA_EYE {1} \
] $ps
# Optional board-owned file must set properties on $ps; not executed unless
# explicitly supplied as a build argument. The audited PL-only project is not it.
if {$preset ne ""} {source [file normalize $preset]}
foreach name {DDR FIXED_IO M_AXI_GP0 S_AXI_HP0} {
 make_bd_intf_pins_external [get_bd_intf_pins ps7/$name]
 set_property name $name [get_bd_intf_ports ${name}_0]
}
foreach name {FCLK_CLK0 FCLK_RESET0_N M_AXI_GP0_ACLK S_AXI_HP0_ACLK} {
 make_bd_pins_external [get_bd_pins ps7/$name]
 set_property name $name [get_bd_ports ${name}_0]
}
foreach name {RCOUNT WCOUNT RACOUNT WACOUNT RDISSUECAP1_EN WRISSUECAP1_EN} {
 make_bd_pins_external [get_bd_pins ps7/S_AXI_HP0_$name]
 set_property name S_AXI_HP0_$name [get_bd_ports S_AXI_HP0_${name}_0]
}
set_property CONFIG.FREQ_HZ 50000000 [get_bd_ports M_AXI_GP0_ACLK]
set_property CONFIG.FREQ_HZ 50000000 [get_bd_ports S_AXI_HP0_ACLK]
set_property CONFIG.ASSOCIATED_BUSIF M_AXI_GP0 [get_bd_ports M_AXI_GP0_ACLK]
set_property CONFIG.ASSOCIATED_BUSIF S_AXI_HP0 [get_bd_ports S_AXI_HP0_ACLK]
# Advertise external mailbox decoding; CNN/cache masters implement actual checks.
set gp_seg [get_bd_addr_segs -quiet M_AXI_GP0/Reg]
if {[llength $gp_seg]} {
 assign_bd_address -offset 0x40000000 -range 0x00001000 -target_address_space [get_bd_addr_spaces ps7/Data] $gp_seg
}
assign_bd_address
validate_bd_design
save_bd_design
set bd [get_files */ees331_ps_bd.bd]
generate_target all $bd
set wrapper [make_wrapper -files $bd -top]
add_files -norecurse $wrapper
set fp [open [file join $out ps7_properties.txt] w]
foreach prop [lsort [list_property $ps]] {
 if {[string match CONFIG.* $prop]} {puts $fp "$prop=[get_property $prop $ps]"}
}
close $fp
set fp [open [file join $out ps_bd_ports.tsv] w]
foreach p [get_bd_ports] {puts $fp "[get_property NAME $p]\t[get_property DIR $p]"}
close $fp
write_bd_tcl -force [file join $out recreate_ps_bd.tcl]
puts "EES331_PS_BD_COMPLETE $out"
exit 0
