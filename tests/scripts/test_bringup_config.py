"""T1.9 (l10-board-bringup): configuration checks of the bring-up flow, without a board.

Nothing here proves that the board boots, that the AXI register answers or what the UART
throughput is: that needs the Zybo Z7-10 and is the job of hw/host/tests (marker `board`). These
tests check what can be checked without it:

  - build.tcl runs to the end in a Tcl interpreter whose Vivado commands are recorded instead of
    executed, and build_app.py runs with a fake `vitis` module (mocks, never shown as a result of
    the tools);
  - the PL register has the entity and the AXI4-Lite ports the block design expects;
  - the PS application compiles with the ARM compiler against the real Xilinx UART driver
    headers, in both driver APIs (device id and SDT), when a Vitis installation is available.
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import types
import zipfile
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from tkinter import Tk

ROOT = Path(__file__).resolve().parents[2]
BUILD_TCL = ROOT / "hw" / "vivado" / "build.tcl"
APP_DIR = ROOT / "hw" / "ps_app" / "bringup"
APP_PY = APP_DIR / "build_app.py"
HELLO_C = APP_DIR / "hello.c"
REG_VHD = ROOT / "hw" / "rtl" / "axil_reg_bringup.vhd"

PART = "xc7z010clg400-1"
BOARD_PART = "digilent.com:zybo-z7-10:part0:1.1"


# --------------------------------------------------------------------------------------------
# A Tcl interpreter that records the commands of Vivado and XSCT
# --------------------------------------------------------------------------------------------

PRELUDE = r"""
set ::calls {}
set ::answers [dict create]
proc mock_answer {name value} { dict set ::answers $name $value }
proc unknown {name args} {
  lappend ::calls [linsert $args 0 $name]
  if {[dict exists $::answers $name]} { return [dict get $::answers $name] }
  return ""
}
rename exec ::real_exec
proc exec {args} {
  lappend ::calls [linsert $args 0 exec]
  return ""
}
"""


class Recorder:
    def __init__(self, interp: Tk) -> None:
        self.interp = interp

    def answer(self, command: str, value: str) -> None:
        self.interp.eval(f"mock_answer {{{command}}} {{{value}}}")

    def source(self, script: Path) -> None:
        # Not Tcl's own `source`: on Windows it failed now and then with "couldn't read file ...:
        # No error". The text is read here and evaluated with `info script` set, which is all the
        # scripts use of it.
        text = script.read_text(encoding="utf-8")
        self.interp.eval(f"info script {{{script.as_posix()}}}")
        self.interp.eval(text)

    def calls(self) -> list[list[str]]:
        raw = self.interp.eval("set ::calls")
        return [
            list(self.interp.splitlist(call)) for call in self.interp.splitlist(raw)
        ]

    def commands(self) -> list[str]:
        return [call[0] for call in self.calls()]

    def find(self, command: str, *needles: str) -> list[list[str]]:
        return [
            call
            for call in self.calls()
            if call[0] == command and all(n in " ".join(call) for n in needles)
        ]


@pytest.fixture
def tcl() -> Recorder:
    tkinter = pytest.importorskip("tkinter", reason="no Tcl interpreter (tkinter) here")
    interp = tkinter.Tcl()
    interp.eval(PRELUDE)
    return Recorder(interp)


@pytest.fixture
def outdir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    out = tmp_path / "out"
    reports = tmp_path / "reports"
    monkeypatch.setenv("SAAM_HW_BUILD_DIR", str(out))
    monkeypatch.setenv("SAAM_HW_REPORT_DIR", str(reports))
    monkeypatch.setenv("SAAM_VIVADO_PROJECT", str(tmp_path / "zybo" / "zybo.xpr"))
    return tmp_path


def _good_project(tcl: Recorder) -> None:
    tcl.answer("get_property", "")
    tcl.interp.eval(
        "proc get_property {args} {"
        " lappend ::calls [linsert $args 0 get_property];"
        f" switch -- [lindex $args 0] {{PART {{return {PART}}} BOARD_PART {{return {BOARD_PART}}}"
        " DIRECTORY {return /tmp/proj} PROGRESS {return 100%} STATUS {return {write_bitstream Complete!}}}"
        " ; return {} }"
    )
    tcl.answer("version", "2025.2")
    # The segment of the register in the address map of the PS, as Vivado names it.
    tcl.answer("get_bd_addr_segs", "/processing_system7_0/Data/SEG_reg0_reg0")


# --------------------------------------------------------------------------------------------
# build.tcl: PS7 + one AXI4-Lite register, on the project the user created with the board
# --------------------------------------------------------------------------------------------

ALLOWED_VIVADO = {
    "open_project",
    "current_project",
    "get_property",
    "set_property",
    "add_files",
    "update_compile_order",
    "get_files",
    "remove_files",
    "get_bd_designs",
    "create_bd_design",
    "create_bd_cell",
    "get_bd_cells",
    "apply_bd_automation",
    "connect_bd_net",
    "get_bd_pins",
    "get_bd_intf_pins",
    "assign_bd_address",
    "get_bd_addr_segs",
    "get_bd_addr_spaces",
    "validate_bd_design",
    "save_bd_design",
    "make_wrapper",
    "launch_runs",
    "wait_on_run",
    "get_runs",
    "open_run",
    "report_utilization",
    "report_timing_summary",
    "write_hw_platform",
    "version",
    "close_project",
    "set_param",
    "current_fileset",
    "close_bd_design",
    "generate_target",
    "reset_run",
}


def test_the_part_and_the_board_are_the_ones_of_the_architecture() -> None:
    text = BUILD_TCL.read_text(encoding="utf-8")
    assert PART in text
    assert "xc7z020" not in text
    assert "zybo-z7-10" in text


def test_the_build_runs_to_the_bitstream_and_the_xsa(
    tcl: Recorder, outdir: Path
) -> None:
    _good_project(tcl)
    tcl.source(BUILD_TCL)

    assert tcl.find("open_project", "zybo.xpr")
    assert tcl.find("launch_runs", "impl_1", "write_bitstream")
    xsa = tcl.find("write_hw_platform", ".xsa")
    assert xsa
    assert "-include_bit" in xsa[0]
    assert (outdir / "out").as_posix() in " ".join(xsa[0]).replace("\\", "/")


def test_the_ps_is_configured_from_the_board_preset_at_100_mhz(
    tcl: Recorder, outdir: Path
) -> None:
    _good_project(tcl)
    tcl.source(BUILD_TCL)

    ps = tcl.find("create_bd_cell", "processing_system7")
    assert ps
    preset = tcl.find("apply_bd_automation", "processing_system7", "apply_board_preset")
    assert preset
    # The board preset is on: without it the PS7 has no DDR and no MIO set-up for the Zybo and
    # the application cannot run.
    assert 'apply_board_preset "1"' in " ".join(preset[0])
    assert 'apply_board_preset "0"' not in " ".join(preset[0])
    setters = " ".join(" ".join(c) for c in tcl.find("set_property"))
    assert "PCW_FPGA0_PERIPHERAL_FREQMHZ" in setters
    assert re.search(r"PCW_FPGA0_PERIPHERAL_FREQMHZ\s*\{?100\}?", setters)
    assert re.search(r"PCW_USE_M_AXI_GP0\s*\{?1\}?", setters)


def test_one_axi4_lite_register_is_added_as_a_module_reference_in_plain_vhdl(
    tcl: Recorder, outdir: Path
) -> None:
    _good_project(tcl)
    tcl.source(BUILD_TCL)

    added = tcl.find("add_files", "axil_reg_bringup.vhd")
    assert added
    # Vivado 2025.2 refuses a module reference whose top file is typed VHDL-2008 (filemgmt 56-195,
    # found by running the block design in Vivado): the file keeps the default type.
    assert not tcl.find("set_property", "file_type")
    assert "VHDL 2008" not in BUILD_TCL.read_text(encoding="utf-8").replace(
        "{VHDL 2008}: Vivado refuses", ""
    )
    module = tcl.find("create_bd_cell", "-type", "module", "axil_reg_bringup")
    assert len(module) == 1
    assert tcl.find("apply_bd_automation", "xilinx.com:bd_rule:axi4")
    # Only the PS and this register: no SHA-256 or FIR core in the bring-up design.
    everything = " ".join(" ".join(c) for c in tcl.calls())
    assert "sha256" not in everything.lower()
    assert "fir_" not in everything.lower()


def test_the_register_is_mapped_at_the_documented_address(
    tcl: Recorder, outdir: Path
) -> None:
    _good_project(tcl)
    tcl.source(BUILD_TCL)

    everything = " ".join(" ".join(c) for c in tcl.calls())
    assert "0x43C00000" in everything
    assert "assign_bd_address" in tcl.commands()
    # The C application uses the same base address.
    assert "0x43C00000" in HELLO_C.read_text(encoding="utf-8")


def test_the_environment_evidence_for_q14_is_written_without_a_path(
    tcl: Recorder, outdir: Path
) -> None:
    _good_project(tcl)
    tcl.source(BUILD_TCL)

    report = outdir / "reports" / "bringup-environment.json"
    assert report.is_file()
    data = json.loads(report.read_text(encoding="utf-8"))
    assert data["vivado_version"] == "2025.2"
    assert data["part"] == PART
    assert data["board_part"] == BOARD_PART
    assert data["register_base"] == "0x43C00000"
    text = report.read_text(encoding="utf-8")
    assert str(outdir) not in text
    assert os.environ.get("USERNAME", "\0") not in text


def test_the_reports_of_utilization_and_timing_are_written(
    tcl: Recorder, outdir: Path
) -> None:
    _good_project(tcl)
    tcl.source(BUILD_TCL)

    assert tcl.find("report_utilization", "bringup-utilization.rpt")
    assert tcl.find("report_timing_summary", "bringup-timing.rpt")


def test_it_stops_when_no_project_is_given(
    tcl: Recorder, outdir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("SAAM_VIVADO_PROJECT")
    _good_project(tcl)
    with pytest.raises(Exception, match="SAAM_VIVADO_PROJECT"):
        tcl.source(BUILD_TCL)
    assert "launch_runs" not in tcl.commands()


@pytest.mark.parametrize(
    ("property_name", "wrong", "message"),
    [
        ("PART", "xc7z020clg400-1", "xc7z010clg400-1"),
        ("BOARD_PART", "digilent.com:zybo-z7-20:part0:1.0", "zybo-z7-10"),
        ("BOARD_PART", "", "zybo-z7-10"),
    ],
)
def test_it_refuses_a_project_for_another_part_or_without_the_board(
    tcl: Recorder, outdir: Path, property_name: str, wrong: str, message: str
) -> None:
    _good_project(tcl)
    tcl.interp.eval(
        "proc get_property {args} {"
        f" switch -- [lindex $args 0] {{{property_name} {{return {{{wrong}}}}}"
        f" PART {{return {PART}}} BOARD_PART {{return {BOARD_PART}}} DIRECTORY {{return /tmp/p}}}}"
        " ; return {} }"
    )
    with pytest.raises(Exception, match=message):
        tcl.source(BUILD_TCL)
    assert "create_bd_design" not in tcl.commands()
    assert "launch_runs" not in tcl.commands()


def test_it_stops_when_the_run_does_not_finish(tcl: Recorder, outdir: Path) -> None:
    _good_project(tcl)
    tcl.interp.eval(
        "proc get_property {args} {"
        f" switch -- [lindex $args 0] {{PART {{return {PART}}} BOARD_PART {{return {BOARD_PART}}}"
        " DIRECTORY {return /tmp/p} PROGRESS {return 42%} STATUS {return {route_design ERROR}}}"
        " ; return {} }"
    )
    with pytest.raises(Exception, match="implementation"):
        tcl.source(BUILD_TCL)
    assert "write_hw_platform" not in tcl.commands()


def test_the_script_only_uses_vivado_commands_it_declares(
    tcl: Recorder, outdir: Path
) -> None:
    """A typo in a command name would run silently in the mock: the list is the guard."""
    _good_project(tcl)
    tcl.source(BUILD_TCL)

    used = set(tcl.commands())
    assert used <= ALLOWED_VIVADO, sorted(used - ALLOWED_VIVADO)


def test_the_build_products_are_not_versioned() -> None:
    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "hw/build/" in gitignore


def _ignored(path: str) -> bool:
    done = subprocess.run(
        ["git", "check-ignore", "-q", "--no-index", path],
        cwd=ROOT,
        capture_output=True,
        check=False,
    )
    return done.returncode == 0


@pytest.mark.parametrize(
    "path",
    [
        "hw/SAAM/SAAM.xpr",
        "hw/SAAM/SAAM.cache/wt/synthesis.wdf",
        "hw/SAAM/SAAM.runs/impl_1/ISEWrap.sh",
        "hw/SAAM/SAAM.hw/SAAM.lpr",
        "hw/SAAM/SAAM.ip_user_files/README.txt",
        "hw/SAAM/SAAM.sim/sim_1/behav/xsim/xsim.dir/run.sh",
        "hw/SAAM/SAAM.gen/sources_1/bd/bringup/hdl/bringup.vhd",
        "hw/SAAM/SAAM.srcs/sources_1/bd/bringup/bringup.bd",
        "hw/another_name/other.xpr",
        "hw/vivado/project/zybo.runs/synth_1/runme.sh",
    ],
)
def test_a_vivado_project_made_by_hand_is_never_versioned(path: str) -> None:
    """AUD-114: the project the user creates with the board (build.tcl opens it) holds caches,
    logs, shell scripts (which the executable-bit test would then require) and machine paths.
    Whatever its name and its folder under hw/, it is ignored."""
    assert _ignored(path), path


@pytest.mark.parametrize(
    "path",
    [
        "hw/rtl/axil_reg_bringup.vhd",
        "hw/vivado/build.tcl",
        "hw/ps_app/bringup/hello.c",
        "hw/ps_app/bringup/build_app.py",
        "hw/reports/bringup-utilization.rpt",
        "hw/reports/bringup-environment.json",
        "hw/host/tests/test_bringup.py",
        "hw/sim/Makefile",
        "hw/BRINGUP.md",
    ],
)
def test_the_sources_and_the_reports_of_the_hardware_part_stay_versioned(
    path: str,
) -> None:
    assert not _ignored(path), path


# --------------------------------------------------------------------------------------------
# build_app.py: XSA -> platform, FSBL, hello application, BOOT.bin (Vitis Unified)
# --------------------------------------------------------------------------------------------


class FakeComponent:
    """A Vitis component that writes the files the real build would."""

    def __init__(
        self, calls: list[tuple[str, ...]], workspace: Path, name: str
    ) -> None:
        self.calls = calls
        self.workspace = workspace
        self.name = name

    def build(self) -> None:
        self.calls.append(("build", self.name))
        if self.name == "bringup_plat":
            target = (
                self.workspace / "bringup_plat" / "export" / "sw" / "boot" / "fsbl.elf"
            )
        else:
            target = self.workspace / "hello" / "build" / "hello.elf"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"elf")

    def import_files(self, **kwargs: object) -> None:
        files = [str(name) for name in kwargs["files"]]  # type: ignore[attr-defined]
        self.calls.append(("import_files", str(kwargs["from_loc"]), *files))


class FakeClient:
    def __init__(self, calls: list[tuple[str, ...]]) -> None:
        self.calls = calls
        self.workspace = Path()

    def set_workspace(self, path: str) -> None:
        self.workspace = Path(path)
        self.calls.append(("set_workspace", path))

    def create_platform_component(self, **kwargs: object) -> FakeComponent:
        self.calls.append(
            ("create_platform_component", *(f"{k}={v}" for k, v in kwargs.items()))
        )
        return FakeComponent(self.calls, self.workspace, "bringup_plat")

    def find_platform_in_repos(self, name: str) -> str:
        self.calls.append(("find_platform_in_repos", name))
        return f"/xpfm/{name}.xpfm"

    def create_app_component(self, **kwargs: object) -> FakeComponent:
        self.calls.append(
            ("create_app_component", *(f"{k}={v}" for k, v in kwargs.items()))
        )
        return FakeComponent(self.calls, self.workspace, "hello")


def _xsa(directory: Path, *, bitstream: bool) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "bringup.xsa"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("sysdef.xml", "<xml/>")
        if bitstream:
            archive.writestr("bringup_wrapper.bit", b"bit")
    return path


@pytest.fixture
def app_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    """build_app.py with a fake `vitis` module and a fake `bootgen`; returns the module, the calls
    and the build directory. A mock of the tools: nothing here is a result of Vitis."""
    calls: list[tuple[str, ...]] = []
    fake = types.ModuleType("vitis")
    fake.create_client = lambda: FakeClient(calls)  # type: ignore[attr-defined]
    fake.dispose = lambda: calls.append(("dispose",))  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "vitis", fake)
    monkeypatch.setenv("SAAM_HW_BUILD_DIR", str(tmp_path / "out"))

    def fake_run(command: list[str], **kwargs: object) -> object:
        calls.append(("run", *command))
        (Path(str(kwargs["cwd"])) / "BOOT.bin").write_bytes(b"boot")
        return types.SimpleNamespace(returncode=0)

    spec = importlib.util.spec_from_file_location("build_app", APP_PY)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module.subprocess, "run", fake_run)
    return module, calls, tmp_path / "out"


def test_the_app_script_builds_the_platform_and_the_hello_app_from_the_xsa(
    app_run,
) -> None:  # type: ignore[no-untyped-def]
    module, calls, out = app_run
    _xsa(out, bitstream=True)

    module.main()

    platform = next(c for c in calls if c[0] == "create_platform_component")
    assert f"hw_design={out / 'bringup.xsa'}" in platform
    assert "cpu=ps7_cortexa9_0" in platform and "os=standalone" in platform
    app = next(c for c in calls if c[0] == "create_app_component")
    assert "template=empty_application" in app
    assert "domain=standalone_ps7_cortexa9_0" in app
    imported = next(c for c in calls if c[0] == "import_files")
    assert imported[1] == str(APP_DIR) and imported[2] == "hello.c"
    # The platform (and with it the first stage loader) is built before the application.
    assert [c[1] for c in calls if c[0] == "build"] == ["bringup_plat", "hello"]
    assert ("dispose",) in calls


def test_the_app_script_writes_the_boot_image_with_bootgen(app_run) -> None:  # type: ignore[no-untyped-def]
    module, calls, out = app_run
    _xsa(out, bitstream=True)

    module.main()

    boot = out / "boot"
    run = next(c for c in calls if c[0] == "run")
    assert run[1:] == (
        "bootgen",
        "-arch",
        "zynq",
        "-image",
        "boot.bif",
        "-w",
        "-o",
        "BOOT.bin",
    )
    assert (boot / "BOOT.bin").is_file()
    bif = (boot / "boot.bif").read_text(encoding="utf-8")
    # The first stage loader first, then the bitstream, then the application.
    assert bif.index("fsbl.elf") < bif.index(".bit") < bif.index("hello.elf")
    assert "[bootloader]" in bif
    for name in ("fsbl.elf", "hello.elf", "bringup_wrapper.bit"):
        assert (boot / name).is_file(), name


def test_the_app_script_stops_without_an_xsa(app_run) -> None:  # type: ignore[no-untyped-def]
    module, calls, _out = app_run
    with pytest.raises(SystemExit):
        module.main()
    assert not [c for c in calls if c[0] == "create_platform_component"]


def test_the_app_script_stops_when_the_xsa_has_no_bitstream(app_run) -> None:  # type: ignore[no-untyped-def]
    module, calls, out = app_run
    _xsa(out, bitstream=False)

    with pytest.raises(SystemExit):
        module.main()
    assert not [c for c in calls if c[0] == "run"]


def test_the_vitis_client_is_closed_even_when_a_build_fails(  # type: ignore[no-untyped-def]
    app_run, monkeypatch: pytest.MonkeyPatch
) -> None:
    module, calls, out = app_run
    _xsa(out, bitstream=True)

    def broken(self: FakeComponent) -> None:
        raise RuntimeError("build failed")

    monkeypatch.setattr(FakeComponent, "build", broken)
    with pytest.raises(RuntimeError):
        module.main()
    assert ("dispose",) in calls


# --------------------------------------------------------------------------------------------
# The PL register
# --------------------------------------------------------------------------------------------

VHDL = REG_VHD.read_text(encoding="utf-8") if REG_VHD.exists() else ""


def test_the_register_is_an_axi4_lite_slave_with_the_ports_of_the_architecture() -> (
    None
):
    assert re.search(r"entity\s+axil_reg_bringup\s+is", VHDL, re.IGNORECASE)
    for port in (
        "aclk", "aresetn",
        "s_axi_awaddr", "s_axi_awprot", "s_axi_awvalid", "s_axi_awready",
        "s_axi_wdata", "s_axi_wstrb", "s_axi_wvalid", "s_axi_wready",
        "s_axi_bresp", "s_axi_bvalid", "s_axi_bready",
        "s_axi_araddr", "s_axi_arprot", "s_axi_arvalid", "s_axi_arready",
        "s_axi_rdata", "s_axi_rresp", "s_axi_rvalid", "s_axi_rready",
    ):  # fmt: skip
        assert re.search(rf"\b{port}\b", VHDL), port


def test_the_register_follows_the_conventions_of_the_hardware_part() -> None:
    lowered = VHDL.lower()
    assert "ieee.numeric_std" in lowered
    for banned in ("std_logic_arith", "std_logic_unsigned", "unisim", "xpm"):
        assert banned not in lowered, banned
    # One clock, synchronous active-low reset.
    assert len(re.findall(r"rising_edge\s*\(", lowered)) == 1
    assert "rising_edge(aclk)" in lowered
    assert "aresetn = '0'" in lowered
    assert "falling_edge" not in lowered
    assert "wait for" not in lowered


def test_the_register_tells_vivado_which_clock_and_reset_belong_to_the_bus() -> None:
    assert "ASSOCIATED_BUSIF s_axi" in VHDL
    assert "ASSOCIATED_RESET aresetn" in VHDL


# --------------------------------------------------------------------------------------------
# The PS application, compiled with the ARM compiler against the real driver headers
# --------------------------------------------------------------------------------------------


def _vitis() -> Path | None:
    for variable in ("SAAM_VITIS_DIR", "XILINX_VITIS"):
        value = os.environ.get(variable, "").strip()
        if value and (Path(value) / "data" / "embeddedsw").is_dir():
            return Path(value)
    return None


def _newest(directory: Path, prefix: str) -> Path:
    return max(
        directory.glob(f"{prefix}_v*"),
        key=lambda p: [int(x) for x in re.findall(r"\d+", p.name)],
    )


def _compiler(vitis: Path) -> str | None:
    found = shutil.which("arm-none-eabi-gcc")
    if found:
        return found
    for candidate in (
        vitis.parent / "gnu" / "aarch32" / "nt" / "gcc-arm-none-eabi" / "bin",
        vitis.parent / "gnu" / "aarch32" / "lin" / "gcc-arm-none-eabi" / "bin",
    ):
        for name in ("arm-none-eabi-gcc.exe", "arm-none-eabi-gcc"):
            if (candidate / name).is_file():
                return str(candidate / name)
    return None


@pytest.mark.parametrize("sdt", [False, True], ids=["device-id-api", "sdt-api"])
def test_the_ps_app_compiles_against_the_real_uart_driver(
    tmp_path: Path, sdt: bool
) -> None:
    vitis = _vitis()
    if vitis is None:
        pytest.skip("no Vitis installation (set XILINX_VITIS or SAAM_VITIS_DIR)")
    compiler = _compiler(vitis)
    if compiler is None:
        pytest.skip("no arm-none-eabi-gcc")
    sw = vitis / "data" / "embeddedsw"
    standalone = _newest(sw / "lib" / "bsp", "standalone") / "src"
    uart = _newest(sw / "XilinxProcessorIPLib" / "drivers", "uartps") / "src"
    # Generated by the BSP in a real build: the two values the application reads.
    (tmp_path / "xparameters.h").write_text(
        "#define XPAR_XUARTPS_0_DEVICE_ID 0\n"
        "#define XPAR_XUARTPS_0_BASEADDR 0xE0001000\n"
        "#define XPAR_CPU_ID 0U\n#define XPAR_PS7_CORTEXA9_0_CPU_CLK_FREQ_HZ 666666687\n",
        encoding="utf-8",
    )
    (tmp_path / "bspconfig.h").write_text(
        "#define MICROBLAZE_PM_ENABLED 0\n", encoding="utf-8"
    )
    command = [
        compiler, "-fsyntax-only", "-std=gnu11", "-Wall", "-Wextra", "-Werror",
        "-mcpu=cortex-a9", "-I", str(tmp_path),
        "-I", str(standalone / "common"), "-I", str(standalone / "arm" / "cortexa9"),
        "-I", str(standalone / "arm" / "common" / "gcc"),
        "-I", str(standalone / "arm" / "common"), "-I", str(uart),
        *(["-DSDT"] if sdt else []), str(HELLO_C),
    ]  # fmt: skip
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr[-2500:]


def test_the_ps_app_answers_the_commands_the_host_test_sends() -> None:
    source = HELLO_C.read_text(encoding="utf-8")
    for token in (
        "hello SAAM-BRINGUP",
        "case 'H'",
        "case 'W'",
        "case 'R'",
        "case 'B'",
        "case 'E'",
    ):
        assert token in source, token
    assert "115200" in source and "921600" in source
    # A bring-up console, not the protocol of IF-14: no frame start, no CRC.
    assert "0xA5" not in source
    assert "crc" not in source.lower()
