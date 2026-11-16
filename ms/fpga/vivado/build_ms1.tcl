# SeizeLUT-MS kit "ms1" on the Kria KV260 (MS_SPEC.md D-MS6 (a)): the FCCM SeizeLUT core, unchanged, plus the
# impairment emulator (ms_impair_axi) on the same AXI4-Lite bus. A SEPARATE bitstream: the FCCM kit
# (hw/kv260/) is only read, never written; every output goes to ms/fpga/build and ms/fpga/out.
#
#   vivado -mode batch -source ms/fpga/vivado/build_ms1.tcl -tclargs [-jobs 8] [-noboard]   (from the repo root)
#   or: bash ms/fpga/vivado/build_ms1.sh [-jobs 8]
#
# Same PS configuration as hw/kv260/vivado/build_kv260.tcl (M_AXI_HPM0_LPD, 32 bit, pl_clk0 100 MHz), with a
# 1-to-2 interconnect. Outputs: out/ms1.bit + out/ms1.hwh (PYNQ overlay), utilization/timing/power reports,
# build_summary.txt with the two register base addresses.

set script_dir [file dirname [file normalize [info script]]]
set ms_fpga [file normalize [file join $script_dir ..]]
set repo [file normalize [file join $ms_fpga .. ..]]
set fccm_rtl [file join $repo hw kv260 rtl]
set fccm_xdc [file join $repo hw kv260 vivado kv260_pmod.xdc]
set build_dir [file join $ms_fpga build]
set out_dir [file join $ms_fpga out]
set proj ms1_kv260
set bd ms1_bd
set part xck26-sfvc784-2LV-c
set jobs 4
set use_board 1
for {set i 0} {$i < [llength $argv]} {incr i} {
    set a [lindex $argv $i]
    if {$a eq "-jobs"} { incr i; set jobs [lindex $argv $i] }
    if {$a eq "-noboard"} { set use_board 0 }
}
file mkdir $out_dir
set summary [open [file join $out_dir build_summary.txt] w]
proc note {msg} { global summary; puts "MS1: $msg"; puts $summary $msg; flush $summary }
note "vivado_version=[version -short]"
proc latest_vlnv {name} {
    set defs [get_ipdefs -all "xilinx.com:ip:${name}:*"]
    if {[llength $defs] == 0} { error "IP xilinx.com:ip:${name} is not in this Vivado installation" }
    return [lindex [lsort -dictionary $defs] end]
}

set board ""
if {$use_board} {
    catch { set_param board.repoPaths [get_property LOCAL_ROOT_DIR [xhub::get_xstores xilinx_board_store]] }
    foreach pat {"*:kv260_som:*" "*:kv260:*"} {
        set b [get_board_parts -quiet -latest_file_version $pat]
        if {[llength $b] > 0} { set board [lindex $b 0]; break }
    }
}
note "board_part=[expr {$board eq "" ? "none" : $board}]"

file delete -force [file join $build_dir $proj]
create_project $proj [file join $build_dir $proj] -part $part -force
if {$board ne ""} { set_property board_part $board [current_project] }
set_property target_language Verilog [current_project]
add_files -norecurse [list [file join $fccm_rtl seizelut_axi.v] [file join $fccm_rtl lutnet_classifier.v] \
                           [file join $fccm_rtl seizelut_bist_rom.v] \
                           [file join $ms_fpga rtl ms_impair.v] [file join $ms_fpga rtl ms_impair_axi.v]]
# sine table of ms_impair ($readmemh "sin4096.hex"): added to the project so synthesis finds it by name
set sin [file join $ms_fpga rtl sin4096.hex]
add_files -norecurse $sin
set_property file_type {Memory File} [get_files $sin]
add_files -fileset constrs_1 -norecurse $fccm_xdc
update_compile_order -fileset sources_1

create_bd_design $bd
set ps [create_bd_cell -type ip -vlnv [latest_vlnv zynq_ultra_ps_e] zynq_ultra_ps_e_0]
if {$board ne ""} {
    if {[catch {apply_bd_automation -rule xilinx.com:bd_rule:zynq_ultra_ps_e -config {apply_board_preset "1"} $ps} err]} {
        note "WARNING board preset not applied: $err"
    }
}
set_property -dict [list CONFIG.PSU__USE__M_AXI_GP0 {0} CONFIG.PSU__USE__M_AXI_GP1 {0} CONFIG.PSU__USE__M_AXI_GP2 {1} \
    CONFIG.PSU__MAXIGP2__DATA_WIDTH {32} CONFIG.PSU__FPGA_PL0_ENABLE {1} \
    CONFIG.PSU__CRL_APB__PL0_REF_CTRL__FREQMHZ {100}] $ps
set rst [create_bd_cell -type ip -vlnv [latest_vlnv proc_sys_reset] rst_pl0_100M]
set ic [create_bd_cell -type ip -vlnv [latest_vlnv smartconnect] axi_ic]
set_property -dict [list CONFIG.NUM_SI {1} CONFIG.NUM_MI {2}] $ic
set core [create_bd_cell -type module -reference seizelut_axi seizelut_0]
set imp [create_bd_cell -type module -reference ms_impair_axi ms_impair_0]
create_bd_port -dir O -from 6 -to 0 pmod_out
create_bd_port -dir I pmod_btn
connect_bd_net [get_bd_ports pmod_out] [get_bd_pins $core/pmod_out]
connect_bd_net [get_bd_ports pmod_btn] [get_bd_pins $core/pmod_btn]
connect_bd_net [get_bd_pins $ps/pl_clk0] [get_bd_pins $ps/maxihpm0_lpd_aclk] [get_bd_pins $rst/slowest_sync_clk] \
               [get_bd_pins $ic/aclk] [get_bd_pins $core/s_axi_aclk] [get_bd_pins $imp/s_axi_aclk]
connect_bd_net [get_bd_pins $rst/peripheral_aresetn] [get_bd_pins $ic/aresetn] [get_bd_pins $core/s_axi_aresetn] \
               [get_bd_pins $imp/s_axi_aresetn]
connect_bd_net [get_bd_pins $ps/pl_resetn0] [get_bd_pins $rst/ext_reset_in]
connect_bd_intf_net [get_bd_intf_pins $ps/M_AXI_HPM0_LPD] [get_bd_intf_pins $ic/S00_AXI]
connect_bd_intf_net [get_bd_intf_pins $ic/M00_AXI] [get_bd_intf_pins $core/s_axi]
connect_bd_intf_net [get_bd_intf_pins $ic/M01_AXI] [get_bd_intf_pins $imp/s_axi]
assign_bd_address
foreach seg [get_bd_addr_segs -quiet -of_objects [get_bd_addr_spaces $ps/Data]] {
    note "address [get_property NAME $seg] offset=[get_property OFFSET $seg] range=[get_property RANGE $seg]"
}
validate_bd_design
save_bd_design

set bd_file [get_files ${bd}.bd]
set_property synth_checkpoint_mode None $bd_file
generate_target all $bd_file
add_files -norecurse [make_wrapper -files $bd_file -top]
set_property top ${bd}_wrapper [current_fileset]
update_compile_order -fileset sources_1
launch_runs synth_1 -jobs $jobs
wait_on_run synth_1
if {[get_property PROGRESS [get_runs synth_1]] ne "100%"} { note "ERROR synthesis failed"; close $summary; error "synthesis failed" }
launch_runs impl_1 -to_step write_bitstream -jobs $jobs
wait_on_run impl_1
if {[get_property PROGRESS [get_runs impl_1]] ne "100%"} { note "ERROR implementation failed"; close $summary; error "implementation failed" }

open_run impl_1
report_utilization -file [file join $out_dir utilization.rpt]
report_utilization -hierarchical -file [file join $out_dir utilization_hier.rpt]
report_timing_summary -max_paths 10 -file [file join $out_dir timing_summary.rpt]
report_power -hierarchical_depth 6 -file [file join $out_dir power_hier.rpt]
set wns [get_property SLACK [get_timing_paths -max_paths 1 -nworst 1 -setup]]
set whs [get_property SLACK [get_timing_paths -max_paths 1 -nworst 1 -hold]]
note "wns_ns=$wns whs_ns=$whs"
if {$wns < 0 || $whs < 0} { note "WARNING timing not met" } else { note "timing_met=1" }
set rom [get_cells -hier -quiet -filter {NAME =~ *ms_impair_0*sin_rom* && PRIMITIVE_GROUP == BLOCKRAM}]
note "ms_impair_sine_rom_bram_cells=[llength $rom]"

set proj_dir [file join $build_dir $proj]
set bit [glob -nocomplain [file join $proj_dir ${proj}.runs impl_1 ${bd}_wrapper.bit]]
set hwh [glob -nocomplain [file join $proj_dir ${proj}.gen sources_1 bd $bd hw_handoff ${bd}.hwh] \
                          [file join $proj_dir ${proj}.srcs sources_1 bd $bd hw_handoff ${bd}.hwh]]
if {[llength $bit] == 0 || [llength $hwh] == 0} { note "ERROR bitstream or hwh not found"; close $summary; error "no bitstream" }
file copy -force [lindex $bit 0] [file join $out_dir ms1.bit]
file copy -force [lindex $hwh 0] [file join $out_dir ms1.hwh]
note "bitstream=ms/fpga/out/ms1.bit hwh=ms/fpga/out/ms1.hwh"
note "done=1"
close $summary
