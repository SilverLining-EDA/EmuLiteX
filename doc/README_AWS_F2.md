# LiteX on AWS EC2 F2

Host access to a LiteX SoC on F2 uses the same software path as the AWS HDK
examples (`cl_axil_reg_access`, `hello_world`): FPGA **slot**, then
`fpga_pci_attach` on **AppPF BAR0** (OCL AXI-Lite) and 32-bit peek/poke.

There is no board UART. The LiteX BIOS is the **crossover UART** on CSRs.
`litex_term crossover` talks to `litex_server`; the server is `CommAWSF2`.

```
  litex_term crossover
          |  TCP Etherbone :1234
  litex_server --aws-f2 --slot 0
          |  fpga_mgmt_init
          |  fpga_pci_attach(slot, FPGA_APP_PF, APP_PF_BAR0)
          |  fpga_pci_peek / fpga_pci_poke
          v
  AppPF BAR0  (64 MiB OCL)
          v
  AWS Shell  -->  LiteX SoC CSRs (BAR offset 0 = CSR base)
          v
  uart_xover  -->  BIOS
```

`RemoteClient` subtracts the CSR base when the server announces `CommAWSF2`,
so addresses from `csr.csv` (for example `0xf0002020`) become BAR offsets
(`0x2020`).

## Prerequisites

- F2 instance with the AFI already created from the LiteX DCP.
- aws-fpga SDK sourced (`libfpga_mgmt` / `fpga-load-local-image`).
- The **same** `csr.csv` that was used to build that AFI.
- LiteX installed (this tree), including `litex_server` and `litex_term`.

## Steps

### 1. Source the SDK and load the AFI

```bash
source $AWS_FPGA_REPO_DIR/sdk_setup.sh
sudo fpga-load-local-image -S 0 -I agfi-xxxxxxxxxxxxxxxxx
sudo fpga-describe-local-image -S 0 -H
```

Status must be `loaded`. Optional check that the CL is alive:

```bash
sudo fpga-get-virtual-led -S 0
```

If the target supports `--load`, this is the same as:

```bash
python3 -m litex_boards.targets.aws_f2 --load --agfi agfi-xxxxxxxxxxxxxxxxx
```

### 2. Start CommAWSF2 (keep this running)

Same attach as the HDK host apps (`test_sum`, `hello_cva6`):

```bash
litex_server --aws-f2 --slot 0
```

Use `--slot N` on multi-FPGA instance types. The process needs the SDK
library from step 1 (`source sdk_setup.sh`). BAR access often requires
root or FPGA device group membership, same as the AWS examples (`sudo`
those tools if peek/poke fails).

### 3. Open the BIOS terminal

Other terminal:

```bash
litex_term crossover --csr-csv build/aws_f2/csr.csv
```

This is the usual LiteX console (crossover, not `/dev/ttyUSB*`).

### 4. Optional CSR peek (same server)

```bash
python3 -c "
from litex import RemoteClient
bus = RemoteClient(csr_csv='build/aws_f2/csr.csv')
bus.open()
print(hex(bus.regs.ctrl_scratch.read()))
bus.regs.ctrl_scratch.write(0xdeadbeef)
print(hex(bus.regs.ctrl_scratch.read()))
bus.close()
"
```

## Files

| File | Role |
|------|------|
| `litex/tools/remote/comm_aws_f2.py` | `CommAWSF2`: `fpga_mgmt_init`, attach AppPF BAR0, peek/poke |
| `litex/tools/litex_server.py` | `--aws-f2` / `--slot` |
| `litex/tools/litex_client.py` | CSR-base remap for `CommAWSF2` |
| `litex/tools/litex_term.py` | Unchanged; use port `crossover` |

## Notes

- AppPF BAR0 is OCL only. Do not attach MgmtPF.
- `csr.csv` must match the loaded AGFI. UART offsets are not fixed across configs.
- OCL is 32-bit AXI-Lite; `CommAWSF2` only does DWORD incr accesses.
- `litex_term jtag` is not used on this path.
