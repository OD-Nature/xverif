PYTHON ?= $(shell if [ -x "$(HOME)/miniconda3/bin/python" ]; then echo "$(HOME)/miniconda3/bin/python"; else echo python3; fi)
PYTHONPATH := $(CURDIR)

.PHONY: all clean

all:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m compileall -q xsva

clean:
	find xsva tests -type d -name __pycache__ -prune -exec rm -rf {} +
	rm -rf .pytest_cache
