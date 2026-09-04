#
# This file is part of LiteX.
#
# SPDX-License-Identifier: BSD-2-Clause

import os

from migen import *

from litex import get_data_mod
from litex.gen import *

from litex.soc.interconnect import wishbone
from litex.soc.cores.cpu import CPU, CPU_GCC_TRIPLE_RISCV64

# Variants -----------------------------------------------------------------------------------------

CPU_VARIANTS = ["standard"]

# GCC Flags ----------------------------------------------------------------------------------------

GCC_FLAGS = {
    #                       /------------ Base ISA
    #                       |    /------- Hardware Multiply + Divide
    #                       |    |/----- Atomics
    #                       |    ||/---- Compressed ISA
    #                       |    |||/--- Single-Precision Floating-Point
    #                       |    ||||/-- Double-Precision Floating-Point
    #                       i    macfd
    "standard": "-march=rv64imac_zicsr_zifencei -mabi=lp64 ",
}

# Silver -------------------------------------------------------------------------------------------

class Silver(CPU):
    category             = "softcore"
    family               = "riscv"
    name                 = "silver"
    human_name           = "Silver"
    variants             = CPU_VARIANTS
    data_width           = 64
    endianness           = "little"
    gcc_triple           = CPU_GCC_TRIPLE_RISCV64
    linker_output_format = "elf64-littleriscv"
    nop                  = "nop"
    io_regions           = {0x8000_0000: 0x8000_0000} # Origin, Length.

    # GCC Flags.
    @property
    def gcc_flags(self):
        flags =  "-mno-save-restore "
        flags += GCC_FLAGS[self.variant]
        flags += "-D__silver__ "
        flags += "-DUART_POLLING "
        flags += "-mcmodel=medany"
        return flags

    # Memory Mapping.
    @property
    def mem_map(self):
        return {
            "rom"  : 0x1000_0000,
            "sram" : 0x2000_0000,
            "csr"  : 0x8000_0000,
        }

    def __init__(self, platform, variant="standard"):
        self.platform     = platform
        self.variant      = variant
        self.reset        = Signal()
        self.ibus         = ibus = wishbone.Interface(data_width=64, address_width=32, addressing="word")
        self.dbus         = dbus = wishbone.Interface(data_width=64, address_width=32, addressing="word")
        self.periph_buses = [ibus, dbus]
        self.memory_buses = []

        # # #

        self.cpu_params = dict(
            # Clk / Rst.
            i_clk = ClockSignal("sys"),
            i_rst = ResetSignal("sys") | self.reset,

            # IBus (64-bit, word addressed).
            o_ibus_adr   = ibus.adr,
            o_ibus_cyc   = ibus.cyc,
            o_ibus_stb   = ibus.stb,
            o_ibus_we    = ibus.we,
            o_ibus_sel   = ibus.sel,
            o_ibus_dat_w = ibus.dat_w,
            i_ibus_dat_r = ibus.dat_r,
            i_ibus_ack   = ibus.ack,
            i_ibus_err   = ibus.err,

            # DBus (64-bit, word addressed).
            o_dbus_adr   = dbus.adr,
            o_dbus_cyc   = dbus.cyc,
            o_dbus_stb   = dbus.stb,
            o_dbus_we    = dbus.we,
            o_dbus_sel   = dbus.sel,
            o_dbus_dat_w = dbus.dat_w,
            i_dbus_dat_r = dbus.dat_r,
            i_dbus_ack   = dbus.ack,
            i_dbus_err   = dbus.err,

            o_halt_o = Open(),
        )

        self.add_sources(platform)

    def set_reset_address(self, reset_address):
        self.reset_address = reset_address
        self.cpu_params.update(p_RESET_PC=Constant(reset_address, 64))

    def add_sources(self, platform):
        vdir = os.path.join(get_data_mod("cpu", "silver").data_location, "rtl")
        for fname in ("alu.v", "regfile.v", "c_decompress.v", "imem.v", "dmem.v", "riscv_rtype_fsm.v"):
            platform.add_source(os.path.join(vdir, fname))
        platform.add_source(os.path.join(os.path.dirname(__file__), "silver_wb.v"))

    def do_finalize(self):
        assert hasattr(self, "reset_address")
        self.specials += Instance("silver_wb", **self.cpu_params)
