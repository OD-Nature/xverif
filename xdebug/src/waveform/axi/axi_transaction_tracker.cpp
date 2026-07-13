#include "axi_transaction_tracker.h"

#include <algorithm>
#include <cstdlib>

namespace xdebug_waveform {
namespace {

void inc_outstanding(int& total, std::map<std::string, int>& by_id,
                     const std::string& id) {
    ++total;
    ++by_id[id];
}

void dec_outstanding(int& total, std::map<std::string, int>& by_id,
                     const std::string& id) {
    if (total > 0) --total;
    auto it = by_id.find(id);
    if (it == by_id.end()) return;
    if (it->second > 0) --it->second;
    if (it->second == 0) by_id.erase(it);
}

bool txn_addr_less(const AxiTransaction& lhs, const AxiTransaction& rhs) {
    if (lhs.addr_time != rhs.addr_time) return lhs.addr_time < rhs.addr_time;
    return lhs.seq < rhs.seq;
}

} // namespace

size_t axi_expected_beats(const std::string& len) {
    if (len.empty()) return 1;
    char* end = nullptr;
    unsigned long long value = strtoull(len.c_str(), &end, 16);
    return end == len.c_str() ? 1 : static_cast<size_t>(value + 1);
}

std::string axi_write_phase_order(const AxiTransaction& txn) {
    if (!txn.is_write || txn.data.empty()) return "unknown";
    if (txn.first_data_time < txn.addr_time) return "w_before_aw";
    if (txn.first_data_time == txn.addr_time) return "same_cycle";
    return "aw_before_w";
}

void AxiTransactionTracker::clear_for_reset() {
    result_.diagnostics.reset_cleared_write_count += pending_writes_.size();
    for (const auto& item : pending_reads_)
        result_.diagnostics.reset_cleared_read_count += item.second.size();
    result_.diagnostics.reset_cleared_w_beat_count += w_beats_.size();
    pending_writes_.clear();
    pending_reads_.clear();
    w_beats_.clear();
    write_outstanding_ = 0;
    read_outstanding_ = 0;
    write_outstanding_by_id_.clear();
    read_outstanding_by_id_.clear();
}

void AxiTransactionTracker::drain_w_beats() {
    while (!w_beats_.empty()) {
        auto pending = std::find_if(pending_writes_.begin(), pending_writes_.end(),
            [](const AxiTransaction& txn) { return !txn.data_complete; });
        if (pending == pending_writes_.end()) return;
        WBeat beat = std::move(w_beats_.front());
        w_beats_.pop_front();
        if (pending->data.empty()) pending->first_data_time = beat.time;
        pending->data.push_back(std::move(beat.data));
        pending->wstrb.push_back(std::move(beat.strb));
        pending->last_data_time = beat.time;
        if (beat.last) {
            pending->data_complete = true;
            pending->phase_order = axi_write_phase_order(*pending);
            if (pending->data.size() != pending->expected_beat_count)
                ++result_.diagnostics.beat_count_mismatch_count;
        }
    }
}

void AxiTransactionTracker::complete_write(const AxiSample& sample) {
    auto pending = std::find_if(pending_writes_.begin(), pending_writes_.end(),
        [&](const AxiTransaction& txn) {
            return txn.data_complete && txn.id == sample.bid;
        });
    if (pending == pending_writes_.end()) {
        ++result_.diagnostics.orphan_b_count;
        return;
    }
    pending->resp_time = sample.time;
    pending->resp = sample.bresp;
    if (sample.time <= pending->addr_time || sample.time <= pending->last_data_time) {
        pending->response_dependency_violation = true;
        ++result_.diagnostics.response_dependency_violation_count;
    }
    dec_outstanding(write_outstanding_, write_outstanding_by_id_, pending->id);
    result_.writes.push_back(std::move(*pending));
    pending_writes_.erase(pending);
}

void AxiTransactionTracker::complete_read(const AxiSample& sample) {
    auto by_id = pending_reads_.find(sample.rid);
    if (by_id == pending_reads_.end() || by_id->second.empty()) {
        ++result_.diagnostics.orphan_r_beat_count;
        return;
    }
    AxiTransaction& pending = by_id->second.front();
    if (pending.data.empty()) pending.first_data_time = sample.time;
    pending.data.push_back(sample.rdata);
    pending.resp = sample.rresp;
    pending.last_data_time = sample.time;
    if (!sample.rlast) return;
    pending.data_complete = true;
    pending.resp_time = sample.time;
    if (pending.data.size() != pending.expected_beat_count)
        ++result_.diagnostics.beat_count_mismatch_count;
    dec_outstanding(read_outstanding_, read_outstanding_by_id_, pending.id);
    result_.reads.push_back(std::move(pending));
    by_id->second.pop_front();
    if (by_id->second.empty()) pending_reads_.erase(by_id);
}

void AxiTransactionTracker::snapshot(npiFsdbTime time) {
    AxiOutstandingSample sample;
    sample.time = time;
    sample.read = read_outstanding_;
    sample.write = write_outstanding_;
    sample.read_by_id = read_outstanding_by_id_;
    sample.write_by_id = write_outstanding_by_id_;
    result_.outstanding_samples.push_back(std::move(sample));
}

void AxiTransactionTracker::consume(const AxiSample& sample) {
    if (finished_) return;
    ++result_.diagnostics.sample_count;
    if (sample.reset_active) {
        clear_for_reset();
        return;
    }

    if (sample.aw_handshake) {
        ++result_.diagnostics.handshakes.aw;
        AxiTransaction txn;
        txn.seq = ++next_seq_;
        txn.is_write = true;
        txn.addr_time = sample.time;
        txn.addr = sample.awaddr;
        txn.id = sample.awid;
        txn.len = sample.awlen;
        txn.size = sample.awsize;
        txn.burst = sample.awburst;
        txn.expected_beat_count = axi_expected_beats(txn.len);
        inc_outstanding(write_outstanding_, write_outstanding_by_id_, txn.id);
        result_.diagnostics.max_total_write_outstanding =
            std::max(result_.diagnostics.max_total_write_outstanding, write_outstanding_);
        result_.diagnostics.max_write_outstanding_by_id[txn.id] = std::max(
            result_.diagnostics.max_write_outstanding_by_id[txn.id],
            write_outstanding_by_id_[txn.id]);
        pending_writes_.push_back(std::move(txn));
    }
    if (sample.ar_handshake) {
        ++result_.diagnostics.handshakes.ar;
        AxiTransaction txn;
        txn.seq = ++next_seq_;
        txn.is_write = false;
        txn.addr_time = sample.time;
        txn.addr = sample.araddr;
        txn.id = sample.arid;
        txn.len = sample.arlen;
        txn.size = sample.arsize;
        txn.burst = sample.arburst;
        txn.expected_beat_count = axi_expected_beats(txn.len);
        inc_outstanding(read_outstanding_, read_outstanding_by_id_, txn.id);
        result_.diagnostics.max_total_read_outstanding =
            std::max(result_.diagnostics.max_total_read_outstanding, read_outstanding_);
        result_.diagnostics.max_read_outstanding_by_id[txn.id] = std::max(
            result_.diagnostics.max_read_outstanding_by_id[txn.id],
            read_outstanding_by_id_[txn.id]);
        pending_reads_[txn.id].push_back(std::move(txn));
    }
    if (sample.w_handshake) {
        ++result_.diagnostics.handshakes.w;
        WBeat beat;
        beat.time = sample.time;
        beat.data = sample.wdata;
        beat.strb = sample.wstrb;
        beat.last = sample.wlast;
        w_beats_.push_back(std::move(beat));
    }
    drain_w_beats();

    if (sample.b_handshake) {
        ++result_.diagnostics.handshakes.b;
        complete_write(sample);
    }
    if (sample.r_handshake) {
        ++result_.diagnostics.handshakes.r;
        complete_read(sample);
    }
    snapshot(sample.time);
}

AxiResult AxiTransactionTracker::finish(npiFsdbTime scan_begin,
                                        npiFsdbTime scan_end,
                                        bool analysis_complete) {
    if (finished_) return AxiResult();
    finished_ = true;
    result_.diagnostics.scan_begin = scan_begin;
    result_.diagnostics.scan_end = scan_end;
    result_.diagnostics.analysis_complete = analysis_complete;
    result_.diagnostics.incomplete_write_count = pending_writes_.size();
    result_.diagnostics.buffered_w_beat_count = w_beats_.size();
    result_.diagnostics.orphan_w_beat_count = w_beats_.size();
    for (const auto& beat : w_beats_)
        if (beat.last) ++result_.diagnostics.buffered_w_burst_count;
    result_.diagnostics.final_write_outstanding = write_outstanding_;
    result_.diagnostics.final_read_outstanding = read_outstanding_;

    for (const auto& txn : pending_writes_) result_.pending_writes.push_back(txn);
    for (const auto& item : pending_reads_) {
        result_.diagnostics.incomplete_read_count += item.second.size();
        for (const auto& txn : item.second) result_.pending_reads.push_back(txn);
    }

    result_.all.reserve(result_.writes.size() + result_.reads.size());
    for (const auto& txn : result_.writes) result_.all.push_back(txn);
    for (const auto& txn : result_.reads) result_.all.push_back(txn);
    std::sort(result_.writes.begin(), result_.writes.end(), txn_addr_less);
    std::sort(result_.reads.begin(), result_.reads.end(), txn_addr_less);
    std::sort(result_.all.begin(), result_.all.end(), txn_addr_less);
    result_.all_by_resp_time.resize(result_.all.size());
    for (size_t i = 0; i < result_.all.size(); ++i) result_.all_by_resp_time[i] = i;
    std::sort(result_.all_by_resp_time.begin(), result_.all_by_resp_time.end(),
        [&](size_t lhs, size_t rhs) {
            return result_.all[lhs].resp_time < result_.all[rhs].resp_time;
        });
    return std::move(result_);
}

} // namespace xdebug_waveform
