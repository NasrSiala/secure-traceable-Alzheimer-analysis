"""cocotb bench of fir_decim (T3.19, 1/2, AC-16.2).

Needs GHDL and cocotb: `make -C hw/sim cocotb` runs this after the SHA-256 benches.
Not collected by pytest (testpaths = tests). The oracle is saam.dsp.fir_fixed.
20 signals of 5055 int16 samples, reset or clear between them, 1011 outputs each.
"""

from __future__ import annotations

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, RisingEdge
from fir_support import (
    INPUT_LENGTH,
    OUTPUT_LENGTH,
    SIGNAL_COUNT,
    coef_id,
    filter_decimate,
    signals,
)

# 111 MAC cycles, one rounding cycle, then the edge that raises out_valid.
MAC_EDGES = 112


def _signed(value: int, bits: int = 16) -> int:
    value &= (1 << bits) - 1
    if value >= 1 << (bits - 1):
        value -= 1 << bits
    return value


async def _reset(dut) -> None:  # type: ignore[no-untyped-def]
    dut.clear.value = 0
    dut.in_valid.value = 0
    dut.in_data.value = 0
    dut.aresetn.value = 0
    await ClockCycles(dut.aclk, 2)
    dut.aresetn.value = 1
    await RisingEdge(dut.aclk)


async def _clear(dut) -> None:  # type: ignore[no-untyped-def]
    dut.in_valid.value = 0
    dut.clear.value = 1
    await RisingEdge(dut.aclk)
    dut.clear.value = 0
    await RisingEdge(dut.aclk)
    assert int(dut.in_ready.value) == 1
    assert int(dut.out_valid.value) == 0


async def _put(dut, sample: int, produces: bool) -> int | None:  # type: ignore[no-untyped-def]
    for _ in range(200):
        await RisingEdge(dut.aclk)
        if int(dut.in_ready.value) == 1 and int(dut.in_valid.value) == 0:
            break
    else:
        raise AssertionError("in_ready stayed low")
    dut.in_data.value = sample & 0xFFFF
    dut.in_valid.value = 1
    await RisingEdge(dut.aclk)
    dut.in_valid.value = 0
    if not produces:
        assert int(dut.out_valid.value) == 0
        assert int(dut.in_ready.value) == 1
        return None
    assert int(dut.in_ready.value) == 0
    edges = 0
    while True:
        await RisingEdge(dut.aclk)
        edges += 1
        if int(dut.out_valid.value) == 1:
            break
        assert int(dut.in_ready.value) == 0, "in_ready rose during the MAC"
        assert edges < 200
    assert edges == MAC_EDGES, edges
    output = _signed(int(dut.out_data.value))
    await RisingEdge(dut.aclk)
    assert int(dut.out_valid.value) == 0, "out_valid is not a single cycle"
    return output


async def _run(dut, samples: list[int]) -> list[int]:  # type: ignore[no-untyped-def]
    outputs: list[int] = []
    for index, sample in enumerate(samples):
        got = await _put(dut, sample, index % 5 == 0)
        if got is not None:
            outputs.append(got)
    return outputs


@cocotb.test
async def test_coef_id_and_random_signals(dut) -> None:  # type: ignore[no-untyped-def]
    """20 int16 signals, clear or reset between them, 1011 outputs each."""
    clock = Clock(dut.aclk, 10, unit="ns")
    cocotb.start_soon(clock.start())
    await _reset(dut)
    assert f"{int(dut.coef_id.value):08x}" == coef_id()
    for number, samples in enumerate(signals()):
        assert len(samples) == INPUT_LENGTH
        if number == 10:
            await _reset(dut)
        elif number != 0:
            await _clear(dut)
        got = await _run(dut, samples)
        assert len(got) == OUTPUT_LENGTH
        assert got == filter_decimate(samples)
    assert SIGNAL_COUNT == 20
