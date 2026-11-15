These four files (inv.sch, inv.mag and the two transistor .mag cells) are copied unchanged from test 02 of
IIC-OSIC-TOOLS (https://github.com/iic-jku/IIC-OSIC-TOOLS, `_tests/02/`, commit f15ef6a),
Copyright 2024-2026 Harald Pretl, Johannes Kepler University, Department for Integrated Circuits,
licensed under the Apache License 2.0 (https://www.apache.org/licenses/LICENSE-2.0).
They are a known-good 5 V inverter (schematic and layout) used only to check that DRC (Magic) and LVS
(netgen, with xschem netlisting the schematic) work in your container: see ms/setup/check_tools.sh.
