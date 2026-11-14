# SeizeLUT live demo 2: parts to order now (no soldering)

Demo 1 needs none of this: it uses the board's own LEDs (see `DEMO.md`). These parts are for Demo 2.

Everything plugs into the KV260's **PMOD connector** (the 2 x 6 socket on the carrier board) with jumper wires and a
breadboard. Your laptop shows the live dashboard in a browser; the board runs the detector and drives the LEDs,
buzzer and button.

## Shopping list (Amazon India / Robu.in / local electronics shop; all common, next-day in most cities)

| # | Item | Qty | Search for | Why |
|---|---|---|---|---|
| 1 | Breadboard, half size (400 points) | 1 | "400 point breadboard" | holds LEDs, resistors, button |
| 2 | Jumper wires male-to-male, 20 cm | 1 pack (20-40) | "male to male jumper wire 20cm" | PMOD socket to breadboard |
| 3 | Jumper wires female-to-male, 20 cm | 1 pack | "female to male jumper wire" | spare, in case your PMOD has pins instead of a socket |
| 4 | 5 mm **diffused** LEDs: 2 green, 1 yellow, 1 orange, 1 blue or white; plus one **10 mm red** LED for ALARM | assorted pack + spares | "5mm diffused LED", "10mm red LED" | score bar, decision, ALARM, heartbeat (diffused LEDs glow evenly) |
| 5 | Resistors: 220 ohm (red/green/yellow/orange LEDs), 100 ohm (blue or white LED), 1 kohm (transistor base) | 10 / 4 / 4, or a resistor kit | "resistor kit" | one per LED (limits the FPGA pin's current) |
| 6 | **Active** buzzer: a 3-pin **module** (VCC, GND, I/O; works at 3.3 V), or a plain 2-pin active buzzer (3 V-5 V) with the transistor below | 1 (+1 spare) | "active buzzer module 3.3V 5V" or "active buzzer 3V" | beeps on ALARM. Must be *active*: touched to a 3 V coin cell it beeps by itself (a *passive* one only clicks) |
| 6b | Only for a plain 2-pin buzzer: NPN transistor BC547 (or 2N2222, S8050), 1 kohm resistor, diode 1N4148 | 2 each | "BC547 transistor", "1N4148" | the FPGA pin switches the transistor, which powers the buzzer |
| 7 | Tactile push button 12x12 mm with a round cap (6x6 mm also works) | 2 | "12x12 tactile switch with cap" | the patient button: marks the moment, starts playback |
| 8 | Ethernet cable Cat6, 1-2 m | 1 | "cat6 ethernet cable 1.5m" | laptop <-> KV260, no Wi-Fi needed |
| 9 | USB to Ethernet adapter (USB-A or USB-C, gigabit) | 1 | "usb to ethernet adapter gigabit" | **only if your laptop has no Ethernet port** |

Optional: a pocket Wi-Fi router (for example TP-Link TL-WR802N) if you prefer Wi-Fi on the laptop; the board then
connects to it by Ethernet. Not needed with the direct cable.

## Wiring (do it with the board powered OFF)

Find **pin 1** of the PMOD connector (small triangle or "1" on the board). The connector has two rows of six:

```
            row with pin 1 ->   [A1] [A2] [A3] [A4] [GND] [3.3V]
            other row      ->   [B1] [B2] [B3] [B4] [GND] [3.3V]
```

| PMOD position | FPGA pin | Connect to |
|---|---|---|
| A1 | H12 | 220 ohm -> green LED 1 (score bar, low) -> GND |
| A2 | E10 | 220 ohm -> green LED 2 (score bar, mid) -> GND |
| A3 | D10 | 220 ohm -> yellow LED (score bar, high) -> GND |
| A4 | C11 | 220 ohm -> orange LED (**DECISION**: this second looks like a seizure) -> GND |
| B1 | B10 | 220 ohm -> **10 mm red LED (ALARM)** -> GND |
| B2 | E12 | buzzer module **I/O** pin (buzzer VCC -> 3.3 V, buzzer GND -> GND); for a plain 2-pin buzzer see below |
| B3 | D11 | 100 ohm -> blue/white LED (**heartbeat**: blinks once per second processed by the FPGA) -> GND |
| B4 | B11 | push button -> other leg of the button to GND (the FPGA pulls this pin up; pressing = 0) |
| GND | - | breadboard blue (-) rail; every LED's short leg and the button go here |
| 3.3 V | - | buzzer module VCC only |

**Plain 2-pin active buzzer** (no module): B2 -> 1 kohm -> transistor base; emitter -> GND; collector -> buzzer
short leg (-); buzzer long leg (+) -> PMOD 3.3 V. Optional: 1N4148 across the buzzer, striped end to 3.3 V. A BC547 seen
from its flat face has the legs C, B, E from left to right (a 2N2222 or S8050 is E, B, C: check the shop's pinout).
The buzzer sounds when B2 is high, the design's default (no `--buzzer-active-low`).

LED direction: the **long leg** (+) goes towards the resistor and the FPGA pin, the **short leg** (-) to GND. If
an LED stays dark in the dashboard's "LED walk test", turn it around.

The dashboard has an **LED walk test** that lights A1, A2, A3, A4, B1, B2, B3 one after the other, so you can check
every wire before the demo. Start Demo 2 with `sudo bash demo2_components.sh` (see `DEMO.md`, section 2).
