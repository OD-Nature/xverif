#include "axi_analyzer.h"
#include "../common/clock_sampling.h"
#include "../server/fsdb_value_reader.h"
#include "../server/fsdb_scan_utils.h"
#include "npi_fsdb.h"
#include "npi_L1.h"
#include <cstdio>
#include <cstdlib>
#include <cstdint>
#include <algorithm>
#include <list>
#include <deque>
#include <map>
#include <limits>
#include <set>

namespace xdebug_waveform {

bool AxiAnalyzer::parse_hex_value(const std::string& hex_str, uint64_t& out) {
    if (hex_str.empty()) return false;
    const char* start = hex_str.c_str();
    char* end = nullptr;
    out = strtoull(start, &end, 16);
    return end != start;
}

bool AxiAnalyzer::id_matches(const std::string& txn_id, const char* id_str) {
    if (!id_str) return true;
    uint64_t txn_id_val = 0;
    if (!parse_hex_value(txn_id, txn_id_val)) return false;
    char* end = nullptr;
    uint64_t id_val = strtoull(id_str, &end, 0);
    if (end == id_str) return false;
    return txn_id_val == id_val;
}

const AxiResult* AxiAnalyzer::get_result(const std::string& name) const {
    auto it = results_.find(name);
    if (it != results_.end()) return &it->second;
    return nullptr;
}

AxiResult* AxiAnalyzer::get_result_mut(const std::string& name) {
    auto it = results_.find(name);
    if (it != results_.end()) return &it->second;
    return nullptr;
}

AxiCursor* AxiAnalyzer::get_cursor_mut(const std::string& name) {
    auto it = cursors_.find(name);
    if (it != cursors_.end()) return &it->second;
    return nullptr;
}

struct SigIdx {
    int reset = -1;
    int awaddr = -1, awid = -1, awlen = -1, awsize = -1, awburst = -1, awvalid = -1, awready = -1;
    int wdata = -1, wstrb = -1, wlast = -1, wvalid = -1, wready = -1;
    int bid = -1, bresp = -1, bvalid = -1, bready = -1;
    int araddr = -1, arid = -1, arlen = -1, arsize = -1, arburst = -1, arvalid = -1, arready = -1;
    int rid = -1, rdata = -1, rresp = -1, rlast = -1, rvalid = -1, rready = -1;
};

static void add_sig(const std::string& path, int& idx, std::vector<std::string>& signals) {
    if (!path.empty()) {
        idx = (int)signals.size();
        signals.push_back(path);
    } else {
        idx = -1;
    }
}

static bool is_active(const std::string& v) {
    return !v.empty() && v != "0" && v != "X" && v != "Z";
}

bool AxiAnalyzer::analyze(const std::string& name, npiFsdbFileHandle file, const AxiConfig& config) {
    if (get_result(name) != nullptr) {
        return true; // already cached
    }

    ClockSampleSpec clock_sample = config.clock_sample;
    std::string normalize_error;
    if (!normalize_clock_sample_spec(file, clock_sample, normalize_error)) return false;

    // Build signal vector and index map
    std::vector<std::string> signals;
    signals.reserve(30);
    SigIdx idx;
    add_sig(config.reset.signal, idx.reset, signals);
    add_sig(config.awaddr,  idx.awaddr,  signals);
    add_sig(config.awid,    idx.awid,    signals);
    add_sig(config.awlen,   idx.awlen,   signals);
    add_sig(config.awsize,  idx.awsize,  signals);
    add_sig(config.awburst, idx.awburst, signals);
    add_sig(config.awvalid, idx.awvalid, signals);
    add_sig(config.awready, idx.awready, signals);
    add_sig(config.wdata,   idx.wdata,   signals);
    add_sig(config.wstrb,   idx.wstrb,   signals);
    add_sig(config.wlast,   idx.wlast,   signals);
    add_sig(config.wvalid,  idx.wvalid,  signals);
    add_sig(config.wready,  idx.wready,  signals);
    add_sig(config.bid,     idx.bid,     signals);
    add_sig(config.bresp,   idx.bresp,   signals);
    add_sig(config.bvalid,  idx.bvalid,  signals);
    add_sig(config.bready,  idx.bready,  signals);
    add_sig(config.araddr,  idx.araddr,  signals);
    add_sig(config.arid,    idx.arid,    signals);
    add_sig(config.arlen,   idx.arlen,   signals);
    add_sig(config.arsize,  idx.arsize,  signals);
    add_sig(config.arburst, idx.arburst, signals);
    add_sig(config.arvalid, idx.arvalid, signals);
    add_sig(config.arready, idx.arready, signals);
    add_sig(config.rid,     idx.rid,     signals);
    add_sig(config.rdata,   idx.rdata,   signals);
    add_sig(config.rresp,   idx.rresp,   signals);
    add_sig(config.rlast,   idx.rlast,   signals);
    add_sig(config.rvalid,  idx.rvalid,  signals);
    add_sig(config.rready,  idx.rready,  signals);

    fsdbSigVec_t sig_handles;
    for (const auto& sig_name : signals) {
        npiFsdbSigHandle sig = npi_fsdb_sig_by_name(file, sig_name.c_str(), NULL);
        if (!sig) {
            return false;
        }
        sig_handles.push_back(sig);
    }
    std::vector<ClockSampleSignal> sample_signals;
    for (size_t i = 0; i < signals.size(); ++i) {
        sample_signals.push_back({signals[i], signals[i], sig_handles[i]});
    }

    AxiTransactionTracker tracker;

    auto process_edge = [&](npiFsdbTime t, const std::vector<std::string>& values) {
        if (values.size() != signals.size()) return;
        AxiSample sample;
        sample.time = t;
        if (idx.reset >= 0) {
            sample.reset_active = reset_is_active(config.reset, values[idx.reset]);
        }
        sample.aw_valid = idx.awvalid >= 0 && is_active(values[idx.awvalid]);
        sample.w_valid = idx.wvalid >= 0 && is_active(values[idx.wvalid]);
        sample.ar_valid = idx.arvalid >= 0 && is_active(values[idx.arvalid]);
        sample.r_valid = idx.rvalid >= 0 && is_active(values[idx.rvalid]);
        sample.aw_handshake = idx.awvalid >= 0 && idx.awready >= 0 &&
            is_active(values[idx.awvalid]) && is_active(values[idx.awready]);
        sample.w_handshake = idx.wvalid >= 0 && idx.wready >= 0 &&
            is_active(values[idx.wvalid]) && is_active(values[idx.wready]);
        sample.b_handshake = idx.bvalid >= 0 && idx.bready >= 0 &&
            is_active(values[idx.bvalid]) && is_active(values[idx.bready]);
        sample.ar_handshake = idx.arvalid >= 0 && idx.arready >= 0 &&
            is_active(values[idx.arvalid]) && is_active(values[idx.arready]);
        sample.r_handshake = idx.rvalid >= 0 && idx.rready >= 0 &&
            is_active(values[idx.rvalid]) && is_active(values[idx.rready]);
        sample.wlast = idx.wlast >= 0 ? is_active(values[idx.wlast]) : true;
        sample.rlast = idx.rlast >= 0 ? is_active(values[idx.rlast]) : true;
        sample.awaddr = idx.awaddr >= 0 ? values[idx.awaddr] : "";
        sample.awid = idx.awid >= 0 ? values[idx.awid] : "0";
        sample.awlen = idx.awlen >= 0 ? values[idx.awlen] : "0";
        sample.awsize = idx.awsize >= 0 ? values[idx.awsize] : "";
        sample.awburst = idx.awburst >= 0 ? values[idx.awburst] : "";
        sample.wdata = idx.wdata >= 0 ? values[idx.wdata] : "";
        sample.wstrb = idx.wstrb >= 0 ? values[idx.wstrb] : "";
        sample.bid = idx.bid >= 0 ? values[idx.bid] : "0";
        sample.bresp = idx.bresp >= 0 ? values[idx.bresp] : "";
        sample.araddr = idx.araddr >= 0 ? values[idx.araddr] : "";
        sample.arid = idx.arid >= 0 ? values[idx.arid] : "0";
        sample.arlen = idx.arlen >= 0 ? values[idx.arlen] : "0";
        sample.arsize = idx.arsize >= 0 ? values[idx.arsize] : "";
        sample.arburst = idx.arburst >= 0 ? values[idx.arburst] : "";
        sample.rid = idx.rid >= 0 ? values[idx.rid] : "0";
        sample.rdata = idx.rdata >= 0 ? values[idx.rdata] : "";
        sample.rresp = idx.rresp >= 0 ? values[idx.rresp] : "";
        tracker.consume(sample);
    };

    npiFsdbTime min_time = 0;
    npiFsdbTime max_time = 0;
    npi_fsdb_min_time(file, &min_time);
    npi_fsdb_max_time(file, &max_time);

    ClockSampleScanner scanner(file, clock_sample);
    std::string scan_error;
    int sample_count = 0;
    bool truncated = false;
    if (!scanner.scan(sample_signals, min_time, max_time, npiFsdbHexStrVal, '\0', -1,
        [&](const ClockSample& sample) -> bool {
            process_edge(sample.time, sample.values);
            return true;
        }, scan_error, sample_count, truncated)) {
        return false;
    }

    results_[name] = tracker.finish(min_time, max_time, !truncated);
    results_[name].diagnostics.full_scan_count = 1;
    cursors_[name] = AxiCursor();
    return true;
}

size_t AxiAnalyzer::get_write_count(const std::string& name) const {
    const AxiResult* r = get_result(name);
    return r ? r->writes.size() : 0;
}

size_t AxiAnalyzer::get_read_count(const std::string& name) const {
    const AxiResult* r = get_result(name);
    return r ? r->reads.size() : 0;
}

bool AxiAnalyzer::get_write_by_addr(const std::string& name, uint64_t addr, const AxiTransaction*& out) const {
    const AxiResult* r = get_result(name);
    if (!r) return false;
    for (const auto& txn : r->writes) {
        uint64_t txn_addr = 0;
        if (parse_hex_value(txn.addr, txn_addr) && txn_addr == addr) {
            out = &txn;
            return true;
        }
    }
    return false;
}

bool AxiAnalyzer::get_write_by_addr_num(const std::string& name, uint64_t addr, size_t num, const AxiTransaction*& out) const {
    const AxiResult* r = get_result(name);
    if (!r) return false;
    if (num == 0) return false;
    size_t count = 0;
    for (const auto& txn : r->writes) {
        uint64_t txn_addr = 0;
        if (parse_hex_value(txn.addr, txn_addr) && txn_addr == addr) {
            if (++count == num) {
                out = &txn;
                return true;
            }
        }
    }
    return false;
}

bool AxiAnalyzer::get_write_by_addr_last(const std::string& name, uint64_t addr, const AxiTransaction*& out) const {
    const AxiResult* r = get_result(name);
    if (!r) return false;
    const AxiTransaction* found = nullptr;
    for (const auto& txn : r->writes) {
        uint64_t txn_addr = 0;
        if (parse_hex_value(txn.addr, txn_addr) && txn_addr == addr) {
            found = &txn;
        }
    }
    if (found) {
        out = found;
        return true;
    }
    return false;
}

bool AxiAnalyzer::get_write_by_num(const std::string& name, size_t num, const AxiTransaction*& out) const {
    const AxiResult* r = get_result(name);
    if (!r || num == 0 || num > r->writes.size()) return false;
    out = &r->writes[num - 1];
    return true;
}

bool AxiAnalyzer::get_write_last(const std::string& name, const AxiTransaction*& out) const {
    const AxiResult* r = get_result(name);
    if (!r || r->writes.empty()) return false;
    out = &r->writes.back();
    return true;
}

bool AxiAnalyzer::get_write_by_addr(const std::string& name, uint64_t addr, const char* id_str, const AxiTransaction*& out) const {
    const AxiResult* r = get_result(name);
    if (!r) return false;
    for (const auto& txn : r->writes) {
        uint64_t txn_addr = 0;
        if (parse_hex_value(txn.addr, txn_addr) && txn_addr == addr && id_matches(txn.id, id_str)) {
            out = &txn;
            return true;
        }
    }
    return false;
}

bool AxiAnalyzer::get_write_by_addr_num(const std::string& name, uint64_t addr, const char* id_str, size_t num, const AxiTransaction*& out) const {
    const AxiResult* r = get_result(name);
    if (!r || num == 0) return false;
    size_t count = 0;
    for (const auto& txn : r->writes) {
        uint64_t txn_addr = 0;
        if (parse_hex_value(txn.addr, txn_addr) && txn_addr == addr && id_matches(txn.id, id_str)) {
            if (++count == num) {
                out = &txn;
                return true;
            }
        }
    }
    return false;
}

bool AxiAnalyzer::get_write_by_addr_last(const std::string& name, uint64_t addr, const char* id_str, const AxiTransaction*& out) const {
    const AxiResult* r = get_result(name);
    if (!r) return false;
    const AxiTransaction* found = nullptr;
    for (const auto& txn : r->writes) {
        uint64_t txn_addr = 0;
        if (parse_hex_value(txn.addr, txn_addr) && txn_addr == addr && id_matches(txn.id, id_str)) {
            found = &txn;
        }
    }
    if (!found) return false;
    out = found;
    return true;
}

bool AxiAnalyzer::get_write_by_num(const std::string& name, const char* id_str, size_t num, const AxiTransaction*& out) const {
    const AxiResult* r = get_result(name);
    if (!r || num == 0) return false;
    size_t count = 0;
    for (const auto& txn : r->writes) {
        if (id_matches(txn.id, id_str) && ++count == num) {
            out = &txn;
            return true;
        }
    }
    return false;
}

bool AxiAnalyzer::get_write_last(const std::string& name, const char* id_str, const AxiTransaction*& out) const {
    const AxiResult* r = get_result(name);
    if (!r) return false;
    const AxiTransaction* found = nullptr;
    for (const auto& txn : r->writes) {
        if (id_matches(txn.id, id_str)) found = &txn;
    }
    if (!found) return false;
    out = found;
    return true;
}

bool AxiAnalyzer::get_read_by_addr(const std::string& name, uint64_t addr, const AxiTransaction*& out) const {
    const AxiResult* r = get_result(name);
    if (!r) return false;
    for (const auto& txn : r->reads) {
        uint64_t txn_addr = 0;
        if (parse_hex_value(txn.addr, txn_addr) && txn_addr == addr) {
            out = &txn;
            return true;
        }
    }
    return false;
}

bool AxiAnalyzer::get_read_by_addr_num(const std::string& name, uint64_t addr, size_t num, const AxiTransaction*& out) const {
    const AxiResult* r = get_result(name);
    if (!r) return false;
    if (num == 0) return false;
    size_t count = 0;
    for (const auto& txn : r->reads) {
        uint64_t txn_addr = 0;
        if (parse_hex_value(txn.addr, txn_addr) && txn_addr == addr) {
            if (++count == num) {
                out = &txn;
                return true;
            }
        }
    }
    return false;
}

bool AxiAnalyzer::get_read_by_addr_last(const std::string& name, uint64_t addr, const AxiTransaction*& out) const {
    const AxiResult* r = get_result(name);
    if (!r) return false;
    const AxiTransaction* found = nullptr;
    for (const auto& txn : r->reads) {
        uint64_t txn_addr = 0;
        if (parse_hex_value(txn.addr, txn_addr) && txn_addr == addr) {
            found = &txn;
        }
    }
    if (found) {
        out = found;
        return true;
    }
    return false;
}

bool AxiAnalyzer::get_read_by_num(const std::string& name, size_t num, const AxiTransaction*& out) const {
    const AxiResult* r = get_result(name);
    if (!r || num == 0 || num > r->reads.size()) return false;
    out = &r->reads[num - 1];
    return true;
}

bool AxiAnalyzer::get_read_last(const std::string& name, const AxiTransaction*& out) const {
    const AxiResult* r = get_result(name);
    if (!r || r->reads.empty()) return false;
    out = &r->reads.back();
    return true;
}

bool AxiAnalyzer::get_read_by_addr(const std::string& name, uint64_t addr, const char* id_str, const AxiTransaction*& out) const {
    const AxiResult* r = get_result(name);
    if (!r) return false;
    for (const auto& txn : r->reads) {
        uint64_t txn_addr = 0;
        if (parse_hex_value(txn.addr, txn_addr) && txn_addr == addr && id_matches(txn.id, id_str)) {
            out = &txn;
            return true;
        }
    }
    return false;
}

bool AxiAnalyzer::get_read_by_addr_num(const std::string& name, uint64_t addr, const char* id_str, size_t num, const AxiTransaction*& out) const {
    const AxiResult* r = get_result(name);
    if (!r || num == 0) return false;
    size_t count = 0;
    for (const auto& txn : r->reads) {
        uint64_t txn_addr = 0;
        if (parse_hex_value(txn.addr, txn_addr) && txn_addr == addr && id_matches(txn.id, id_str)) {
            if (++count == num) {
                out = &txn;
                return true;
            }
        }
    }
    return false;
}

bool AxiAnalyzer::get_read_by_addr_last(const std::string& name, uint64_t addr, const char* id_str, const AxiTransaction*& out) const {
    const AxiResult* r = get_result(name);
    if (!r) return false;
    const AxiTransaction* found = nullptr;
    for (const auto& txn : r->reads) {
        uint64_t txn_addr = 0;
        if (parse_hex_value(txn.addr, txn_addr) && txn_addr == addr && id_matches(txn.id, id_str)) {
            found = &txn;
        }
    }
    if (!found) return false;
    out = found;
    return true;
}

bool AxiAnalyzer::get_read_by_num(const std::string& name, const char* id_str, size_t num, const AxiTransaction*& out) const {
    const AxiResult* r = get_result(name);
    if (!r || num == 0) return false;
    size_t count = 0;
    for (const auto& txn : r->reads) {
        if (id_matches(txn.id, id_str) && ++count == num) {
            out = &txn;
            return true;
        }
    }
    return false;
}

bool AxiAnalyzer::get_read_last(const std::string& name, const char* id_str, const AxiTransaction*& out) const {
    const AxiResult* r = get_result(name);
    if (!r) return false;
    const AxiTransaction* found = nullptr;
    for (const auto& txn : r->reads) {
        if (id_matches(txn.id, id_str)) found = &txn;
    }
    if (!found) return false;
    out = found;
    return true;
}

bool AxiAnalyzer::cursor_begin(const std::string& name, int filter, const AxiTransaction*& out) {
    AxiResult* r = get_result_mut(name);
    AxiCursor* c = get_cursor_mut(name);
    if (!r || !c) return false;

    if (filter == 1) {
        c->wr_idx = 0;
        if (c->wr_idx < r->writes.size()) {
            out = &r->writes[c->wr_idx];
            return true;
        }
    } else if (filter == 2) {
        c->rd_idx = 0;
        if (c->rd_idx < r->reads.size()) {
            out = &r->reads[c->rd_idx];
            return true;
        }
    } else {
        c->all_idx = 0;
        if (c->all_idx < r->all.size()) {
            out = &r->all[c->all_idx];
            return true;
        }
    }
    return false;
}

bool AxiAnalyzer::cursor_next(const std::string& name, int filter, const AxiTransaction*& out) {
    AxiResult* r = get_result_mut(name);
    AxiCursor* c = get_cursor_mut(name);
    if (!r || !c) return false;

    if (filter == 1) {
        if (c->wr_idx + 1 < r->writes.size()) {
            out = &r->writes[++c->wr_idx];
            return true;
        }
    } else if (filter == 2) {
        if (c->rd_idx + 1 < r->reads.size()) {
            out = &r->reads[++c->rd_idx];
            return true;
        }
    } else {
        if (c->all_idx + 1 < r->all.size()) {
            out = &r->all[++c->all_idx];
            return true;
        }
    }
    return false;
}

bool AxiAnalyzer::cursor_prev(const std::string& name, int filter, const AxiTransaction*& out) {
    AxiResult* r = get_result_mut(name);
    AxiCursor* c = get_cursor_mut(name);
    if (!r || !c) return false;

    if (filter == 1) {
        if (c->wr_idx > 0) {
            out = &r->writes[--c->wr_idx];
            return true;
        }
    } else if (filter == 2) {
        if (c->rd_idx > 0) {
            out = &r->reads[--c->rd_idx];
            return true;
        }
    } else {
        if (c->all_idx > 0) {
            out = &r->all[--c->all_idx];
            return true;
        }
    }
    return false;
}

bool AxiAnalyzer::cursor_last(const std::string& name, int filter, const AxiTransaction*& out) {
    AxiResult* r = get_result_mut(name);
    AxiCursor* c = get_cursor_mut(name);
    if (!r || !c) return false;

    if (filter == 1) {
        if (!r->writes.empty()) {
            c->wr_idx = r->writes.size() - 1;
            out = &r->writes[c->wr_idx];
            return true;
        }
    } else if (filter == 2) {
        if (!r->reads.empty()) {
            c->rd_idx = r->reads.size() - 1;
            out = &r->reads[c->rd_idx];
            return true;
        }
    } else {
        if (!r->all.empty()) {
            c->all_idx = r->all.size() - 1;
            out = &r->all[c->all_idx];
            return true;
        }
    }
    return false;
}

bool AxiAnalyzer::cursor_state(const std::string& name, int filter,
                               size_t& one_based_index, size_t& total_count) const {
    const AxiResult* result = get_result(name);
    auto cursor_it = cursors_.find(name);
    if (!result || cursor_it == cursors_.end()) return false;
    const AxiCursor& cursor = cursor_it->second;
    if (filter == 1) {
        total_count = result->writes.size();
        one_based_index = total_count == 0 ? 0 : cursor.wr_idx + 1;
    } else if (filter == 2) {
        total_count = result->reads.size();
        one_based_index = total_count == 0 ? 0 : cursor.rd_idx + 1;
    } else {
        total_count = result->all.size();
        one_based_index = total_count == 0 ? 0 : cursor.all_idx + 1;
    }
    return true;
}

bool AxiAnalyzer::get_latency_stats(const std::string& name, bool is_write,
                                    const AxiTransaction*& max_txn,
                                    const AxiTransaction*& min_txn,
                                    double& avg_latency) const {
    const AxiResult* r = get_result(name);
    if (!r) return false;
    const auto& vec = is_write ? r->writes : r->reads;
    if (vec.empty()) return false;

    const AxiTransaction* max_t = &vec[0];
    const AxiTransaction* min_t = &vec[0];
    double total = 0.0;

    for (const auto& txn : vec) {
        double lat = static_cast<double>(txn.resp_time) - static_cast<double>(txn.addr_time);
        total += lat;
        double max_lat = static_cast<double>(max_t->resp_time) - static_cast<double>(max_t->addr_time);
        double min_lat = static_cast<double>(min_t->resp_time) - static_cast<double>(min_t->addr_time);
        if (lat > max_lat) max_t = &txn;
        if (lat < min_lat) min_t = &txn;
    }

    max_txn = max_t;
    min_txn = min_t;
    avg_latency = total / vec.size();
    return true;
}

bool AxiAnalyzer::get_latency_stats(const std::string& name, int filter, const char* id_str,
                                    AxiStatResult& out) const {
    const AxiResult* r = get_result(name);
    if (!r) return false;

    bool include_wr = (filter == 0 || filter == 1);
    bool include_rd = (filter == 0 || filter == 2);
    double total = 0.0;
    std::vector<double> latencies;
    bool seen = false;

    auto visit = [&](const AxiTransaction& txn) {
        if (!id_matches(txn.id, id_str)) return;
        double lat = static_cast<double>(txn.resp_time) - static_cast<double>(txn.addr_time);
        if (!seen) {
            out.max = lat;
            out.min = lat;
            out.max_txn = &txn;
            out.min_txn = &txn;
            seen = true;
        } else {
            if (lat > out.max) {
                out.max = lat;
                out.max_txn = &txn;
            }
            if (lat < out.min) {
                out.min = lat;
                out.min_txn = &txn;
            }
        }
        total += lat;
        latencies.push_back(lat);
        ++out.samples;
    };

    if (include_wr) {
        for (const auto& txn : r->writes) visit(txn);
    }
    if (include_rd) {
        for (const auto& txn : r->reads) visit(txn);
    }

    if (!seen || out.samples == 0) return false;
    out.avg = total / static_cast<double>(out.samples);
    std::sort(latencies.begin(), latencies.end());
    auto percentile = [&](size_t percent) {
        size_t rank = (percent * latencies.size() + 99) / 100;
        if (rank == 0) rank = 1;
        return latencies[rank - 1];
    };
    out.p50 = percentile(50);
    out.p95 = percentile(95);
    out.p99 = percentile(99);
    return true;
}

bool AxiAnalyzer::get_outstanding_stats(const std::string& name, int filter, const char* id_str,
                                        AxiStatResult& out) const {
    const AxiResult* r = get_result(name);
    if (!r || r->outstanding_samples.empty()) return false;

    bool seen = false;
    double total = 0.0;

    for (const auto& sample : r->outstanding_samples) {
        int value = 0;
        if (id_str) {
            uint64_t want = 0;
            char* end = nullptr;
            want = strtoull(id_str, &end, 0);
            if (end == id_str) return false;

            auto add_matching = [&](const std::map<std::string, int>& m) {
                for (const auto& kv : m) {
                    uint64_t id_val = 0;
                    if (parse_hex_value(kv.first, id_val) && id_val == want) {
                        value += kv.second;
                    }
                }
            };
            if (filter == 0 || filter == 1) add_matching(sample.write_by_id);
            if (filter == 0 || filter == 2) add_matching(sample.read_by_id);
        } else {
            if (filter == 0 || filter == 1) value += sample.write;
            if (filter == 0 || filter == 2) value += sample.read;
        }

        if (!seen) {
            out.max = value;
            out.min = value;
            seen = true;
        } else {
            if (value > out.max) out.max = value;
            if (value < out.min) out.min = value;
        }
        total += value;
        ++out.samples;
    }

    if (!seen || out.samples == 0) return false;
    out.avg = total / static_cast<double>(out.samples);
    return true;
}

bool AxiAnalyzer::get_transactions_in_range(const std::string& name,
                                            npiFsdbTime begin,
                                            npiFsdbTime end,
                                            std::vector<AxiContextTransaction>& out,
                                            int max_results) const {
    out.clear();
    const AxiResult* r = get_result(name);
    if (!r) return false;

    std::set<const AxiTransaction*> emitted;
    auto emit = [&](const AxiTransaction& txn, npiFsdbTime match_time) {
        if (max_results >= 0 && static_cast<int>(out.size()) >= max_results) return;
        if (!emitted.insert(&txn).second) return;
        AxiContextTransaction item;
        item.txn = &txn;
        item.match_time = match_time;
        out.push_back(item);
    };

    auto addr_it = std::lower_bound(r->all.begin(), r->all.end(), begin,
        [](const AxiTransaction& txn, npiFsdbTime t) {
            return txn.addr_time < t;
        });
    for (; addr_it != r->all.end() && addr_it->addr_time <= end; ++addr_it) {
        if (max_results >= 0 && static_cast<int>(out.size()) >= max_results) break;
        emit(*addr_it, addr_it->addr_time);
    }

    auto resp_it = std::lower_bound(r->all_by_resp_time.begin(), r->all_by_resp_time.end(), begin,
        [&](size_t idx, npiFsdbTime t) {
            return r->all[idx].resp_time < t;
        });
    for (; resp_it != r->all_by_resp_time.end(); ++resp_it) {
        if (max_results >= 0 && static_cast<int>(out.size()) >= max_results) break;
        const AxiTransaction& txn = r->all[*resp_it];
        if (txn.resp_time > end) break;
        emit(txn, txn.resp_time);
    }

    std::sort(out.begin(), out.end(), [](const AxiContextTransaction& lhs, const AxiContextTransaction& rhs) {
        return lhs.match_time < rhs.match_time;
    });
    return true;
}

const std::vector<AxiAnalyzer::HandshakeIndexEntry>* AxiAnalyzer::handshake_index(
        const std::string& name, const std::string& channel) const {
    const AxiResult* result = get_result(name);
    if (!result) return nullptr;
    auto& by_channel = handshake_indexes_[name];
    auto found = by_channel.find(channel);
    if (found != by_channel.end()) return &found->second;

    std::vector<HandshakeIndexEntry> index;
    const bool write_channel = channel == "aw" || channel == "w" || channel == "b";
    const std::vector<AxiTransaction>& txns = write_channel ? result->writes : result->reads;
    for (const auto& txn : txns) {
        if (channel == "aw" || channel == "ar") {
            index.push_back({txn.addr_time, &txn, 0});
        } else if (channel == "b") {
            index.push_back({txn.resp_time, &txn, 0});
        } else if (channel == "w" || channel == "r") {
            for (size_t i = 0; i < txn.data_handshake_times.size(); ++i)
                index.push_back({txn.data_handshake_times[i], &txn, i + 1});
        }
    }
    std::sort(index.begin(), index.end(), [](const HandshakeIndexEntry& lhs,
                                             const HandshakeIndexEntry& rhs) {
        if (lhs.time != rhs.time) return lhs.time < rhs.time;
        if (lhs.txn && rhs.txn && lhs.txn->seq != rhs.txn->seq)
            return lhs.txn->seq < rhs.txn->seq;
        return lhs.beat_index < rhs.beat_index;
    });
    auto inserted = by_channel.emplace(channel, std::move(index));
    return &inserted.first->second;
}

bool AxiAnalyzer::get_by_handshake(const std::string& name,
                                   const std::string& channel,
                                   npiFsdbTime handshake_time,
                                   AxiHandshakeMatch& out) const {
    out = AxiHandshakeMatch();
    if (channel != "aw" && channel != "w" && channel != "b" &&
        channel != "ar" && channel != "r") return false;
    const std::vector<HandshakeIndexEntry>* index = handshake_index(name, channel);
    if (!index) return false;
    auto it = std::lower_bound(index->begin(), index->end(), handshake_time,
        [](const HandshakeIndexEntry& item, npiFsdbTime time) {
            return item.time < time;
        });
    if (it == index->end() || it->time != handshake_time) return false;
    out.txn = it->txn;
    out.channel = channel;
    out.handshake_time = it->time;
    out.beat_index = it->beat_index;
    return out.txn != nullptr;
}

bool AxiAnalyzer::get_outstanding_samples_in_range(const std::string& name,
                                                   npiFsdbTime begin,
                                                   npiFsdbTime end,
                                                   std::vector<AxiOutstandingSample>& out,
                                                   int max_results) const {
    out.clear();
    const AxiResult* r = get_result(name);
    if (!r) return false;
    auto it = std::lower_bound(r->outstanding_samples.begin(), r->outstanding_samples.end(), begin,
        [](const AxiOutstandingSample& sample, npiFsdbTime t) {
            return sample.time < t;
        });
    for (; it != r->outstanding_samples.end() && it->time <= end; ++it) {
        if (max_results >= 0 && static_cast<int>(out.size()) >= max_results) break;
        out.push_back(*it);
    }
    return true;
}

bool AxiAnalyzer::summarize_outstanding_in_range(const std::string& name,
                                                  npiFsdbTime begin,
                                                  npiFsdbTime end,
                                                  int filter,
                                                  int max_change_points,
                                                  AxiOutstandingSummary& out) const {
    out = AxiOutstandingSummary();
    const AxiResult* result = get_result(name);
    if (!result) return false;
    auto it = std::lower_bound(result->outstanding_samples.begin(),
                               result->outstanding_samples.end(), begin,
        [](const AxiOutstandingSample& sample, npiFsdbTime time) {
            return sample.time < time;
        });
    int previous_read = -1;
    int previous_write = -1;
    for (; it != result->outstanding_samples.end() && it->time <= end; ++it) {
        ++out.sample_count;
        out.has_samples = true;
        out.final_read = it->read;
        out.final_write = it->write;
        if (it->read > out.peak_read) {
            out.peak_read = it->read;
            out.peak_read_time = it->time;
        }
        if (it->write > out.peak_write) {
            out.peak_write = it->write;
            out.peak_write_time = it->time;
        }
        if (!out.has_first_nonzero && (it->read > 0 || it->write > 0)) {
            out.has_first_nonzero = true;
            out.first_nonzero_time = it->time;
        }
        const int visible_read = filter == 1 ? 0 : it->read;
        const int visible_write = filter == 2 ? 0 : it->write;
        if (visible_read == previous_read && visible_write == previous_write) continue;
        ++out.change_point_count;
        if (max_change_points < 0 ||
            static_cast<int>(out.change_points.size()) < max_change_points) {
            out.change_points.push_back(*it);
        }
        previous_read = visible_read;
        previous_write = visible_write;
    }
    return true;
}

} // namespace xdebug_waveform
