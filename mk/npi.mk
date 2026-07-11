VERDI_HOME ?= $(shell echo $$VERDI_HOME)

ifeq ($(VERDI_HOME),)
$(error VERDI_HOME environment variable is not set)
endif

XVERIF_EDA_PROFILE ?= auto

ifeq ($(XVERIF_EDA_PROFILE),auto)
ifneq ($(findstring 2018,$(VERDI_HOME)),)
XVERIF_EDA_PROFILE_RESOLVED := verdi-2018
else
# Preserve the upstream behavior for modern Verdi installs and versionless
# VERDI_HOME symlinks. Verdi 2018 remains explicitly selectable.
XVERIF_EDA_PROFILE_RESOLVED := verdi-2023
endif
else
XVERIF_EDA_PROFILE_RESOLVED := $(XVERIF_EDA_PROFILE)
endif

ifneq ($(filter $(XVERIF_EDA_PROFILE_RESOLVED),verdi-2018 verdi-2023),$(XVERIF_EDA_PROFILE_RESOLVED))
$(error unsupported XVERIF_EDA_PROFILE '$(XVERIF_EDA_PROFILE)'; expected auto, verdi-2018, or verdi-2023)
endif

NPI_INC       = $(VERDI_HOME)/share/NPI/inc
NPI_L1_INC    = $(VERDI_HOME)/share/NPI/L1/C/inc
NPI_LIB_UPPER = $(VERDI_HOME)/share/NPI/lib/LINUX64
NPI_LIB_LOWER = $(VERDI_HOME)/share/NPI/lib/linux64
NPI_LIB       = $(if $(wildcard $(NPI_LIB_UPPER)),$(NPI_LIB_UPPER),$(NPI_LIB_LOWER))

NPI_CXXFLAGS = -I$(NPI_INC) -I$(NPI_L1_INC)
NPI_LDFLAGS  = -L$(NPI_LIB) -Wl,-rpath-link,$(NPI_LIB) -lNPI -lnpiL1 -ldl -lrt -lz

ifeq ($(XVERIF_EDA_PROFILE_RESOLVED),verdi-2018)
NPI_CXXFLAGS += -D_GLIBCXX_USE_CXX11_ABI=0 -DXVERIF_VERDI_2018=1
endif
