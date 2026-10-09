set folder [file dirname [file normalize [info script]]]
set log [open [file join $folder gtk_selfcheck.log] w]
set status [catch {
    set names [gtkwave::getDisplayedSignals]
    set normalized [list]
    foreach name $names {lappend normalized [regsub {\[[0-9]+:[0-9]+\]$} $name {}]}
    set expected [list {soc_wires.clk} {soc_wires.rst_n_in} {soc_wires.rst_n} {soc_wires.imem_re} {soc_wires.imem_addr} {soc_wires.imem_rdata} {soc_wires.load_req} {soc_wires.load_complete} {soc_wires.load_error} {soc_wires.uart_tx} {soc_wires.uart_rx} {soc_wires.io_mem_req} {soc_wires.io_mem_we} {soc_wires.io_mem_gnt} {soc_wires.io_mem_error} {soc_wires.io_mem_addr} {soc_wires.io_mem_be} {soc_wires.io_mem_wdata} {soc_wires.cnn_mmio_re} {soc_wires.cnn_mmio_we} {soc_wires.cnn_mmio_ready} {soc_wires.cnn_mmio_addr} {soc_wires.cnn_mmio_wdata} {soc_wires.cnn_mmio_rdata} {soc_wires.mem_read} {soc_wires.mem_write} {soc_wires.mem_ready} {soc_wires.mem_addr} {soc_wires.mem_wdata} {soc_wires.mem_rdata} {soc_wires.dmem_re} {soc_wires.dmem_we} {soc_wires.dmem_wstrb} {soc_wires.dmem_addr} {soc_wires.dmem_wdata} {soc_wires.dmem_rdata}]
    if {$normalized ne $expected} {error "Signal list/order mismatch"}
    puts $log "COUNT=[llength $names]"
    puts $log "DUMP=[gtkwave::getDumpFileName]"
    puts $log "VIEW_START=[gtkwave::getWindowStartTime]"
    foreach {t value write} {313280000 00000005 0 313300000 A5A505A5 1} {
        gtkwave::setMarker $t
        set actual [gtkwave::getTraceValueAtMarkerFromName {soc_wires.mem_wdata[31:0]}]
        set enabled [gtkwave::getTraceValueAtMarkerFromName soc_wires.mem_write]
        if {$actual ne $value || $enabled ne $write} {error "Unexpected waveform value at $t: $actual / $enabled"}
        puts $log "SAMPLE=$t $actual $enabled"
    }
    puts $log "PASS portable GTKWave loaded 36 ordered signals and verified real waveform values"
} message]
if {$status} {puts $log "FAIL $message"}
close $log
gtkwave::/File/Quit
