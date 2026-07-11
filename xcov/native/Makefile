TOP ?= ../..

include $(TOP)/mk/npi.mk

CXX ?= g++
TARGET := xcov-npi-worker
SRC := xcov-npi-worker.cpp
JSON_INC := $(TOP)/xdebug/third_party

CXXFLAGS += -std=c++17 -O2 -Wall -Wextra -Wpedantic \
	$(NPI_CXXFLAGS) -I$(JSON_INC)
NPI_RPATH := -Wl,-rpath,$(NPI_LIB)
LDFLAGS += $(NPI_LDFLAGS) $(NPI_RPATH) -lstdc++fs

all: $(TARGET)

$(TARGET): $(SRC)
	$(CXX) $(CXXFLAGS) -o $@ $< $(LDFLAGS)

clean:
	rm -f $(TARGET)

.PHONY: all clean
