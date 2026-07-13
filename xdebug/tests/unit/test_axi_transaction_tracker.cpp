#include "waveform/axi/axi_transaction_tracker.h"

#include <cassert>
#include <cstdint>
#include <iostream>
#include <random>

using namespace xdebug_waveform;

namespace {

AxiSample aw(npiFsdbTime time, const char* id = "1", const char* len = "0") {
    AxiSample s;
    s.time = time;
    s.aw_handshake = true;
    s.awid = id;
    s.awaddr = "100";
    s.awlen = len;
    s.awsize = "3";
    s.awburst = "1";
    return s;
}

AxiSample w(npiFsdbTime time, bool last = true) {
    AxiSample s;
    s.time = time;
    s.w_handshake = true;
    s.wlast = last;
    s.wdata = "55";
    s.wstrb = "ff";
    return s;
}

AxiSample b(npiFsdbTime time, const char* id = "1") {
    AxiSample s;
    s.time = time;
    s.b_handshake = true;
    s.bid = id;
    s.bresp = "0";
    return s;
}

void test_aw_before_w_without_later_aw() {
    AxiTransactionTracker tracker;
    tracker.consume(aw(10));
    tracker.consume(w(20));
    tracker.consume(b(30));
    AxiResult result = tracker.finish(0, 40);
    assert(result.writes.size() == 1);
    assert(result.writes[0].phase_order == "aw_before_w");
    assert(result.writes[0].addr_time == 10);
    assert(result.writes[0].first_data_time == 20);
    assert(result.diagnostics.final_write_outstanding == 0);
    assert(result.diagnostics.incomplete_write_count == 0);
}

void test_multiple_w_bursts_before_aw() {
    AxiTransactionTracker tracker;
    tracker.consume(w(10));
    tracker.consume(w(20));
    tracker.consume(aw(30, "1"));
    tracker.consume(aw(40, "2"));
    tracker.consume(b(50, "2"));
    tracker.consume(b(60, "1"));
    AxiResult result = tracker.finish(0, 70);
    assert(result.writes.size() == 2);
    assert(result.writes[0].id == "1");
    assert(result.writes[0].first_data_time == 10);
    assert(result.writes[0].phase_order == "w_before_aw");
    assert(result.writes[1].id == "2");
    assert(result.writes[1].first_data_time == 20);
    assert(result.writes[1].phase_order == "w_before_aw");
    assert(result.diagnostics.orphan_b_count == 0);
}

void test_same_cycle_and_dependency_violation() {
    AxiTransactionTracker tracker;
    AxiSample sample = aw(10);
    sample.w_handshake = true;
    sample.wlast = true;
    sample.wdata = "aa";
    sample.wstrb = "ff";
    tracker.consume(sample);
    tracker.consume(b(20));
    AxiResult result = tracker.finish(0, 20);
    assert(result.writes.size() == 1);
    assert(result.writes[0].phase_order == "same_cycle");
    assert(!result.writes[0].response_dependency_violation);

    AxiTransactionTracker invalid;
    AxiSample all = aw(10);
    all.w_handshake = true;
    all.wlast = true;
    all.wdata = "aa";
    all.wstrb = "ff";
    all.b_handshake = true;
    all.bid = "1";
    all.bresp = "0";
    invalid.consume(all);
    AxiResult invalid_result = invalid.finish(0, 10);
    assert(invalid_result.writes.size() == 1);
    assert(invalid_result.writes[0].response_dependency_violation);
    assert(invalid_result.diagnostics.response_dependency_violation_count == 1);
}

void test_multibeat_before_aw_and_pending_diagnostics() {
    AxiTransactionTracker tracker;
    tracker.consume(w(10, false));
    tracker.consume(w(20, false));
    tracker.consume(w(30, false));
    tracker.consume(w(40, true));
    tracker.consume(aw(50, "3", "3"));
    tracker.consume(b(60, "3"));
    tracker.consume(aw(70, "4"));
    tracker.consume(w(80));
    AxiResult result = tracker.finish(0, 90);
    assert(result.writes.size() == 1);
    assert(result.writes[0].data.size() == 4);
    assert(result.writes[0].last_data_time < result.writes[0].addr_time);
    assert(result.pending_writes.size() == 1);
    assert(result.pending_writes[0].id == "4");
    assert(result.diagnostics.incomplete_write_count == 1);
    assert(result.diagnostics.final_write_outstanding == 1);
}

void test_reset_and_orphans() {
    AxiTransactionTracker tracker;
    tracker.consume(aw(10));
    tracker.consume(w(20));
    AxiSample reset;
    reset.time = 30;
    reset.reset_active = true;
    tracker.consume(reset);
    tracker.consume(b(40));
    AxiSample orphan_r;
    orphan_r.time = 50;
    orphan_r.r_handshake = true;
    orphan_r.rid = "2";
    orphan_r.rlast = true;
    tracker.consume(orphan_r);
    AxiResult result = tracker.finish(0, 60);
    assert(result.diagnostics.reset_cleared_write_count == 1);
    assert(result.diagnostics.orphan_b_count == 1);
    assert(result.diagnostics.orphan_r_beat_count == 1);
}

void test_fixed_seed_schedules() {
    for (uint32_t seed : {7u, 19u, 73u}) {
        std::mt19937 random(seed);
        AxiTransactionTracker tracker;
        npiFsdbTime time = 10;
        size_t expected_aw_first = 0;
        size_t expected_same = 0;
        size_t expected_w_first = 0;
        for (int i = 0; i < 128; ++i) {
            const int relation = i < 3 ? i : static_cast<int>(random() % 3);
            const std::string id = std::to_string(random() % 8);
            if (relation == 0) {
                tracker.consume(aw(time, id.c_str()));
                tracker.consume(w(time + 2));
                ++expected_aw_first;
            } else if (relation == 1) {
                AxiSample both = aw(time, id.c_str());
                both.w_handshake = true;
                both.wlast = true;
                both.wdata = "1";
                both.wstrb = "ff";
                tracker.consume(both);
                ++expected_same;
            } else {
                tracker.consume(w(time));
                tracker.consume(aw(time + 2, id.c_str()));
                ++expected_w_first;
            }
            tracker.consume(b(time + 4, id.c_str()));
            time += 10;
        }
        AxiResult result = tracker.finish(0, time);
        size_t aw_first = 0, same = 0, w_first = 0;
        for (const auto& txn : result.writes) {
            aw_first += txn.phase_order == "aw_before_w";
            same += txn.phase_order == "same_cycle";
            w_first += txn.phase_order == "w_before_aw";
        }
        assert(result.writes.size() == 128);
        assert(aw_first == expected_aw_first);
        assert(same == expected_same);
        assert(w_first == expected_w_first);
        assert(aw_first > 0 && same > 0 && w_first > 0);
        assert(result.diagnostics.final_write_outstanding == 0);
    }
}

} // namespace

int main() {
    test_aw_before_w_without_later_aw();
    test_multiple_w_bursts_before_aw();
    test_same_cycle_and_dependency_violation();
    test_multibeat_before_aw_and_pending_diagnostics();
    test_reset_and_orphans();
    test_fixed_seed_schedules();
    std::cout << "PASS: AXI transaction tracker unit tests\n";
    return 0;
}
