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
| 4 | 5 mm LEDs: 2 green, 2 yellow (or 1 yellow + 1 orange), 1 red, 1 blue or white | 1 assorted pack | "5mm LED assorted kit" | score bar, decision, ALARM, heartbeat |
| 5 | Resistors 330 ohm (220-470 ohm also fine) | 6+ | "330 ohm resistor" or a resistor kit | one per LED (protects the FPGA pin) |
| 6 | **Active** buzzer **module** (3-pin: VCC, GND, I/O; works at 3.3 V) | 1 | "active buzzer module 3.3V 5V" | beeps on ALARM. Must be *active* (beeps by itself) and a *module* (has a transistor) |
| 7 | Tactile push button 6x6 mm (4 legs) | 2 | "6x6 tactile push button" | "patient presses the button" / jump to seizure |
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
| A1 | H12 | 330 ohm -> green LED 1 (score bar, low) -> GND |
| A2 | E10 | 330 ohm -> green LED 2 (score bar, mid) -> GND |
| A3 | D10 | 330 ohm -> yellow LED (score bar, high) -> GND |
| A4 | C11 | 330 ohm -> orange/yellow LED (**DECISION**: this second looks like a seizure) -> GND |
| B1 | B10 | 330 ohm -> **red LED (ALARM)** -> GND |
| B2 | E12 | buzzer module **I/O** pin (buzzer VCC -> 3.3 V, buzzer GND -> GND) |
| B3 | D11 | 330 ohm -> blue/white LED (**heartbeat**: blinks once per second processed by the FPGA) -> GND |
| B4 | B11 | push button -> other leg of the button to GND (the FPGA pulls this pin up; pressing = 0) |
| GND | - | breadboard blue (-) rail; every LED's short leg and the button go here |
| 3.3 V | - | buzzer module VCC only |

LED direction: the **long leg** (+) goes towards the resistor and the FPGA pin, the **short leg** (-) to GND. If
an LED stays dark in the dashboard's "LED walk test", turn it around.

The dashboard has an **LED walk test** that lights A1, A2, A3, A4, B1, B2, B3 one after the other, so you can check
every wire before the demo. Start Demo 2 with `sudo bash demo2_components.sh` (see `DEMO.md`, section 2).
