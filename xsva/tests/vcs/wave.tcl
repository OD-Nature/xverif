# UCLI script for xsva VCS test
# Dump FSDB waveform and log assertion status

call {$fsdbDumpvars(0,"xsva_vcs_tb","+all")}
run
quit
