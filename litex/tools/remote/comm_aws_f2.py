#
# This file is part of LiteX.
#
# Copyright (c) 2026 LiteX-Hub community
# SPDX-License-Identifier: BSD-2-Clause

# AWS F2 host access follows the HDK software examples (cl_axil_reg_access, hello_world):
#   fpga_mgmt_init()
#   fpga_pci_attach(slot, FPGA_APP_PF, APP_PF_BAR0)
#   fpga_pci_peek / fpga_pci_poke  on OCL (AppPF BAR0)
#
# Same contract as other LiteX comms so litex_server --aws-f2 can serve litex_term crossover.

import ctypes
import ctypes.util
import os

from litex.tools.remote.csr_builder import CSRBuilder

# From aws-fpga sdk/userspace/include/hal/fpga_common.h
FPGA_APP_PF = 0
APP_PF_BAR0 = 0
PCI_BAR_HANDLE_INIT = -1


def _check(rc, what):
    if rc != 0:
        raise RuntimeError(
            "{} failed with status {}. "
            "Source sdk_setup.sh and confirm the AFI is loaded "
            "(sudo fpga-describe-local-image -S <slot>).".format(what, rc))


def _sdk_lib_candidates():
    names = []
    for libname in ("fpga_mgmt", "fpga_pci"):
        found = ctypes.util.find_library(libname)
        if found:
            names.append(found)
    names.extend(["libfpga_mgmt.so", "libfpga_pci.so"])
    roots = []
    for env in ("SDK_DIR", "AWS_FPGA_REPO_DIR"):
        value = os.environ.get(env)
        if value:
            roots.append(value)
            roots.append(os.path.join(value, "sdk", "userspace"))
    for root in roots:
        names.append(os.path.join(root, "lib", "so", "libfpga_mgmt.so"))
        names.append(os.path.join(root, "lib", "libfpga_mgmt.so"))
        names.append(os.path.join(root, "userspace", "lib", "so", "libfpga_mgmt.so"))
    for path in ("/usr/lib", "/usr/local/lib", "/usr/lib64", "/usr/local/lib64"):
        names.append(os.path.join(path, "libfpga_mgmt.so"))
        names.append(os.path.join(path, "libfpga_pci.so"))
    return names


def _bind_sdk_lib(lib):
    if hasattr(lib, "fpga_mgmt_init"):
        lib.fpga_mgmt_init.restype = ctypes.c_int
    if hasattr(lib, "fpga_pci_init"):
        lib.fpga_pci_init.restype = ctypes.c_int
    lib.fpga_pci_attach.argtypes = [
        ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_uint32,
        ctypes.POINTER(ctypes.c_int),
    ]
    lib.fpga_pci_attach.restype = ctypes.c_int
    lib.fpga_pci_detach.argtypes = [ctypes.c_int]
    lib.fpga_pci_detach.restype  = ctypes.c_int
    lib.fpga_pci_poke.argtypes   = [ctypes.c_int, ctypes.c_uint64, ctypes.c_uint32]
    lib.fpga_pci_poke.restype    = ctypes.c_int
    lib.fpga_pci_peek.argtypes   = [ctypes.c_int, ctypes.c_uint64, ctypes.POINTER(ctypes.c_uint32)]
    lib.fpga_pci_peek.restype    = ctypes.c_int


def load_sdk_lib():
    """Load libfpga_mgmt (exports fpga_pci_* via whole-archive) or libfpga_pci."""
    tried = []
    for path in _sdk_lib_candidates():
        if path in tried:
            continue
        tried.append(path)
        try:
            lib = ctypes.CDLL(path)
        except OSError:
            continue
        if hasattr(lib, "fpga_pci_attach") and hasattr(lib, "fpga_pci_peek"):
            _bind_sdk_lib(lib)
            return lib
    return None


# CommAWSF2 ----------------------------------------------------------------------------------------

class CommAWSF2(CSRBuilder):
    """AWS F2 AppPF BAR0 (OCL) via the FPGA SDK, same flow as HDK host examples."""

    def __init__(self, slot=0, csr_csv=None, debug=False, lib=None):
        CSRBuilder.__init__(self, comm=self, csr_csv=csr_csv)
        self.slot    = int(slot)
        self.debug   = debug
        self._lib    = lib
        self._handle = None

    def open(self):
        if self._handle is not None:
            return
        lib = self._lib if self._lib is not None else load_sdk_lib()
        if lib is None:
            raise RuntimeError(
                "AWS FPGA SDK library not found (libfpga_mgmt / libfpga_pci). "
                "On the F2 instance: source sdk_setup.sh from aws-fpga.")
        if hasattr(lib, "fpga_mgmt_init"):
            _check(lib.fpga_mgmt_init(), "fpga_mgmt_init")
        elif hasattr(lib, "fpga_pci_init"):
            _check(lib.fpga_pci_init(), "fpga_pci_init")
        handle = ctypes.c_int(PCI_BAR_HANDLE_INIT)
        _check(lib.fpga_pci_attach(
            self.slot, FPGA_APP_PF, APP_PF_BAR0, 0, ctypes.pointer(handle)),
            "fpga_pci_attach(slot={}, AppPF, BAR0)".format(self.slot))
        self._lib    = lib
        self._handle = handle.value

    def close(self):
        if self._handle is None or self._lib is None:
            return
        self._lib.fpga_pci_detach(self._handle)
        self._handle = None

    def read(self, addr, length=None, burst="incr"):
        assert burst == "incr"
        if self._handle is None:
            self.open()
        data = []
        length_int = 1 if length is None else length
        for i in range(length_int):
            offset = addr + 4 * i
            value  = ctypes.c_uint32()
            _check(self._lib.fpga_pci_peek(self._handle, offset, ctypes.pointer(value)),
                "fpga_pci_peek @ 0x{:08x}".format(offset))
            if self.debug:
                print("read  0x{:08x} @ 0x{:08x}".format(value.value, offset))
            if length is None:
                return value.value
            data.append(value.value)
        return data

    def write(self, addr, data):
        if self._handle is None:
            self.open()
        data = data if isinstance(data, list) else [data]
        for i, value in enumerate(data):
            offset = addr + 4 * i
            _check(self._lib.fpga_pci_poke(self._handle, offset, int(value)),
                "fpga_pci_poke @ 0x{:08x}".format(offset))
            if self.debug:
                print("write 0x{:08x} @ 0x{:08x}".format(int(value), offset))
