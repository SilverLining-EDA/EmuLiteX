# Getting Started with EmuLiteX

## Quick Start

```bash
mkdir Litex_Work
cd Litex_Work
git clone https://github.com/SilverLining-EDA/EmuLiteX.git
cd EmuLiteX
./setup.sh
```
Sets up the full environment and runs the default simulation on VexRiscv.

---

## Common Workflows

### Run simulation only
```bash
./setup.sh --sim-only
# or
source venv/bin/activate
litex_sim --cpu-type=vexriscv
```

### Change CPU
```bash
./setup.sh --cpu=serv
# or
source venv/bin/activate
litex_sim --cpu-type=serv
```

### Update repositories
```bash
./setup.sh --update
```
Updates all repositories and runs a basic simulation as a sanity check.

---

## All Options

| Flag | Description |
|------|-------------|
| `--config=<name>` | Install config: `minimal`, `standard`, `full` (default: `standard`) |
| `--cpu=<name>` | CPU type for simulation (default: `vexriscv`) |
| `--sim-only` | Skip setup, only run simulation |
| `--update` | Force update repositories and reinstall |
| `--help`, `-h` | Show help message |

For all supported values, run `./setup.sh --help`.

---

