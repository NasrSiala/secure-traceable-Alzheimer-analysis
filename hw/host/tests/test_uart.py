"""IF-14 on the PS model: frames, three CRC retries, INFO, SHA-256 of abc, FIR."""

from __future__ import annotations

import hashlib
import struct
import sys
from pathlib import Path

import pytest

HOST = Path(__file__).resolve().parents[1]
ROOT = HOST.parents[1]
sys.path.insert(0, str(HOST))
sys.path.insert(0, str(ROOT))

from ps_model import PsModel
from uart_framing import crc32, decode_frame, encode_frame
from zybo_client import (
    TRANSMISSION,
    UNREACHABLE,
    BoardUnreachable,
    TransmissionError,
    ZyboClient,
)

from saam.dsp.fir_fixed import coef_id, filter_decimate

ABC = hashlib.sha256(b"abc").digest()


def test_frame_roundtrip_and_rejected_crc_and_length() -> None:
    frame = encode_frame(0x10, b"abc")
    assert decode_frame(frame) == (0x10, b"abc")
    broken = bytearray(frame)
    broken[-1] ^= 0xFF
    with pytest.raises(ValueError, match="crc"):
        decode_frame(bytes(broken))
    short = frame[:-1]
    with pytest.raises(ValueError, match="longueur"):
        decode_frame(short)
    huge = bytes((0xA5, 0x01)) + struct.pack("<I", 2_000_000) + b"\x00" * 4
    with pytest.raises(ValueError, match="longueur"):
        decode_frame(huge)
    assert crc32(frame[:-4]) == struct.unpack("<I", frame[-4:])[0]


def test_info_sha256_abc_and_fir_match_the_references() -> None:
    model = PsModel(version=0x01020304)
    client = ZyboClient(model.exchange)
    version, coef = client.info()
    assert version == 0x01020304
    assert coef == int(coef_id(), 16)
    assert client.sha256(b"abc") == ABC
    samples = [0, 1000, -1000, 32767, -32768]
    assert client.fir(samples) == filter_decimate(samples)


def test_three_retries_then_the_transmission_error() -> None:
    calls = {"n": 0}

    def exchange(frame: bytes) -> bytes:
        calls["n"] += 1
        good = PsModel().exchange(frame)
        flipped = bytearray(good)
        flipped[-1] ^= 0x01
        return bytes(flipped)

    client = ZyboClient(exchange)
    with pytest.raises(TransmissionError, match=TRANSMISSION):
        client.sha256(b"abc")
    assert calls["n"] == 4


def test_a_later_good_frame_is_accepted_within_the_retries() -> None:
    calls = {"n": 0}
    model = PsModel()

    def exchange(frame: bytes) -> bytes:
        calls["n"] += 1
        good = model.exchange(frame)
        if calls["n"] < 4:
            flipped = bytearray(good)
            flipped[-1] ^= 0x01
            return bytes(flipped)
        return good

    assert ZyboClient(exchange).sha256(b"abc") == ABC
    assert calls["n"] == 4


def test_timeout_is_the_unreachable_board_sentence() -> None:
    def exchange(frame: bytes) -> bytes:
        raise TimeoutError

    with pytest.raises(BoardUnreachable, match=UNREACHABLE):
        ZyboClient(exchange).info()
