# GHDL + cocotb run of the hardware cores (ADR-12). Called by `make -C hw/sim cocotb`.
#
# Needs GHDL (>= 3.0, VHDL-2008) and cocotb on the machine: `pip install cocotb`, and `cocotb-config`
# on PATH. Not run on the machine where l11 was written (neither tool was installed there): the
# reference run there is the VHDL testbench in Vivado xsim (`make -C hw/sim xsim`).

SIM ?= ghdl
TOPLEVEL_LANG ?= vhdl

SIM_DIR := $(patsubst %/,%,$(dir $(abspath $(lastword $(MAKEFILE_LIST)))))

# `make cocotb` passes TOPLEVEL and MODULE: sha256_core / test_sha256, then the padder,
# then fir_decim / test_fir, then sha256_axi / test_sha256_axi and fir_axi / test_fir_axi.
TOPLEVEL ?= sha256_core
MODULE ?= test_sha256

ifeq ($(TOPLEVEL),sha256_padder)
  VHDL_SOURCES := $(SIM_DIR)/../rtl/sha256_core.vhd $(SIM_DIR)/../rtl/sha256_padder.vhd
else ifeq ($(TOPLEVEL),sha256_axi)
  VHDL_SOURCES := $(SIM_DIR)/../rtl/sha256_core.vhd $(SIM_DIR)/../rtl/sha256_padder.vhd $(SIM_DIR)/../rtl/sha256_axi.vhd
else ifeq ($(TOPLEVEL),fir_decim)
  VHDL_SOURCES := $(SIM_DIR)/../rtl/fir_coeffs_pkg.vhd $(SIM_DIR)/../rtl/fir_decim.vhd
else ifeq ($(TOPLEVEL),fir_axi)
  VHDL_SOURCES := $(SIM_DIR)/../rtl/fir_coeffs_pkg.vhd $(SIM_DIR)/../rtl/fir_decim.vhd $(SIM_DIR)/../rtl/fir_axi.vhd
else
  VHDL_SOURCES := $(SIM_DIR)/../rtl/sha256_core.vhd
endif

# cocotb 2.x names, then the 1.x ones.
COCOTB_TOPLEVEL := $(TOPLEVEL)
COCOTB_TEST_MODULES := $(MODULE)

# The bench imports sha_support.py from this directory. Windows Python splits PYTHONPATH on ';'.
ifeq ($(OS),Windows_NT)
  PYSEP := ;
else
  PYSEP := :
endif
export PYTHONPATH := $(SIM_DIR)$(if $(PYTHONPATH),$(PYSEP)$(PYTHONPATH))

COMPILE_ARGS += --std=08
GHDL_ARGS += --std=08

SIM_BUILD := $(SIM_DIR)/sim_build/$(TOPLEVEL)
COCOTB_RESULTS_FILE := $(SIM_DIR)/results.xml

include $(shell cocotb-config --makefiles)/Makefile.sim
