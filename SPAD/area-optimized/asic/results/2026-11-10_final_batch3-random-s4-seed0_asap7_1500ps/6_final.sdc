###############################################################################
# Created by write_sdc
###############################################################################
current_design photon_core
###############################################################################
# Timing Constraints
###############################################################################
create_clock -name core_clock -period 1500.0000 [get_ports {clk}]
set_propagated_clock [get_clocks {core_clock}]
create_clock -name vclk_core_clock -period 1500.0000 
set_input_delay 300.0000 -clock [get_clocks {vclk_core_clock}] -add_delay [get_ports {arrival[0]}]
set_input_delay 300.0000 -clock [get_clocks {vclk_core_clock}] -add_delay [get_ports {arrival[1]}]
set_input_delay 300.0000 -clock [get_clocks {vclk_core_clock}] -add_delay [get_ports {arrival[2]}]
set_input_delay 300.0000 -clock [get_clocks {vclk_core_clock}] -add_delay [get_ports {arrival[3]}]
set_input_delay 300.0000 -clock [get_clocks {vclk_core_clock}] -add_delay [get_ports {arrival[4]}]
set_input_delay 300.0000 -clock [get_clocks {vclk_core_clock}] -add_delay [get_ports {arrival[5]}]
set_input_delay 300.0000 -clock [get_clocks {vclk_core_clock}] -add_delay [get_ports {arrival[6]}]
set_input_delay 300.0000 -clock [get_clocks {vclk_core_clock}] -add_delay [get_ports {arrival[7]}]
set_input_delay 300.0000 -clock [get_clocks {vclk_core_clock}] -add_delay [get_ports {arrival[8]}]
set_input_delay 300.0000 -clock [get_clocks {vclk_core_clock}] -add_delay [get_ports {arrival[9]}]
set_input_delay 300.0000 -clock [get_clocks {vclk_core_clock}] -add_delay [get_ports {rst}]
set_input_delay 300.0000 -clock [get_clocks {vclk_core_clock}] -add_delay [get_ports {valid}]
set_output_delay 300.0000 -clock [get_clocks {vclk_core_clock}] -add_delay [get_ports {candidate[0]}]
set_output_delay 300.0000 -clock [get_clocks {vclk_core_clock}] -add_delay [get_ports {candidate[1]}]
set_output_delay 300.0000 -clock [get_clocks {vclk_core_clock}] -add_delay [get_ports {candidate[2]}]
set_output_delay 300.0000 -clock [get_clocks {vclk_core_clock}] -add_delay [get_ports {candidate[3]}]
set_output_delay 300.0000 -clock [get_clocks {vclk_core_clock}] -add_delay [get_ports {candidate[4]}]
set_output_delay 300.0000 -clock [get_clocks {vclk_core_clock}] -add_delay [get_ports {candidate[5]}]
set_output_delay 300.0000 -clock [get_clocks {vclk_core_clock}] -add_delay [get_ports {candidate[6]}]
set_output_delay 300.0000 -clock [get_clocks {vclk_core_clock}] -add_delay [get_ports {candidate[7]}]
set_output_delay 300.0000 -clock [get_clocks {vclk_core_clock}] -add_delay [get_ports {candidate[8]}]
set_output_delay 300.0000 -clock [get_clocks {vclk_core_clock}] -add_delay [get_ports {candidate[9]}]
###############################################################################
# Environment
###############################################################################
###############################################################################
# Design Rules
###############################################################################
