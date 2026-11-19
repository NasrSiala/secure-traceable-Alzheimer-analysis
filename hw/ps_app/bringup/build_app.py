"""build_app.py: Vitis side of the bring-up (T1.9, l10): XSA -> platform + FSBL + hello -> BOOT.bin.

    vitis -s hw/ps_app/bringup/build_app.py

Vitis Unified (2025.x). XSCT (`xsct`, Tcl) is still shipped in 2025.2 but its `app create` needs
the Eclipse service that 2025.2 no longer installs, so it cannot build the application there.

Needs hw/build/bringup/bringup.xsa with the bitstream (hw/vivado/build.tcl). Writes, in the same
directory (SAAM_HW_BUILD_DIR moves it):
  ws/                    the Vitis workspace (platform, hello)
  boot/boot.bif          the boot image description
  boot/BOOT.bin          the image: first stage loader, bitstream, application
BOOT.bin goes at the root of a FAT32 SD card; the board boots from it with JP5 on SD
(hw/BRINGUP.md).

Not the final application: hw/ps_app/ (T4.12) replaces hello.c and keeps this flow.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

PLATFORM = "bringup_plat"
DOMAIN = "standalone_ps7_cortexa9_0"
APP = "hello"
BIF = """the_ROM_image:
{
  [bootloader] fsbl.elf
  bringup_wrapper.bit
  hello.elf
}
"""


def build_dir() -> Path:
    here = Path(__file__).resolve().parent
    override = os.environ.get("SAAM_HW_BUILD_DIR", "").strip()
    return Path(override) if override else here.parents[1] / "build" / "bringup"


def fail(message: str) -> None:
    sys.stderr.write(f"error: {message}\n")
    raise SystemExit(1)


def extract_bitstream(xsa: Path, boot: Path) -> Path:
    """The bitstream is inside the XSA (write_hw_platform -include_bit)."""
    with zipfile.ZipFile(xsa) as archive:
        bits = [name for name in archive.namelist() if name.endswith(".bit")]
        if not bits:
            fail(f"{xsa.name} has no bitstream: run hw/vivado/build.tcl to the end")
        target = boot / "bringup_wrapper.bit"
        target.write_bytes(archive.read(bits[0]))
    return target


def first(root: Path, pattern: str) -> Path:
    found = sorted(root.rglob(pattern))
    if not found:
        fail(f"no {pattern} under {root.name}")
    return found[0]


def main() -> None:
    import vitis  # type: ignore[import-not-found]  # only in the Vitis Python environment

    out = build_dir()
    xsa = out / "bringup.xsa"
    if not xsa.is_file():
        fail(f"no {xsa}: run hw/vivado/build.tcl first")
    source = Path(__file__).resolve().parent / "hello.c"
    workspace = out / "ws"
    boot = out / "boot"
    if workspace.exists():
        shutil.rmtree(workspace)
    boot.mkdir(parents=True, exist_ok=True)

    client = vitis.create_client()
    try:
        client.set_workspace(str(workspace))
        platform = client.create_platform_component(
            name=PLATFORM,
            hw_design=str(xsa),
            os="standalone",
            cpu="ps7_cortexa9_0",
            domain_name=DOMAIN,
        )
        # Building the platform also builds the first stage loader (zynq_fsbl).
        platform.build()
        xpfm = client.find_platform_in_repos(PLATFORM)
        app = client.create_app_component(
            name=APP, platform=xpfm, domain=DOMAIN, template="empty_application"
        )
        app.import_files(from_loc=str(source.parent), files=[source.name])
        app.build()
    finally:
        vitis.dispose()

    # Relative names in the .bif: bootgen runs in the directory that holds the copies.
    shutil.copyfile(first(workspace / PLATFORM, "fsbl.elf"), boot / "fsbl.elf")
    shutil.copyfile(first(workspace / APP, "hello.elf"), boot / "hello.elf")
    extract_bitstream(xsa, boot)
    (boot / "boot.bif").write_text(BIF, encoding="utf-8")
    subprocess.run(
        ["bootgen", "-arch", "zynq", "-image", "boot.bif", "-w", "-o", "BOOT.bin"],
        cwd=boot,
        check=True,
    )
    print(f"BOOT.bin written: {boot / 'BOOT.bin'}")


if __name__ == "__main__":
    main()
