#!/usr/bin/env bash
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STAMP="$(date +%Y%m%d_%H%M%S)"
LOG_ROOT="${XDEBUG_REGRESSION_LOG_DIR:-/tmp/xdebug_full_regression_${STAMP}}"
SUMMARY="$LOG_ROOT/summary.txt"
XDEBUG="$ROOT/tools/xdebug"

mkdir -p "$LOG_ROOT"
: >"$SUMMARY"
pass_count=0
fail_count=0
skip_count=0

log_line() {
    printf '%s\n' "$*" | tee -a "$SUMMARY"
}

record() {
    local status="$1"
    local name="$2"
    local log="$3"
    case "$status" in
        PASS) pass_count=$((pass_count + 1)) ;;
        FAIL) fail_count=$((fail_count + 1)) ;;
        SKIP) skip_count=$((skip_count + 1)) ;;
    esac
    log_line "[$status] $name :: $log"
}

run_case() {
    local name="$1"
    shift
    local log="$LOG_ROOT/${name//[^A-Za-z0-9_.-]/_}.log"
    log_line ""
    log_line "===== RUN $name ====="
    (cd "$ROOT" && "$@") >"$log" 2>&1
    local rc=$?
    if [[ $rc -eq 0 ]]; then
        record PASS "$name" "$log"
    else
        record FAIL "$name" "$log"
        tail -40 "$log" | sed 's/^/  | /' | tee -a "$SUMMARY"
    fi
    return $rc
}

skip_case() {
    local name="$1"
    local reason="$2"
    local log="$LOG_ROOT/${name}.log"
    printf 'SKIP: %s\n' "$reason" >"$log"
    record SKIP "$name" "$log"
}

build_uart_fixture() {
    local dir="$ROOT/xdebug/testdata/design/uart"
    local log="$LOG_ROOT/build_design_uart.log"
    (cd "$dir" && vcs -full64 -sverilog -kdb -debug_access+all -f dut.f -top uart_16550 -o simv) >"$log" 2>&1
    if [[ $? -eq 0 && -d "$dir/simv.daidir" ]]; then
        record PASS "build_design_uart" "$log"
    else
        record FAIL "build_design_uart" "$log"
        tail -40 "$log" | sed 's/^/  | /' | tee -a "$SUMMARY"
    fi
}

main() {
    log_line "xdebug full regression"
    log_line "root: $ROOT"
    log_line "logs: $LOG_ROOT"
    log_line "date: $(date)"

    run_case build_all make clean all
    run_case unit_test make -C xdebug unit-test
    run_case build_active_driver make -C xdebug/testdata/combined/active_driver fixture
    run_case api_and_combined regression/run_xdebug_regression.sh

    if command -v vcs >/dev/null 2>&1; then
        build_uart_fixture
        run_case design_semantics bash xdebug/tests/design/run_semantics.sh
        run_case waveform_complex python3 xdebug/tests/waveform/run_complex_wave.py --xdebug "$XDEBUG" --mode nonaxi
    else
        skip_case design_semantics "vcs not found"
        skip_case waveform_complex "vcs not found"
    fi

    if [[ -f /home/yian/xif_agent/src/xif_pkg.sv ]] && command -v vcs >/dev/null 2>&1; then
        run_case waveform_event make -C xdebug/testdata/waveform/xif_agent_event check XDEBUG="$XDEBUG"
    else
        skip_case waveform_event "xif_agent xif_pkg.sv dependency or vcs missing"
    fi

    if [[ -f /home/yian/axi_test/test/sim_run/tb.fsdb ]]; then
        run_case realdata_axi python3 xdebug/tests/waveform/run_complex_wave.py --xdebug "$XDEBUG" --mode axi --skip-build
    else
        skip_case realdata_axi "AXI FSDB not found"
    fi
    if [[ -f /home/yian/wave_tmp/waves.fsdb && -f "$ROOT/xdebug/tests/realdata/run_system_wave.py" ]]; then
        run_case realdata_system_wave python3 xdebug/tests/realdata/run_system_wave.py
    else
        skip_case realdata_system_wave "system FSDB or runner not found"
    fi

    log_line ""
    log_line "===== SUMMARY ====="
    log_line "PASS: $pass_count"
    log_line "SKIP: $skip_count"
    log_line "FAIL: $fail_count"
    log_line "summary: $SUMMARY"
    [[ $fail_count -eq 0 ]]
}

main "$@"
