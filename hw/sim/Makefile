# Simulation of the hardware cores (hw/rtl). T3.18: sha256_core and sha256_padder.
# T3.19 (1/2): fir_decim.
#
#   make -C hw/sim            the best simulator that is installed (below)
#   make -C hw/sim cocotb     GHDL + cocotb: core, padder, fir_decim, then both AXI slaves
#   make -C hw/sim xsim       Vivado xsim: the self-checking VHDL testbench sha256_core_tb.vhd
#   make -C hw/sim xsim-padder  Vivado xsim: sha256_padder_tb.vhd (FIPS padding, 1000 messages)
#   make -C hw/sim xsim-fir   Vivado xsim: fir_decim_tb.vhd (20 int16 signals)
#   make -C hw/sim clean
#
# The default target picks, in this order:
#   1. GHDL and cocotb, when both are installed;
#   2. Vivado xsim (xvhdl, xelab, xsim), found in SAAM_VIVADO_BIN, in $XILINX_VIVADO/bin or on PATH;
#   3. nothing: it prints SKIPPED and exits 0, so that a machine without a simulator is not red.
#      SAAM_HW_SIM_REQUIRED=1 turns that into a failure; CI (job hw-sim) sets it.
# A SKIPPED line is not a pass: nothing was simulated.
#
# T1.10 (B) adds the CI job; this file is the local flow until then.

SIM_DIR   := $(patsubst %/,%,$(dir $(abspath $(lastword $(MAKEFILE_LIST)))))
CORE      := $(SIM_DIR)/../rtl/sha256_core.vhd
TB        := $(SIM_DIR)/sha256_core_tb.vhd
PADDER    := $(SIM_DIR)/../rtl/sha256_padder.vhd
PADDER_TB := $(SIM_DIR)/sha256_padder_tb.vhd
FIR_PKG   := $(SIM_DIR)/../rtl/fir_coeffs_pkg.vhd
FIR       := $(SIM_DIR)/../rtl/fir_decim.vhd
FIR_TB    := $(SIM_DIR)/fir_decim_tb.vhd
FIR_EXT_TB := $(SIM_DIR)/fir_decim_extremes_tb.vhd
SHA_AXI   := $(SIM_DIR)/../rtl/sha256_axi.vhd
SHA_AXI_TB := $(SIM_DIR)/sha256_axi_tb.vhd
FIR_AXI   := $(SIM_DIR)/../rtl/fir_axi.vhd
FIR_AXI_TB := $(SIM_DIR)/fir_axi_tb.vhd
BUILD     := $(SIM_DIR)/build/xsim
BUILD_PADDER := $(SIM_DIR)/build/xsim-padder
BUILD_FIR := $(SIM_DIR)/build/xsim-fir
BUILD_FIR_EXT := $(SIM_DIR)/build/xsim-fir-ext
BUILD_SHA_AXI := $(SIM_DIR)/build/xsim-sha-axi
BUILD_FIR_AXI := $(SIM_DIR)/build/xsim-fir-axi

ifeq ($(OS),Windows_NT)
  BAT := .bat
endif
VIVADO_BIN := $(subst \,/,$(if $(SAAM_VIVADO_BIN),$(SAAM_VIVADO_BIN),$(if $(XILINX_VIVADO),$(XILINX_VIVADO)/bin)))
VIVADO_DIR := $(if $(VIVADO_BIN),$(VIVADO_BIN)/)
XVHDL ?= $(VIVADO_DIR)xvhdl$(BAT)
XELAB ?= $(VIVADO_DIR)xelab$(BAT)
XSIM  ?= $(VIVADO_DIR)xsim$(BAT)

HAVE_GHDL   := $(shell command -v ghdl 2>/dev/null)
HAVE_COCOTB := $(shell command -v cocotb-config 2>/dev/null)
HAVE_XSIM   := $(or $(wildcard $(XVHDL)),$(shell command -v $(XVHDL) 2>/dev/null))

.DEFAULT_GOAL := check
.PHONY: check cocotb xsim xsim-padder xsim-fir xsim-fir-ext xsim-sha-axi xsim-fir-axi clean

check:
ifneq ($(and $(HAVE_GHDL),$(HAVE_COCOTB)),)
	@$(MAKE) --no-print-directory cocotb
else ifneq ($(HAVE_XSIM),)
	@echo "GHDL + cocotb not found: running the VHDL testbenches in Vivado xsim instead."
	@$(MAKE) --no-print-directory xsim
	@$(MAKE) --no-print-directory xsim-padder
	@$(MAKE) --no-print-directory xsim-fir
	@$(MAKE) --no-print-directory xsim-fir-ext
	@$(MAKE) --no-print-directory xsim-sha-axi
	@$(MAKE) --no-print-directory xsim-fir-axi
else ifneq ($(SAAM_HW_SIM_REQUIRED),)
	@echo "FAILED: no simulator (GHDL + cocotb, or Vivado xsim) and SAAM_HW_SIM_REQUIRED is set."
	@exit 1
else
	@echo "SKIPPED: no simulator found, hw/sim was not run. Install GHDL and cocotb (ADR-12), or point"
	@echo "SAAM_VIVADO_BIN at the bin directory of Vivado to run the testbench in xsim."
endif

cocotb:
	@$(MAKE) -f $(SIM_DIR)/cocotb.mk TOPLEVEL=sha256_core MODULE=test_sha256
	@$(MAKE) -f $(SIM_DIR)/cocotb.mk TOPLEVEL=sha256_padder MODULE=test_sha256_padder
	@$(MAKE) -f $(SIM_DIR)/cocotb.mk TOPLEVEL=fir_decim MODULE=test_fir
	@$(MAKE) -f $(SIM_DIR)/cocotb.mk TOPLEVEL=sha256_axi MODULE=test_sha256_axi
	@$(MAKE) -f $(SIM_DIR)/cocotb.mk TOPLEVEL=fir_axi MODULE=test_fir_axi

xsim:
	mkdir -p $(BUILD)
	cd $(BUILD) && $(XVHDL) --2008 $(CORE) $(TB)
	cd $(BUILD) && $(XELAB) --debug off sha256_core_tb -s sha256_core_tb_sim
	cd $(BUILD) && $(XSIM) sha256_core_tb_sim -runall 2>&1 | tee xsim.log
	@grep -q "SHA256_TB PASSED" $(BUILD)/xsim.log || { echo "xsim: the testbench did not pass"; exit 1; }

xsim-padder:
	mkdir -p $(BUILD_PADDER)
	cd $(BUILD_PADDER) && $(XVHDL) --2008 $(CORE) $(PADDER) $(PADDER_TB)
	cd $(BUILD_PADDER) && $(XELAB) --debug off sha256_padder_tb -s sha256_padder_tb_sim
	cd $(BUILD_PADDER) && $(XSIM) sha256_padder_tb_sim -runall 2>&1 | tee xsim.log
	@grep -q "SHA256_PADDER_TB PASSED" $(BUILD_PADDER)/xsim.log || { echo "xsim: the padder testbench did not pass"; exit 1; }

xsim-fir:
	mkdir -p $(BUILD_FIR)
	cd $(BUILD_FIR) && $(XVHDL) --2008 $(FIR_PKG) $(FIR) $(FIR_TB)
	cd $(BUILD_FIR) && $(XELAB) --debug off fir_decim_tb -s fir_decim_tb_sim
	cd $(BUILD_FIR) && $(XSIM) fir_decim_tb_sim -runall 2>&1 | tee xsim.log
	@grep -q "FIR_DECIM_TB PASSED" $(BUILD_FIR)/xsim.log || { echo "xsim: the FIR testbench did not pass"; exit 1; }

xsim-fir-ext:
	mkdir -p $(BUILD_FIR_EXT)
	cd $(BUILD_FIR_EXT) && $(XVHDL) --2008 $(FIR_PKG) $(FIR) $(FIR_EXT_TB)
	cd $(BUILD_FIR_EXT) && $(XELAB) --debug off fir_decim_extremes_tb -s fir_decim_extremes_tb_sim
	cd $(BUILD_FIR_EXT) && $(XSIM) fir_decim_extremes_tb_sim -runall 2>&1 | tee xsim.log
	@grep -q "FIR_DECIM_EXTREMES_TB PASSED" $(BUILD_FIR_EXT)/xsim.log || { echo "xsim: the FIR extremes testbench did not pass"; exit 1; }

xsim-sha-axi:
	mkdir -p $(BUILD_SHA_AXI)
	cd $(BUILD_SHA_AXI) && $(XVHDL) --2008 $(CORE) $(PADDER) $(SHA_AXI) $(SHA_AXI_TB)
	cd $(BUILD_SHA_AXI) && $(XELAB) --debug off sha256_axi_tb -s sha256_axi_tb_sim
	cd $(BUILD_SHA_AXI) && $(XSIM) sha256_axi_tb_sim -runall 2>&1 | tee xsim.log
	@grep -q "SHA256_AXI_TB PASSED" $(BUILD_SHA_AXI)/xsim.log || { echo "xsim: the SHA-256 AXI testbench did not pass"; exit 1; }

xsim-fir-axi:
	mkdir -p $(BUILD_FIR_AXI)
	cd $(BUILD_FIR_AXI) && $(XVHDL) --2008 $(FIR_PKG) $(FIR) $(FIR_AXI) $(FIR_AXI_TB)
	cd $(BUILD_FIR_AXI) && $(XELAB) --debug off fir_axi_tb -s fir_axi_tb_sim
	cd $(BUILD_FIR_AXI) && $(XSIM) fir_axi_tb_sim -runall 2>&1 | tee xsim.log
	@grep -q "FIR_AXI_TB PASSED" $(BUILD_FIR_AXI)/xsim.log || { echo "xsim: the FIR AXI testbench did not pass"; exit 1; }

clean:
	rm -rf $(SIM_DIR)/build $(SIM_DIR)/sim_build $(SIM_DIR)/results.xml
