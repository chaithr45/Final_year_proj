# SeizeLUT live demo: KV260 PMOD connector J2 (bank 45, 3.3 V). Pins as in the official Kria-PYNQ KV260 overlay.
# Row with pin 1: A1 A2 A3 A4 GND 3V3; other row: B1 B2 B3 B4 GND 3V3.
set_property PACKAGE_PIN H12 [get_ports {pmod_out[0]}] ;# A1  score bar low      (green LED)
set_property PACKAGE_PIN E10 [get_ports {pmod_out[1]}] ;# A2  score bar mid      (green LED)
set_property PACKAGE_PIN D10 [get_ports {pmod_out[2]}] ;# A3  score bar high     (yellow LED)
set_property PACKAGE_PIN C11 [get_ports {pmod_out[3]}] ;# A4  decision           (orange/yellow LED)
set_property PACKAGE_PIN B10 [get_ports {pmod_out[4]}] ;# B1  ALARM              (red LED)
set_property PACKAGE_PIN E12 [get_ports {pmod_out[5]}] ;# B2  buzzer module I/O
set_property PACKAGE_PIN D11 [get_ports {pmod_out[6]}] ;# B3  heartbeat          (blue/white LED)
set_property PACKAGE_PIN B11 [get_ports {pmod_btn}]    ;# B4  push button to GND
set_property IOSTANDARD LVCMOS33 [get_ports {pmod_out[*]}]
set_property IOSTANDARD LVCMOS33 [get_ports {pmod_btn}]
set_property DRIVE 8 [get_ports {pmod_out[*]}]
set_property SLEW SLOW [get_ports {pmod_out[*]}]
set_property PULLUP true [get_ports {pmod_btn}]
# LEDs, buzzer and a debounced button are asynchronous to the design clock
set_false_path -to [get_ports {pmod_out[*]}]
set_false_path -from [get_ports {pmod_btn}]
