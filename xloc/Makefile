PYTHON ?= python3
PYTHONPATH := $(CURDIR)

.PHONY: all clean

all:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m compileall -q xloc

clean:
	find xloc tests -type d -name __pycache__ -prune -exec rm -rf {} +
	find xloc tests -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
