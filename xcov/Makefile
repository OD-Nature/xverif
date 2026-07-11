.PHONY: all native clean

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

clean:
	$(MAKE) -C $(NATIVE_DIR) clean
