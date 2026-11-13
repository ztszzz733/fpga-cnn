source "top_milestones.tcl"
set shown [gtkwave::getDisplayedSignals]
set file [open "gtkwave_validation.log" w]
puts $file "DUMP=[gtkwave::getDumpFileName]"
puts $file "DISPLAYED=[llength $shown]"
foreach name {imem_addr dmem_addr cnn_mmio_addr cnn_valid cache_csr_addr M_AXI_GP0_AWVALID S_AXI_HP0_ARVALID} {
    if {![string match "*$name*" $shown]} {
        puts $file "FAIL missing $name"
        close $file
        gtkwave::/File/Quit
        return
    }
}
puts $file "PASS top CPU/CNN/storage/GP0/HP0 signals visible"
close $file
gtkwave::/File/Quit
