# Requires a 100MHz clock named sys_clk; implementation uses sys_clk/4.
# These IO budgets are an explicit proposed contract for the external controller.
# Revise using its actual tCO/setup/hold and measured cable/PCB flight times.
create_generated_clock -name fx8_link_clk -source [get_ports -quiet {sys_clk clk}] -divide_by 4 \
    [get_pins -hier -regexp {.*u_link/divider_reg\[1\]/Q}]
create_generated_clock -name fx8_forward_clk -source [get_pins -hier -filter {NAME =~ *u_link/u_forward_clock/C}] \
    -divide_by 1 [get_ports fx8_clk]
# Return data and ready: total peer clock-to-out plus forward/return flight <=12ns,
# minimum >=1ns, referenced to the forwarded clock at this FPGA's output port.
set_input_delay -clock fx8_forward_clk -max 12.000 [get_ports {fx8_rx_data[*] fx8_rx_valid fx8_tx_ready}]
set_input_delay -clock fx8_forward_clk -min 1.000 [get_ports {fx8_rx_data[*] fx8_rx_valid fx8_tx_ready}]
# Peer needs <=6ns setup budget (including outbound skew), <=2ns hold budget.
set_output_delay -clock fx8_forward_clk -max 6.000 [get_ports {fx8_tx_data[*] fx8_tx_valid fx8_rx_ready}]
set_output_delay -clock fx8_forward_clk -min -2.000 [get_ports {fx8_tx_data[*] fx8_tx_valid fx8_rx_ready}]
# Reset asserts asynchronously and releases on a link rising edge; peer must
# synchronize release in its own logic. It is not a data bus timing endpoint.
set_false_path -to [get_ports fx8_reset_n]
# Gray-pointer CDC: constrain physical spread to <= one fast-clock period.
# Do not use blanket asynchronous clock groups, which would mask these bounds.
set_max_delay -datapath_only 10.000 -from [get_cells -hier -filter {NAME =~ *u_link/*_fifo/wr_gray_reg*}] -to [get_cells -hier -filter {NAME =~ *u_link/*_fifo/wr_gray_meta_reg*}]
set_bus_skew 10.000 -from [get_cells -hier -filter {NAME =~ *u_link/*_fifo/wr_gray_reg*}] -to [get_cells -hier -filter {NAME =~ *u_link/*_fifo/wr_gray_meta_reg*}]
set_max_delay -datapath_only 10.000 -from [get_cells -hier -filter {NAME =~ *u_link/*_fifo/rd_gray_reg*}] -to [get_cells -hier -filter {NAME =~ *u_link/*_fifo/rd_gray_meta_reg*}]
set_bus_skew 10.000 -from [get_cells -hier -filter {NAME =~ *u_link/*_fifo/rd_gray_reg*}] -to [get_cells -hier -filter {NAME =~ *u_link/*_fifo/rd_gray_meta_reg*}]
