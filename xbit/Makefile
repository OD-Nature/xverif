PYTHON ?= python3
PYTHONPATH := $(CURDIR)/src

.PHONY: all clean

all:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m compileall -q src

clean:
	find src tests -type d -name __pycache__ -prune -exec rm -rf {} +
	rm -rf build dist *.egg-info
