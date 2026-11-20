# Timing constraints for one photon-stream core. ASAP7 time unit: ps.
# Follows the ORFS ASAP7 example (designs/asap7/gcd): I/O timed against a virtual clock.
current_design photon_core

set clk_name core_clock
set clk_port_name clk
set clk_period 1500
set clk_io_pct 0.2

set clk_port [get_ports $clk_port_name]
create_clock -name $clk_name -period $clk_period $clk_port
set clk_io_name vclk_$clk_name
create_clock -name $clk_io_name -period $clk_period

# Photon arrival, valid and reset come from registers outside the core, and the result
# goes to registers outside it: 20% of the period on each side.
set non_clock_inputs [all_inputs -no_clocks]
set_input_delay [expr $clk_period * $clk_io_pct] -clock $clk_io_name $non_clock_inputs
set_output_delay [expr $clk_period * $clk_io_pct] -clock $clk_io_name [all_outputs]
