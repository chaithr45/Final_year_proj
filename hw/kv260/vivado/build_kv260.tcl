# SeizeLUT on the Kria KV260: block design, bitstream, PYNQ hardware handoff and reports, in one batch run.
#
#   vivado -mode batch -source vivado/build_kv260.tcl                (from the kit folder)
#   vivado -mode batch -source vivado/build_kv260.tcl -tclargs -jobs 8 -noboard -nooc -nobaselines
#
# Options: -jobs N (parallel jobs, default 4), -noboard (use the bare XCK26 part, no KV260 board files),
#          -nooc (skip the out-of-context runs), -nobaselines (out-of-context run of our classifier only,
#          not of the TreeLUT and logic-gate-network baselines in rtl/baselines/).
# Outputs in out/: seizelut.bit + seizelut.hwh (PYNQ overlay, same base name), seizelut.xsa,
#   utilization*.rpt, timing_summary.rpt, power*.rpt, ooc_classifier_*.rpt, build_summary.txt, build.log copy.
# Tested design choices follow the official Kria-PYNQ KV260 base overlay: Zynq UltraScale+ PS with
# M_AXI_HPM0_LPD (32 bit) at 100 MHz (pl_clk0), proc_sys_reset, interconnect, AXI4-Lite slave at 0x8000_0000.

set script_dir [file dirname [file normalize [info script]]]
set kit [file normalize [file join $script_dir ..]]
set rtl_dir [file join $kit rtl]
set build_dir [file join $kit build]
set out_dir [file join $kit out]
set proj seizelut_kv260
set bd seizelut_bd
set part xck26-sfvc784-2LV-c
set jobs 4
set use_board 1
set run_ooc 1
set run_baselines 1
for {set i 0} {$i < [llength $argv]} {incr i} {
    set a [lindex $argv $i]
    if {$a eq "-jobs"} { incr i; set jobs [lindex $argv $i] }
    if {$a eq "-noboard"} { set use_board 0 }
    if {$a eq "-nooc"} { set run_ooc 0 }
    if {$a eq "-nobaselines"} { set run_baselines 0 }
}
file mkdir $out_dir
set summary [open [file join $out_dir build_summary.txt] w]
proc note {msg} {
    global summary
    puts "SEIZELUT: $msg"
    puts $summary $msg
    flush $summary
}
note "vivado_version=[version -short]"
note "part=$part jobs=$jobs"

proc latest_vlnv {name} {
    set defs [get_ipdefs -all "xilinx.com:ip:${name}:*"]
    if {[llength $defs] == 0} { error "IP xilinx.com:ip:${name} is not in this Vivado installation" }
    return [lindex [lsort -dictionary $defs] end]
}

# ---------------------------------------------------------------- board files (optional)
set board ""
if {$use_board} {
    catch { set_param board.repoPaths [get_property LOCAL_ROOT_DIR [xhub::get_xstores xilinx_board_store]] }
    foreach pat {"*:kv260_som:*" "*:kv260:*"} {
        set b [get_board_parts -quiet -latest_file_version $pat]
        if {[llength $b] > 0} { set board [lindex $b 0]; break }
    }
    if {$board eq ""} {
        note "KV260 board files not installed; trying the Xilinx board store (needs internet)"
        if {[catch {
            xhub::refresh_catalog [xhub::get_xstores xilinx_board_store]
            set items [xhub::get_xitems -quiet "*kv260_som*"]
            if {[llength $items] > 0} { xhub::install [lindex $items 0] }
            set_param board.repoPaths [get_property LOCAL_ROOT_DIR [xhub::get_xstores xilinx_board_store]]
            set b [get_board_parts -quiet -latest_file_version "*:kv260_som:*"]
            if {[llength $b] > 0} { set board [lindex $b 0] }
        } err]} { note "board store not available: $err" }
    }
}
if {$board eq ""} { note "board_part=none (bare part; PS defaults, PL interface configured explicitly)" } else { note "board_part=$board" }

# ---------------------------------------------------------------- project
file delete -force [file join $build_dir $proj]
create_project $proj [file join $build_dir $proj] -part $part -force
if {$board ne ""} { set_property board_part $board [current_project] }
set_property target_language Verilog [current_project]
add_files -norecurse [list [file join $rtl_dir seizelut_axi.v] [file join $rtl_dir lutnet_classifier.v] \
                           [file join $rtl_dir seizelut_bist_rom.v]]
set_property top seizelut_axi [current_fileset]
update_compile_order -fileset sources_1

# ---------------------------------------------------------------- block design
create_bd_design $bd
set ps [create_bd_cell -type ip -vlnv [latest_vlnv zynq_ultra_ps_e] zynq_ultra_ps_e_0]
if {$board ne ""} {
    if {[catch {apply_bd_automation -rule xilinx.com:bd_rule:zynq_ultra_ps_e -config {apply_board_preset "1"} $ps} err]} {
        note "WARNING board preset not applied: $err"
    }
}
set_property -dict [list \
    CONFIG.PSU__USE__M_AXI_GP0 {0} \
    CONFIG.PSU__USE__M_AXI_GP1 {0} \
    CONFIG.PSU__USE__M_AXI_GP2 {1} \
    CONFIG.PSU__MAXIGP2__DATA_WIDTH {32} \
    CONFIG.PSU__FPGA_PL0_ENABLE {1} \
    CONFIG.PSU__CRL_APB__PL0_REF_CTRL__FREQMHZ {100} \
] $ps
note "zynq_ultra_ps_e=[get_property VLNV $ps]"

set rst [create_bd_cell -type ip -vlnv [latest_vlnv proc_sys_reset] rst_pl0_100M]
set ic_name ""
if {[catch {
    set ic [create_bd_cell -type ip -vlnv [latest_vlnv smartconnect] axi_ic]
    set_property -dict [list CONFIG.NUM_SI {1} CONFIG.NUM_MI {1}] $ic
    set ic_name smartconnect
} err]} {
    note "smartconnect not available ($err); using axi_interconnect"
    set ic [create_bd_cell -type ip -vlnv [latest_vlnv axi_interconnect] axi_ic]
    set_property -dict [list CONFIG.NUM_SI {1} CONFIG.NUM_MI {1}] $ic
    set ic_name axi_interconnect
}
note "interconnect=$ic_name"
set core [create_bd_cell -type module -reference seizelut_axi seizelut_0]

# clocks and resets
set clk_pins [list [get_bd_pins $ps/pl_clk0] [get_bd_pins $ps/maxihpm0_lpd_aclk] \
                   [get_bd_pins $rst/slowest_sync_clk] [get_bd_pins $core/s_axi_aclk]]
if {$ic_name eq "smartconnect"} {
    lappend clk_pins [get_bd_pins $ic/aclk]
    connect_bd_net {*}$clk_pins
    connect_bd_net [get_bd_pins $rst/peripheral_aresetn] [get_bd_pins $ic/aresetn] [get_bd_pins $core/s_axi_aresetn]
} else {
    lappend clk_pins [get_bd_pins $ic/ACLK] [get_bd_pins $ic/S00_ACLK] [get_bd_pins $ic/M00_ACLK]
    connect_bd_net {*}$clk_pins
    connect_bd_net [get_bd_pins $rst/peripheral_aresetn] [get_bd_pins $core/s_axi_aresetn] \
                   [get_bd_pins $ic/S00_ARESETN] [get_bd_pins $ic/M00_ARESETN]
    connect_bd_net [get_bd_pins $rst/interconnect_aresetn] [get_bd_pins $ic/ARESETN]
}
connect_bd_net [get_bd_pins $ps/pl_resetn0] [get_bd_pins $rst/ext_reset_in]
connect_bd_intf_net [get_bd_intf_pins $ps/M_AXI_HPM0_LPD] [get_bd_intf_pins $ic/S00_AXI]
connect_bd_intf_net [get_bd_intf_pins $ic/M00_AXI] [get_bd_intf_pins $core/s_axi]
assign_bd_address
foreach seg [get_bd_addr_segs -quiet -of_objects [get_bd_addr_spaces $ps/Data]] {
    note "address [get_property NAME $seg] offset=[get_property OFFSET $seg] range=[get_property RANGE $seg]"
}
validate_bd_design
save_bd_design

# ---------------------------------------------------------------- synthesis and implementation
set bd_file [get_files ${bd}.bd]
set_property synth_checkpoint_mode None $bd_file
generate_target all $bd_file
set wrapper [make_wrapper -files $bd_file -top]
add_files -norecurse $wrapper
set_property top ${bd}_wrapper [current_fileset]
update_compile_order -fileset sources_1

launch_runs synth_1 -jobs $jobs
wait_on_run synth_1
if {[get_property PROGRESS [get_runs synth_1]] ne "100%"} {
    note "ERROR synthesis failed: [get_property STATUS [get_runs synth_1]]"
    close $summary
    error "synthesis failed (see build/$proj/$proj.runs/synth_1/runme.log)"
}
launch_runs impl_1 -to_step write_bitstream -jobs $jobs
wait_on_run impl_1
if {[get_property PROGRESS [get_runs impl_1]] ne "100%"} {
    note "ERROR implementation failed: [get_property STATUS [get_runs impl_1]]"
    close $summary
    error "implementation failed (see build/$proj/$proj.runs/impl_1/runme.log)"
}

# ---------------------------------------------------------------- reports
open_run impl_1
report_utilization -file [file join $out_dir utilization.rpt]
report_utilization -hierarchical -file [file join $out_dir utilization_hier.rpt]
set cls [get_cells -hier -filter {NAME =~ */u_cls}]
set wrap [get_cells -hier -filter {NAME =~ */seizelut_0/inst || NAME =~ */seizelut_0}]
if {[llength $cls] > 0} { report_utilization -cells [lindex $cls 0] -file [file join $out_dir utilization_classifier.rpt] }
if {[llength $wrap] > 0} { report_utilization -cells [lindex $wrap 0] -file [file join $out_dir utilization_seizelut_core.rpt] }
report_timing_summary -max_paths 10 -file [file join $out_dir timing_summary.rpt]
report_power -file [file join $out_dir power.rpt]
report_power -hierarchical_depth 8 -file [file join $out_dir power_hier.rpt]
set wns [get_property SLACK [get_timing_paths -max_paths 1 -nworst 1 -setup]]
set whs [get_property SLACK [get_timing_paths -max_paths 1 -nworst 1 -hold]]
note "wns_ns=$wns"
note "whs_ns=$whs"
if {$wns < 0 || $whs < 0} { note "WARNING timing not met" } else { note "timing_met=1" }
if {[llength $cls] > 0} {
    set c [lindex $cls 0]
    note "classifier_lut_cells=[llength [get_cells -hier -filter "NAME =~ $c/* && PRIMITIVE_GROUP == LUT"]]"
    note "classifier_ff_cells=[llength [get_cells -hier -filter "NAME =~ $c/* && PRIMITIVE_GROUP == FLOP_LATCH"]]"
    note "classifier_carry_cells=[llength [get_cells -hier -filter "NAME =~ $c/* && PRIMITIVE_GROUP == CARRY"]]"
    note "classifier_dsp_cells=[llength [get_cells -hier -filter "NAME =~ $c/* && PRIMITIVE_GROUP == ARITHMETIC"]]"
    note "classifier_bram_cells=[llength [get_cells -hier -filter "NAME =~ $c/* && PRIMITIVE_GROUP == BLOCKRAM"]]"
}

# ---------------------------------------------------------------- outputs (PYNQ needs .bit and .hwh with the same base name)
set proj_dir [file join $build_dir $proj]
set bit [glob -nocomplain [file join $proj_dir ${proj}.runs impl_1 ${bd}_wrapper.bit]]
set hwh [glob -nocomplain [file join $proj_dir ${proj}.gen sources_1 bd $bd hw_handoff ${bd}.hwh] \
                          [file join $proj_dir ${proj}.srcs sources_1 bd $bd hw_handoff ${bd}.hwh]]
if {[llength $bit] == 0 || [llength $hwh] == 0} {
    note "ERROR bitstream or hwh not found"
    close $summary
    error "bitstream or hardware handoff not found"
}
file copy -force [lindex $bit 0] [file join $out_dir seizelut.bit]
file copy -force [lindex $hwh 0] [file join $out_dir seizelut.hwh]
file copy -force [file join $rtl_dir seizelut_regs.json] [file join $out_dir seizelut_regs.json]
if {[catch {write_hw_platform -fixed -include_bit -force [file join $out_dir seizelut.xsa]} err]} { note "xsa not written: $err" }
note "bitstream=out/seizelut.bit"
note "hwh=out/seizelut.hwh"
close_project

# ---------------------------------------------------------------- classifiers alone, out of context: utilisation and Fmax
# Same flow for our DWN classifier and, unless -nobaselines, the TreeLUT and logic-gate-network baselines
# (rtl/baselines/, generated from their frozen final models and checked bit-exact against them in simulation).
proc ooc_run {tag file top period} {
    global part out_dir
    create_project -in_memory -part $part
    read_verilog $file
    synth_design -top $top -part $part -mode out_of_context
    create_clock -period $period -name clk [get_ports clk]
    opt_design
    place_design
    phys_opt_design
    route_design
    report_utilization -file [file join $out_dir ooc_${tag}_utilization.rpt]
    report_timing_summary -file [file join $out_dir ooc_${tag}_timing.rpt]
    report_power -file [file join $out_dir ooc_${tag}_power.rpt]
    set w [get_property SLACK [get_timing_paths -max_paths 1 -nworst 1 -setup]]
    note "ooc_${tag}_period_ns=$period"
    note "ooc_${tag}_wns_ns=$w"
    note "ooc_${tag}_fmax_mhz=[format %.1f [expr {1000.0 / ($period - $w)}]]"
    close_project
}
if {$run_ooc} {
    ooc_run classifier [file join $rtl_dir lutnet_classifier.v] lutnet_classifier 2.5
    if {$run_baselines} {
        foreach {tag top} {treelut treelut_classifier lgn lgn_classifier} {
            set f [file join $rtl_dir baselines ${top}.v]
            if {[file exists $f]} {
                if {[catch {ooc_run $tag $f $top 2.5} err]} { note "WARNING out-of-context run of $tag failed: $err"; catch {close_project} }
            } else { note "baseline $f not found, skipped" }
        }
    }
}
note "done=1"
close $summary
puts "SEIZELUT: build finished; outputs in $out_dir"
