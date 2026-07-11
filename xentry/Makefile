PYTHON ?= $(shell if [ -x "$(HOME)/miniconda3/bin/python" ]; then echo "$(HOME)/miniconda3/bin/python"; else echo python3; fi)
PYTHONPATH := $(CURDIR)/src

.PHONY: all clean

all:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m compileall -q src

clean:
	find src tests -type d -name __pycache__ -prune -exec rm -rf {} +
