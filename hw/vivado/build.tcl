# build.tcl: bring-up design of the Zybo Z7-10 (T1.9, l10): PS7 + one AXI4-Lite register.
#
# The Vivado project is created by hand, from the Digilent board (Zybo Z7-10), and this script
# works inside it. Board files are not fetched here (Q-14 asks for the licence of those files).
#
#   vivado -mode batch -source hw/vivado/build.tcl -tclargs <path/to/project.xpr>
#   (or set SAAM_VIVADO_PROJECT instead of -tclargs)
#
# It builds the block design `bringup` (processing_system7 from the board preset, FCLK_CLK0 at
# 100 MHz, one `axil_reg_bringup` at 0x43C00000), runs implementation to the bitstream and writes
#   hw/build/bringup/bringup.xsa                       the hardware platform for Vitis
#   hw/reports/bringup-utilization.rpt, -timing.rpt    reports
#   hw/reports/bringup-environment.json                tool version, part, board: the answer to Q-14
# Directories can be moved with SAAM_HW_BUILD_DIR and SAAM_HW_REPORT_DIR. Apart from the Vivado
# project itself (the block design and the runs are written in it), nothing outside them is
# written, and no absolute path is recorded in them.
#
# Not the final design: no SHA-256 or FIR core here (T3.21 completes this file).
#
# Not run by the repository tests: they only check it with a mock interpreter (tests/scripts/
# test_bringup_config.py). The first real run is the evidence.

set part        xc7z010clg400-1
set board_stem  digilent.com:zybo-z7-10:
set design      bringup
set reg_cell    reg0
set reg_base    0x43C00000
set reg_range   4K

set script_dir [file dirname [file normalize [info script]]]
set hw_dir     [file normalize [file join $script_dir ..]]

proc setting {name fallback} {
  if {[info exists ::env($name)] && [string trim $::env($name)] ne ""} {
    return [string trim $::env($name)]
  }
  return $fallback
}

set build_dir  [file normalize [setting SAAM_HW_BUILD_DIR  [file join $hw_dir build $design]]]
set report_dir [file normalize [setting SAAM_HW_REPORT_DIR [file join $hw_dir reports]]]

# --- the project, created by hand with the board -------------------------------------------
set xpr ""
if {[info exists ::argv] && [llength $::argv] > 0} {
  set xpr [lindex $::argv 0]
}
set xpr [setting SAAM_VIVADO_PROJECT $xpr]
if {$xpr eq ""} {
  error "no project: give the .xpr created with the Zybo Z7-10 board as -tclargs <project.xpr> or in SAAM_VIVADO_PROJECT"
}
open_project $xpr

set project_part [get_property PART [current_project]]
if {$project_part ne $part} {
  error "the project targets '$project_part', the architecture asks for $part (xc7z010clg400-1)"
}
set board_part [get_property BOARD_PART [current_project]]
if {![string match "${board_stem}*" $board_part]} {
  error "the project has board part '$board_part': create it with the Digilent zybo-z7-10 board (zybo-z7-10 preset of the PS)"
}

file mkdir $build_dir
file mkdir $report_dir

# --- sources and block design ---------------------------------------------------------------
set rtl [file normalize [file join $hw_dir rtl axil_reg_bringup.vhd]]
add_files -norecurse $rtl
# Plain VHDL, not {VHDL 2008}: Vivado refuses a module reference whose top file is VHDL-2008
# (filemgmt 56-195, seen with 2025.2). The register uses no 2008 construct. The AXI wrappers of
# T3.20 that become module references need the same care.
update_compile_order -fileset sources_1

# A second run starts from a clean design.
if {[llength [get_bd_designs -quiet $design]] > 0} {
  catch {close_bd_design [get_bd_designs $design]}
}
if {[llength [get_files -quiet ${design}.bd]] > 0} {
  remove_files [get_files ${design}.bd]
}
create_bd_design $design

create_bd_cell -type ip -vlnv xilinx.com:ip:processing_system7 processing_system7_0
apply_bd_automation -rule xilinx.com:bd_rule:processing_system7 \
  -config {make_external "FIXED_IO, DDR" apply_board_preset "1" Master "Disable" Slave "Disable"} \
  [get_bd_cells processing_system7_0]
set_property -dict [list \
  CONFIG.PCW_USE_M_AXI_GP0 {1} \
  CONFIG.PCW_FPGA0_PERIPHERAL_FREQMHZ {100}] [get_bd_cells processing_system7_0]

create_bd_cell -type module -reference axil_reg_bringup $reg_cell
apply_bd_automation -rule xilinx.com:bd_rule:axi4 \
  -config [list Clk_master {Auto} Clk_slave {Auto} Clk_xbar {Auto} \
    Master {/processing_system7_0/M_AXI_GP0} Slave "/$reg_cell/s_axi" \
    ddr_seg {Auto} intc_ip {New AXI Interconnect} master_apm {0}] \
  [get_bd_intf_pins $reg_cell/s_axi]

# The application reads the register at this address (hw/ps_app/bringup/hello.c).
assign_bd_address
foreach segment [get_bd_addr_segs -of_objects [get_bd_addr_spaces processing_system7_0/Data]] {
  if {[string match "*${reg_cell}*" $segment]} {
    set_property offset $reg_base $segment
    set_property range  $reg_range $segment
  }
}

validate_bd_design
save_bd_design

# --- implementation to the bitstream --------------------------------------------------------
generate_target all [get_files ${design}.bd]
set wrapper [make_wrapper -fileset sources_1 -files [get_files ${design}.bd] -top]
add_files -norecurse -fileset sources_1 $wrapper
set_property top ${design}_wrapper [current_fileset]
update_compile_order -fileset sources_1

reset_run synth_1
reset_run impl_1
launch_runs impl_1 -to_step write_bitstream -jobs 4
wait_on_run impl_1
if {[get_property PROGRESS [get_runs impl_1]] ne "100%"} {
  error "the implementation did not finish: [get_property STATUS [get_runs impl_1]]"
}

open_run impl_1
report_utilization    -file [file join $report_dir bringup-utilization.rpt]
report_timing_summary -file [file join $report_dir bringup-timing.rpt]
write_hw_platform -fixed -include_bit -force [file join $build_dir bringup.xsa]

# --- the evidence for Q-14: what built it, on which part and board --------------------------
set fh [open [file join $report_dir bringup-environment.json] w]
puts $fh "{"
puts $fh "  \"vivado_version\": \"[version -short]\","
puts $fh "  \"part\": \"$project_part\","
puts $fh "  \"board_part\": \"$board_part\","
puts $fh "  \"register_base\": \"$reg_base\","
puts $fh "  \"fclk0_mhz\": 100"
puts $fh "}"
close $fh

close_project
