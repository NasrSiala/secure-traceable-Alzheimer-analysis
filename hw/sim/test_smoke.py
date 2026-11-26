"""Simulation réelle du registre de test utilisé pour amorcer la CI T1.10."""

import cocotb
from cocotb.clock import Clock
from cocotb.handle import SimHandleBase
from cocotb.triggers import FallingEdge, ReadOnly, RisingEdge, Timer


@cocotb.test()
async def captures_every_byte(dut: SimHandleBase) -> None:
    dut.clk.value = 0
    dut.aresetn.value = 0
    dut.d.value = 0
    await Timer(1, unit="ns")
    assert int(dut.q.value) == 0
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())

    for value in range(256):
        await FallingEdge(dut.clk)
        dut.aresetn.value = 1
        dut.d.value = value
        await RisingEdge(dut.clk)
        await ReadOnly()
        assert int(dut.q.value) == value, f"Octet {value} mal capturé"


@cocotb.test()
async def resets_without_an_edge_and_holds_between_edges(dut: SimHandleBase) -> None:
    dut.clk.value = 0
    dut.aresetn.value = 1
    dut.d.value = 0xAA
    await Timer(1, unit="ns")
    dut.clk.value = 1
    await Timer(1, unit="ns")
    assert int(dut.q.value) == 0xAA

    dut.clk.value = 0
    dut.d.value = 0x55
    await Timer(1, unit="ns")
    assert int(dut.q.value) == 0xAA

    dut.aresetn.value = 0
    await Timer(1, unit="ns")
    assert int(dut.q.value) == 0
    dut.aresetn.value = 1
    await Timer(1, unit="ns")
    assert int(dut.q.value) == 0
    dut.clk.value = 1
    await Timer(1, unit="ns")
    assert int(dut.q.value) == 0x55
