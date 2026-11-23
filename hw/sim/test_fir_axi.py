"""cocotb bench of fir_axi (T3.20, 2/2, IF-16).

Needs GHDL and cocotb. `make -C hw/sim cocotb` runs this with the other cores.
The oracle is saam.dsp.fir_fixed. A producing sample keeps IN_READY low until
DATA_OUT is read; the bench polls STATUS the same way the PS driver must.
"""

from __future__ import annotations

import sys
from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, RisingEdge

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from saam.dsp.fir_fixed import coef_id, filter_decimate

CTRL = 0x00
STATUS = 0x04
DATA_IN = 0x08
DATA_OUT = 0x0C
COEF_ID = 0x10
SAMPLES = [1000, 0, 0, 0, 0, -1000]


def _mask(value: int) -> int:
    return int(value) & 0xFFFFFFFF


def _signed16(word: int) -> int:
    value = word & 0xFFFF
    if value >= 0x8000:
        value -= 0x10000
    return value


async def _reset(dut) -> None:  # type: ignore[no-untyped-def]
    clock = Clock(dut.aclk, 10, unit="ns")
    cocotb.start_soon(clock.start())
    for name in (
        "s_axi_awvalid",
        "s_axi_wvalid",
        "s_axi_bready",
        "s_axi_arvalid",
        "s_axi_rready",
        "s_axi_awaddr",
        "s_axi_wdata",
        "s_axi_araddr",
    ):
        getattr(dut, name).value = 0
    dut.s_axi_awprot.value = 0
    dut.s_axi_wstrb.value = 0
    dut.s_axi_arprot.value = 0
    dut.aresetn.value = 0
    await ClockCycles(dut.aclk, 2)
    dut.aresetn.value = 1
    await RisingEdge(dut.aclk)


async def _write(dut, addr: int, value: int) -> None:  # type: ignore[no-untyped-def]
    dut.s_axi_awaddr.value = addr
    dut.s_axi_wdata.value = value & 0xFFFFFFFF
    dut.s_axi_wstrb.value = 0xF
    dut.s_axi_awvalid.value = 1
    dut.s_axi_wvalid.value = 1
    dut.s_axi_bready.value = 1
    for _ in range(100000):
        await RisingEdge(dut.aclk)
        if int(dut.s_axi_bvalid.value) == 1:
            break
    else:
        raise AssertionError(f"write timeout at {addr:#x}")
    dut.s_axi_awvalid.value = 0
    dut.s_axi_wvalid.value = 0
    await RisingEdge(dut.aclk)
    dut.s_axi_bready.value = 0


async def _read(dut, addr: int) -> int:  # type: ignore[no-untyped-def]
    dut.s_axi_araddr.value = addr
    dut.s_axi_arvalid.value = 1
    dut.s_axi_rready.value = 1
    for _ in range(1000):
        await RisingEdge(dut.aclk)
        if int(dut.s_axi_rvalid.value) == 1:
            break
    else:
        raise AssertionError(f"read timeout at {addr:#x}")
    data = _mask(dut.s_axi_rdata.value)
    dut.s_axi_arvalid.value = 0
    await RisingEdge(dut.aclk)
    dut.s_axi_rready.value = 0
    return data


async def _push(dut, sample: int, produces: bool) -> int | None:  # type: ignore[no-untyped-def]
    await _write(dut, DATA_IN, sample & 0xFFFF)
    for _ in range(400):
        status = await _read(dut, STATUS)
        if status & 0x2:
            assert not status & 0x1, "IN_READY high while an output is pending"
            assert produces
            output = _signed16(await _read(dut, DATA_OUT))
            status = await _read(dut, STATUS)
            assert not status & 0x2, "DATA_OUT read did not consume the sample"
            return output
        if status & 0x1:
            assert not produces
            return None
    raise AssertionError("STATUS timeout")


@cocotb.test
async def test_axi_fir_matches_fir_fixed_and_holds_the_output(dut) -> None:  # type: ignore[no-untyped-def]
    await _reset(dut)
    assert await _read(dut, COEF_ID) == int(coef_id(), 16)
    await _write(dut, CTRL, 0x1)
    outputs: list[int] = []
    for index, sample in enumerate(SAMPLES):
        got = await _push(dut, sample, index % 5 == 0)
        if got is not None:
            outputs.append(got)
    assert outputs == filter_decimate(SAMPLES)
