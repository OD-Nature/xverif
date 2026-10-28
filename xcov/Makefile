include ../mk/npi.mk
CXX ?= g++
.PHONY: all clean FORCE
SDK_HOME := $(realpath $(VERDI_HOME))
SDK_LIBRARY := $(NPI_LIB)/libNPI.so
SDK_SIZE := $(shell stat -Lc %s '$(SDK_LIBRARY)')
SDK_MTIME := $(shell stat -Lc %Y '$(SDK_LIBRARY)')
all: libexec/xcov-npi-worker
libexec/xcov-npi-worker: src/npi_worker.cpp Makefile ../mk/npi.mk ../xdebug/third_party/nlohmann/json.hpp libexec/.sdk-build $(NPI_INC)/npi.h $(NPI_INC)/npi_cov.h $(SDK_LIBRARY)
	mkdir -p libexec
	$(CXX) -std=c++11 -O2 -Wall -Wextra -MMD -MP -MF libexec/xcov-npi-worker.d $(NPI_CXXFLAGS) -I../xdebug/third_party \
		-DXCOV_SDK_HOME='"$(SDK_HOME)"' -DXCOV_NPI_SIZE=$(SDK_SIZE) -DXCOV_NPI_MTIME=$(SDK_MTIME) \
		$< -o $@ $(NPI_LDFLAGS) -pthread
libexec/.sdk-build: FORCE
	@mkdir -p libexec
	@printf '%s\n' '$(SDK_HOME)' '$(SDK_SIZE):$(SDK_MTIME)' '$(CXX) $(NPI_CXXFLAGS) $(NPI_LDFLAGS)' > $@.tmp
	@cmp -s $@.tmp $@ || mv $@.tmp $@
	@rm -f $@.tmp
FORCE:
clean:
	rm -f libexec/xcov-npi-worker libexec/xcov-npi-worker.d libexec/.sdk-build
-include libexec/xcov-npi-worker.d
