# T1.10 : amorcer cocotb dans l'environnement Python verrouillé du dépôt.
ROOT := $(abspath ../..)
TEST ?= smoke

ifeq ($(SAAM_COCOTB_ACTIVE),1)
ifneq ($(TEST),smoke)
$(error Banc inconnu : $(TEST). Seul smoke est disponible dans T1.10)
endif

SIM := ghdl
TOPLEVEL_LANG := vhdl
VHDL_SOURCES := $(CURDIR)/fixtures/ci_register.vhd
COCOTB_TOPLEVEL := ci_register
COCOTB_TEST_MODULES := test_smoke
GHDL_ARGS += --std=08
SIM_BUILD ?= sim_build/$(TEST)
export PYTHONPATH := $(ROOT):$(PYTHONPATH)

include $(shell cocotb-config --makefiles)/Makefile.sim
else
.PHONY: all
all:
	cd "$(ROOT)" && uv run --locked $(MAKE) -C hw/sim SAAM_COCOTB_ACTIVE=1 TEST="$(TEST)"
endif
