.PHONY: all native test fixture self-test self-test-2018 self-test-2023 clean

PYTHON ?= python3
NATIVE_DIR := native

all:
	@if [ "$(XVERIF_EDA_PROFILE)" = "verdi-2018" ] || \
	   { [ -z "$(XVERIF_EDA_PROFILE)" -o "$(XVERIF_EDA_PROFILE)" = "auto" ] && echo "$(VERDI_HOME)" | grep -q 2018; }; then \
		$(MAKE) -C $(NATIVE_DIR); \
	else \
		echo "xcov: Python NPI backend selected; native worker build skipped"; \
	fi

native:
	$(MAKE) -C $(NATIVE_DIR)

test:
	PYTHONPATH=. $(PYTHON) -m pytest tests

fixture:
	$(MAKE) -C testdata/basic_coverage fixture

self-test: all test fixture
	@case "$(XVERIF_EDA_PROFILE)" in \
		verdi-2018) worker=npi_native_2018 ;; \
		verdi-2023) worker=npi_python ;; \
		*) echo "ERROR: self-test requires explicit XVERIF_EDA_PROFILE=verdi-2018 or verdi-2023" >&2; exit 1 ;; \
	esac; \
	PYTHONPATH=. $(PYTHON) tests/real_vdb_smoke.py \
		testdata/basic_coverage/out/simv.vdb --expected-worker "$$worker"

self-test-2018:
	$(MAKE) self-test XVERIF_EDA_PROFILE=verdi-2018

self-test-2023:
	$(MAKE) self-test XVERIF_EDA_PROFILE=verdi-2023

clean:
	$(MAKE) -C $(NATIVE_DIR) clean
	$(MAKE) -C testdata/basic_coverage clean
