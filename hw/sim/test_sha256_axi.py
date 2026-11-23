"""cocotb bench of sha256_axi (T3.20, 1/2, IF-15).

Needs GHDL and cocotb. `make -C hw/sim cocotb` runs this after the direct cores.
The oracle is hashlib. The slave is driven as AXI4-Lite: the write response is
what the bench waits for, because awready falls in the same delta that accepts
the beat and cocotb samples signals after the clock edge.
"""

from __future__ import annotations

import hashlib

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, RisingEdge

CTRL = 0x00
STATUS = 0x04
DATA_IN = 0x08
LAST_BYTES = 0x0C
DIGEST0 = 0x10


def _mask(value: int) -> int:
    return int(value) & 0xFFFFFFFF


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


async def _hash(dut, message: bytes) -> bytes:  # type: ignore[no-untyped-def]
    await _write(dut, CTRL, 0x1)
    if len(message) == 0:
        await _write(dut, LAST_BYTES, 0)
        await _write(dut, CTRL, 0x2)
    else:
        last_n = len(message) % 4 or 4
        words = [message[i : i + 4] for i in range(0, len(message), 4)]
        for word in words[:-1]:
            await _write(dut, DATA_IN, int.from_bytes(word, "big"))
        await _write(dut, LAST_BYTES, last_n)
        await _write(dut, CTRL, 0x2)
        await _write(dut, DATA_IN, int.from_bytes(words[-1], "big"))
    for _ in range(100000):
        status = await _read(dut, STATUS)
        if status & 0x4:
            break
    else:
        raise AssertionError("DONE timeout")
    digest = bytearray()
    for index in range(8):
        digest += (await _read(dut, DIGEST0 + 4 * index)).to_bytes(4, "big")
    return bytes(digest)


@cocotb.test
async def test_axi_hash_matches_hashlib(dut) -> None:  # type: ignore[no-untyped-def]
    await _reset(dut)
    for message in (b"", b"abc", b"abcd"):
        got = await _hash(dut, message)
        assert got == hashlib.sha256(message).digest(), message
