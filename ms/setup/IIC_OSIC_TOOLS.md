# Installing IIC-OSIC-TOOLS (SKY130) for SeizeLUT-MS

IIC-OSIC-TOOLS is a Docker image from JKU Linz with the whole open-source analog flow in one place: Xschem
(schematics), ngspice (simulation), Magic and KLayout (layout, DRC, extraction), netgen (LVS), and the SKY130A
PDK. One image works on both of your machines: the ASUS (Windows, x86-64) and the MacBook (Apple Silicon is
supported natively since release 2025.01).

Everything below is from the project's README and KNOWN_ISSUES.md at commit `f15ef6a` (12 Nov 2026), latest
release **2026.10**. That release pins ngspice-47, Magic 8.3.685, netgen 1.5.324, KLayout 0.30.12 and open_pdks
`1689ac3f` for SKY130A.

**Pick one machine as the main one.** Both work. The README states no RAM requirement. Choose the machine with more
free RAM and at least 20 GB free disk, and tell me which one you picked. Docker on Apple Silicon runs the arm64 image
natively, so the MacBook is not at a disadvantage.

Our repository may be private. If so, `git clone` asks you to sign in to GitHub (on Windows the Git Credential
Manager opens a browser window). That is expected.

## What you need

- About **20 GB free disk**. The image is about 4 GB compressed and is extracted on your drive (README §1.3).
- Docker Desktop:
  - Windows: https://desktop.docker.com/win/main/amd64/Docker%20Desktop%20Installer.exe (uses WSL2)
  - Mac with Apple chip: https://desktop.docker.com/mac/main/arm64/Docker.dmg
- Git.
- A fast connection for the first start (it pulls the image).

## Windows (ASUS)

1. Install Docker Desktop and start it once (it sets up WSL2; a reboot may be needed). Update WSL so WSLg (the
   graphics layer) is current. In PowerShell, run `wsl --update`.
2. Get the start scripts. In PowerShell:
   ```
   cd $HOME
   git clone --depth=1 https://github.com/iic-jku/iic-osic-tools.git
   ```
3. Get our repository into the folder the container sees. The container mounts `%USERPROFILE%\eda\designs` as
   `/foss/designs`. In PowerShell:
   ```
   mkdir $HOME\eda\designs -Force
   cd $HOME\eda\designs
   git clone -b FPGA https://github.com/chaithr45/Final_year_proj.git
   ```
   (Our `ms/.gitattributes` keeps the scripts' Unix line endings even on Windows. If bash ever complains about
   `$'\r'`, clone the repository from inside the container instead, as in step 5.)
4. Start the container in browser (VNC) mode, the easiest mode:
   ```
   cd $HOME\iic-osic-tools
   .\start_vnc.bat
   ```
   The first start downloads the image, which takes a while. Then open **http://localhost/?password=abc123** in your browser
   (default password `abc123`; the script prints the exact URL).
5. In the desktop that opens, start a terminal and run the check:
   ```
   cd /foss/designs/Final_year_proj
   bash ms/setup/check_tools.sh
   ```

The faster alternative is X11 mode through WSLg: `.\start_x.bat`. Use it later if the browser desktop feels slow.

## macOS (MacBook)

1. Install Docker Desktop (Apple chip). In Docker Desktop settings, turn **off** the beta setting
   *"Enable VirtioFS accelerated directory sharing"*. The README warns that it breaks access to the mounted design
   folder. The general VirtioFS setting is fine.
2. In Terminal:
   ```
   cd ~
   git clone --depth=1 https://github.com/iic-jku/iic-osic-tools.git
   mkdir -p ~/eda/designs && cd ~/eda/designs
   git clone -b FPGA https://github.com/chaithr45/Final_year_proj.git
   cd ~/iic-osic-tools
   ./start_vnc.sh
   ```
3. Open **http://localhost/?password=abc123** in the browser, start a terminal in the desktop, then:
   ```
   cd /foss/designs/Final_year_proj
   bash ms/setup/check_tools.sh
   ```

On the Mac, VNC mode is usually smoother than X11 for KLayout (README). If you want X11 later (`./start_x.sh`), install
XQuartz first and enable *"Allow connections from network clients"* (XQuartz preferences, Security tab).

Known Apple Silicon issue: an "Illegal instruction" crash in some libraries under Docker's VM. The start scripts
since image 2026.08 apply the workaround (`OPENSSL_armcap=0`) automatically (KNOWN_ISSUES.md).

## What the check does, and what you should see

`ms/setup/check_tools.sh` runs four steps and saves its output to `ms/setup/results/check_tools_<date>.txt`:

1. **PDK.** It selects SKY130A (`source sak-pdk-script.sh sky130A`, as the image's own tests do) and checks that the ngspice
   model library exists.
2. **Versions.** It finds ngspice, xschem, magic, netgen and klayout, and prints the versions it can read.
3. **ngspice + SKY130 smoke test** (`ms/analog/smoke/run_smoke.sh`, about 30-60 s), compared with values I simulated
   with the same PDK commit (ngspice-42 in the cloud; your container has ngspice-47, so ranges allow small changes):

   | Check | Cloud reference | Must be in |
   |---|---|---|
   | nfet_01v8 W/L = 1/0.15 um, drain current at VGS = VDS = 1.8 V | 501.0 uA | 486-516 uA |
   | pfet_01v8 W/L = 2/0.15 um, \|ID\| at \|VGS\| = \|VDS\| = 1.8 V | 403.4 uA | 391-416 uA |
   | inverter (Wn 1 um, Wp 2 um) switching threshold VM | 0.870 V | 0.855-0.885 V |
   | inverter delay into 10 fF, high-to-low / low-to-high | 36.0 / 43.3 ps | +-10 % |
   | Monte Carlo, 40 samples: offset of two matched nfets (W/L 1/0.5 um, 10 uA), mean / std | -2.9 / 9.5 mV | -6..6 / 6.2-12.9 mV |

4. **Magic DRC and netgen LVS** of a known-good inverter (the image's own test 02, copied into `ms/setup/layver_inv/`
   with its licence notice). xschem netlists the schematic, Magic extracts the layout, and netgen compares the two.

The last line must read **`ALL TOOL CHECKS PASSED`**. Send me the results file (or commit it on `FPGA`).

| If you see | Do |
|---|---|
| `PDK_ROOT is not set` / sky130A not selected | run `sak-pdk sky130A` in the container terminal, then the check again |
| a value `OUT OF RANGE` in step 3 | send the results file; it means a different model version, not a broken install. I'll look at it |
| `sak-drc.sh / sak-lvs.sh not found` | you are not inside the container (run it in the container's terminal, not on Windows/macOS) |
| browser shows nothing at http://localhost | wait for the first image download to finish (the start script's window shows progress); if port 80 is taken, start with `set WEBSERVER_PORT=8080` (Windows) or `WEBSERVER_PORT=8080 ./start_vnc.sh` (Mac) and open http://localhost:8080 |
| `/foss/designs` empty | the repository was cloned somewhere else: it must be in `%USERPROFILE%\eda\designs` (Windows) or `~/eda/designs` (Mac) |
| `$'\r': command not found` | Windows line endings: delete the clone and clone from inside the container terminal (`cd /foss/designs && git clone -b FPGA https://github.com/chaithr45/Final_year_proj.git`) |

## What was verified before shipping this

In the cloud session (15 Nov 2026) I installed ngspice-42 and SKY130A from the same open_pdks commit the 2026.10
image pins (`1689ac3f2dc763876eaf967227c7dfe831b031ae`, fetched with `ciel`) and ran step 3: all 8 checks pass,
and the Monte Carlo samples repeat exactly for the same seeds. Steps 1, 2 and 4 need the container's own scripts
(`sak-pdk-script.sh`, `sak-drc.sh`, `sak-lvs.sh`), Magic, netgen, KLayout and xschem, which the cloud session does not have.
So **step 4 has not been run by me**. It is the image maintainers' own regression test, so it should pass, but your
run is the first real check.
