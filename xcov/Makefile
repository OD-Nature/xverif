include ../mk/npi.mk
CXX ?= g++
.PHONY: all clean
all: libexec/xcov-npi-worker
libexec/xcov-npi-worker: native/worker.cpp ../xdebug/third_party/nlohmann/json.hpp
	mkdir -p libexec
	$(CXX) -std=c++17 -O2 -Wall -Wextra $(NPI_CXXFLAGS) -I../xdebug/third_party $< -o $@ $(NPI_LDFLAGS) -pthread
clean:
	rm -f libexec/xcov-npi-worker
