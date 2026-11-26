# GHDL + cocotb run of the hardware cores (ADR-12). Called by `make -C hw/sim cocotb`.
#
# Needs GHDL (>= 3.0, VHDL-2008) and cocotb on the machine: `pip install cocotb`, and `cocotb-config`
# on PATH. Not run on the machine where l11 was written (neither tool was installed there): the
# reference run there is the VHDL testbench in Vivado xsim (`make -C hw/sim xsim`).

SIM ?= ghdl
TOPLEVEL_LANG ?= vhdl

SIM_DIR := $(patsubst %/,%,$(dir $(abspath $(lastword $(MAKEFILE_LIST)))))

ifeq ($(TEST),smoke)
VHDL_SOURCES := $(SIM_DIR)/fixtures/ci_register.vhd
COCOTB_TOPLEVEL := ci_register
COCOTB_TEST_MODULES := test_smoke
TOPLEVEL := ci_register
MODULE := test_smoke
else ifeq ($(TEST),sha256)
VHDL_SOURCES := $(SIM_DIR)/../rtl/sha256_core.vhd

# cocotb 2.x names, then the 1.x ones.
COCOTB_TOPLEVEL := sha256_core
COCOTB_TEST_MODULES := test_sha256
TOPLEVEL := sha256_core
MODULE := test_sha256
else
$(error Banc inconnu : $(TEST))
endif

# The bench imports sha_support.py from this directory. Windows Python splits PYTHONPATH on ';'.
ifeq ($(OS),Windows_NT)
  PYSEP := ;
else
  PYSEP := :
endif
export PYTHONPATH := $(SIM_DIR)$(PYSEP)$(abspath $(SIM_DIR)/../..)$(if $(PYTHONPATH),$(PYSEP)$(PYTHONPATH))

COMPILE_ARGS += --std=08
GHDL_ARGS += --std=08

SIM_BUILD := $(SIM_DIR)/sim_build/$(TEST)
COCOTB_RESULTS_FILE := $(SIM_DIR)/results.xml

include $(shell cocotb-config --makefiles)/Makefile.sim
