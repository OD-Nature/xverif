#include "axi_exporter.h"
#include "../server/fsdb_scan_utils.h"
#include "npi_L1.h"

#include <algorithm>
#include <cstdlib>
#include <deque>
#include <fstream>
#include <list>
#include <set>
#include <sstream>
#include <sys/stat.h>

namespace xdebug_waveform {

std::string format_time(npiFsdbTime t);
std::string format_duration(npiFsdbTime t);

namespace {

struct SigIdx {
    int rst_n = -1;
    int awaddr = -1, awid = -1, awlen = -1, awsize = -1, awburst = -1, awvalid = -1, awready = -1;
    int wlast = -1, wvalid = -1, wready = -1;
    int bid = -1, bresp = -1, bvalid = -1, bready = -1;
    int araddr = -1, arid = -1, arlen = -1, arsize = -1, arburst = -1, arvalid = -1, arready = -1;
    int rid = -1, rresp = -1, rlast = -1, rvalid = -1, rready = -1;
};

struct WBeatSummary {
    npiFsdbTime time = 0;
    bool last = false;
};

struct PendingWriteSummary {
    AxiExportTransaction txn;
    bool data_complete = false;
};

static void add_sig(const std::string& path, int& idx, std::vector<std::string>& signals) {
    if (!path.empty()) {
        idx = static_cast<int>(signals.size());
        signals.push_back(path);
    } else {
        idx = -1;
    }
}

static bool is_active(const std::string& v) {
    return !v.empty() && v != "0" && v != "X" && v != "Z";
}

static bool parse_hex_value(const std::string& text, uint64_t& out) {
    if (text.empty()) return false;
    char* end = nullptr;
    out = strtoull(text.c_str(), &end, 16);
    return end != text.c_str();
}

static size_t expected_beats(const std::string& len) {
    uint64_t value = 0;
    if (!parse_hex_value(len.empty() ? "0" : len, value)) return 1;
    return static_cast<size_t>(value + 1);
}

static void inc_osd(int& total,
                    std::map<std::string, int>& by_id,
                    std::map<std::string, int>& max_by_id,
                    int& max_total,
                    const std::string& id) {
    ++total;
    int count = ++by_id[id];
    if (count > max_by_id[id]) max_by_id[id] = count;
    if (total > max_total) max_total = total;
}

static void dec_osd(int& total, std::map<std::string, int>& by_id, const std::string& id) {
    if (total > 0) --total;
    auto it = by_id.find(id);
    if (it != by_id.end()) {
        if (it->second > 0) --it->second;
        if (it->second == 0) by_id.erase(it);
    }
}

static bool in_window(npiFsdbTime t, npiFsdbTime begin, npiFsdbTime end) {
    return t >= begin && t <= end;
}

static bool txn_less(const AxiExportTransaction& lhs, const AxiExportTransaction& rhs) {
    if (lhs.completion_time != rhs.completion_time) return lhs.completion_time < rhs.completion_time;
    if (lhs.addr_time != rhs.addr_time) return lhs.addr_time < rhs.addr_time;
    return lhs.seq < rhs.seq;
}

static bool ensure_parent_dir(const std::string& path) {
    size_t slash = path.find_last_of('/');
    if (slash == std::string::npos) return true;
    std::string dir = path.substr(0, slash);
    if (dir.empty()) return true;
    std::string cur;
    if (dir[0] == '/') cur = "/";
    size_t pos = dir[0] == '/' ? 1 : 0;
    while (pos <= dir.size()) {
        size_t next = dir.find('/', pos);
        std::string part = dir.substr(pos, next == std::string::npos ? std::string::npos : next - pos);
        if (!part.empty()) {
            if (!cur.empty() && cur[cur.size() - 1] != '/') cur += "/";
            cur += part;
            mkdir(cur.c_str(), 0700);
        }
        if (next == std::string::npos) break;
        pos = next + 1;
    }
    return true;
}

static char sep_for(const std::string& format) {
    return format == "csv" ? ',' : '\t';
}

static std::string sv_hex(const std::string& value) {
    return "'h" + value;
}

static void write_header(std::ofstream& out, char sep) {
    out << "seq" << sep
        << "completion_time" << sep
        << "addr_time" << sep
        << "first_data_time" << sep
        << "last_data_time" << sep
        << "latency" << sep
        << "id" << sep << "addr" << sep << "len" << sep << "size" << sep
        << "burst" << sep << "resp" << sep
        << "beat_count" << sep << "expected_beat_count" << "\n";
}

static void write_txn(std::ofstream& out, char sep, const AxiExportTransaction& txn) {
    npiFsdbTime latency = txn.completion_time >= txn.addr_time ? txn.completion_time - txn.addr_time : 0;
    out << txn.seq << sep
        << format_time(txn.completion_time) << sep
        << format_time(txn.addr_time) << sep
        << format_time(txn.first_data_time) << sep
        << format_time(txn.last_data_time) << sep
        << format_duration(latency) << sep
        << sv_hex(txn.id) << sep << sv_hex(txn.addr) << sep << sv_hex(txn.len) << sep
        << sv_hex(txn.size) << sep << sv_hex(txn.burst) << sep << sv_hex(txn.resp) << sep
        << txn.beat_count << sep << txn.expected_beat_count << "\n";
}

static Json map_to_json(const std::map<std::string, int>& values) {
    Json out = Json::object();
    for (const auto& kv : values) out[sv_hex(kv.first)] = kv.second;
    return out;
}

static Json ids_json(const std::map<std::string, int>& counts) {
    Json out = Json::array();
    for (const auto& kv : counts) out.push_back(sv_hex(kv.first));
    return out;
}

} // namespace

bool AxiExporter::scan(npiFsdbFileHandle file,
                       const AxiConfig& config,
                       npiFsdbTime begin,
                       npiFsdbTime end,
                       AxiExportResult& result,
                       std::string& error) const {
    result = AxiExportResult();
    result.name = config.name;
    result.begin = begin;
    result.end = end;

    ClockSampleSpec clock_sample = config.clock_sample;
    if (!normalize_clock_sample_spec(file, clock_sample, error)) return false;

    npiFsdbSigHandle clk_sig = npi_fsdb_sig_by_name(file, clock_sample.clock.c_str(), NULL);
    if (!clk_sig) {
        error = "Clock signal not found: " + clock_sample.clock;
        return false;
    }
    npiFsdbVctHandle vct = npi_fsdb_create_vct(clk_sig);
    if (!vct) {
        error = "Failed to create AXI clock VCT";
        return false;
    }

    std::vector<std::string> signals;
    signals.reserve(27);
    SigIdx idx;
    add_sig(config.rst_n, idx.rst_n, signals);
    add_sig(config.awaddr, idx.awaddr, signals);
    add_sig(config.awid, idx.awid, signals);
    add_sig(config.awlen, idx.awlen, signals);
    add_sig(config.awsize, idx.awsize, signals);
    add_sig(config.awburst, idx.awburst, signals);
    add_sig(config.awvalid, idx.awvalid, signals);
    add_sig(config.awready, idx.awready, signals);
    add_sig(config.wlast, idx.wlast, signals);
    add_sig(config.wvalid, idx.wvalid, signals);
    add_sig(config.wready, idx.wready, signals);
    add_sig(config.bid, idx.bid, signals);
    add_sig(config.bresp, idx.bresp, signals);
    add_sig(config.bvalid, idx.bvalid, signals);
    add_sig(config.bready, idx.bready, signals);
    add_sig(config.araddr, idx.araddr, signals);
    add_sig(config.arid, idx.arid, signals);
    add_sig(config.arlen, idx.arlen, signals);
    add_sig(config.arsize, idx.arsize, signals);
    add_sig(config.arburst, idx.arburst, signals);
    add_sig(config.arvalid, idx.arvalid, signals);
    add_sig(config.arready, idx.arready, signals);
    add_sig(config.rid, idx.rid, signals);
    add_sig(config.rresp, idx.rresp, signals);
    add_sig(config.rlast, idx.rlast, signals);
    add_sig(config.rvalid, idx.rvalid, signals);
    add_sig(config.rready, idx.rready, signals);

    fsdbSigVec_t sig_handles;
    for (const auto& sig_name : signals) {
        npiFsdbSigHandle sig = npi_fsdb_sig_by_name(file, sig_name.c_str(), NULL);
        if (!sig) {
            npi_fsdb_release_vct(vct);
            error = "AXI signal not found: " + sig_name;
            return false;
        }
        sig_handles.push_back(sig);
    }

    npiFsdbTime min_time = 0;
    npiFsdbTime max_time = 0;
    npi_fsdb_min_time(file, &min_time);
    npi_fsdb_max_time(file, &max_time);
    result.scan_begin = min_time;
    result.scan_end = max_time;

    fsdbSigVec_t all_handles;
    all_handles.push_back(clk_sig);
    for (auto sig : sig_handles) all_handles.push_back(sig);

    fsdbValVec_t init_values;
    std::vector<std::string> values(signals.size());
    std::string prev_clk_val;
    if (npi_fsdb_sig_hdl_vec_value_at(all_handles, min_time, init_values, npiFsdbHexStrVal) &&
        init_values.size() == all_handles.size()) {
        prev_clk_val = init_values[0];
        for (size_t i = 0; i < signals.size(); ++i) values[i] = init_values[i + 1];
    }

    std::deque<WBeatSummary> w_beat_buffer;
    std::list<PendingWriteSummary> pending_writes;
    std::map<std::string, std::deque<AxiExportTransaction>> pending_reads;
    int read_outstanding = 0;
    int write_outstanding = 0;
    std::map<std::string, int> read_outstanding_by_id;
    std::map<std::string, int> write_outstanding_by_id;
    uint64_t seq = 0;

    auto clear_pending_for_reset = [&]() {
        result.reset_cleared_write_count += static_cast<int>(pending_writes.size());
        for (const auto& kv : pending_reads) result.reset_cleared_read_count += static_cast<int>(kv.second.size());
        w_beat_buffer.clear();
        pending_writes.clear();
        pending_reads.clear();
        read_outstanding = 0;
        write_outstanding = 0;
        read_outstanding_by_id.clear();
        write_outstanding_by_id.clear();
    };

    auto accept_txn = [&](AxiExportTransaction txn) {
        txn.expected_beat_count = expected_beats(txn.len);
        if (txn.beat_count != txn.expected_beat_count) ++result.beat_count_mismatch_count;
        result.burst_histogram[txn.burst]++;
        if (in_window(txn.completion_time, begin, end)) {
            if (txn.is_write) {
                result.write_count_by_id[txn.id]++;
                result.writes.push_back(txn);
            } else {
                result.read_count_by_id[txn.id]++;
                result.reads.push_back(txn);
            }
        }
    };

    auto process_edge = [&](npiFsdbTime t, const std::vector<std::string>& vals) {
        if (vals.size() != signals.size()) return;
        bool reset_active = false;
        if (idx.rst_n >= 0) {
            const std::string& rst = vals[idx.rst_n];
            if (rst.empty() || rst == "0" || rst == "X" || rst == "Z") reset_active = true;
        }
        if (reset_active) {
            clear_pending_for_reset();
            return;
        }

        bool aw_handshake = idx.awvalid >= 0 && idx.awready >= 0 && is_active(vals[idx.awvalid]) && is_active(vals[idx.awready]);
        bool w_handshake = idx.wvalid >= 0 && idx.wready >= 0 && is_active(vals[idx.wvalid]) && is_active(vals[idx.wready]);
        bool b_handshake = idx.bvalid >= 0 && idx.bready >= 0 && is_active(vals[idx.bvalid]) && is_active(vals[idx.bready]);
        bool ar_handshake = idx.arvalid >= 0 && idx.arready >= 0 && is_active(vals[idx.arvalid]) && is_active(vals[idx.arready]);
        bool r_handshake = idx.rvalid >= 0 && idx.rready >= 0 && is_active(vals[idx.rvalid]) && is_active(vals[idx.rready]);

        auto drain_w_beats = [&]() {
            while (!w_beat_buffer.empty()) {
                PendingWriteSummary* target = nullptr;
                for (auto& pending : pending_writes) {
                    if (!pending.data_complete) {
                        target = &pending;
                        break;
                    }
                }
                if (!target) break;
                WBeatSummary beat = w_beat_buffer.front();
                w_beat_buffer.pop_front();
                if (target->txn.beat_count == 0) target->txn.first_data_time = beat.time;
                ++target->txn.beat_count;
                target->txn.last_data_time = beat.time;
                if (beat.last) target->data_complete = true;
            }
        };

        if (w_handshake) {
            WBeatSummary beat;
            beat.time = t;
            beat.last = idx.wlast >= 0 ? is_active(vals[idx.wlast]) : true;
            w_beat_buffer.push_back(beat);
            drain_w_beats();
        }

        if (aw_handshake) {
            PendingWriteSummary pw;
            pw.txn.seq = ++seq;
            pw.txn.addr_time = t;
            pw.txn.addr = idx.awaddr >= 0 ? vals[idx.awaddr] : "";
            pw.txn.id = idx.awid >= 0 ? vals[idx.awid] : "0";
            pw.txn.len = idx.awlen >= 0 ? vals[idx.awlen] : "0";
            pw.txn.size = idx.awsize >= 0 ? vals[idx.awsize] : "";
            pw.txn.burst = idx.awburst >= 0 ? vals[idx.awburst] : "";
            pw.txn.is_write = true;
            inc_osd(write_outstanding, write_outstanding_by_id,
                    result.max_write_outstanding_by_id, result.max_total_write_outstanding,
                    pw.txn.id);
            pending_writes.push_back(pw);
            drain_w_beats();
        }

        if (b_handshake) {
            std::string b_id_val = idx.bid >= 0 ? vals[idx.bid] : "0";
            for (auto it = pending_writes.begin(); it != pending_writes.end(); ++it) {
                if (!it->data_complete) continue;
                if (idx.bid >= 0 && it->txn.id != b_id_val) continue;
                it->txn.completion_time = t;
                it->txn.resp = idx.bresp >= 0 ? vals[idx.bresp] : "";
                dec_osd(write_outstanding, write_outstanding_by_id, it->txn.id);
                accept_txn(it->txn);
                pending_writes.erase(it);
                break;
            }
        }

        if (ar_handshake) {
            AxiExportTransaction txn;
            txn.seq = ++seq;
            txn.addr_time = t;
            txn.addr = idx.araddr >= 0 ? vals[idx.araddr] : "";
            txn.id = idx.arid >= 0 ? vals[idx.arid] : "0";
            txn.len = idx.arlen >= 0 ? vals[idx.arlen] : "0";
            txn.size = idx.arsize >= 0 ? vals[idx.arsize] : "";
            txn.burst = idx.arburst >= 0 ? vals[idx.arburst] : "";
            txn.is_write = false;
            inc_osd(read_outstanding, read_outstanding_by_id,
                    result.max_read_outstanding_by_id, result.max_total_read_outstanding,
                    txn.id);
            pending_reads[txn.id].push_back(txn);
        }

        if (r_handshake) {
            std::string r_id_val = idx.rid >= 0 ? vals[idx.rid] : "0";
            auto it_fifo = pending_reads.find(r_id_val);
            if (it_fifo != pending_reads.end() && !it_fifo->second.empty()) {
                AxiExportTransaction& txn = it_fifo->second.front();
                if (txn.beat_count == 0) txn.first_data_time = t;
                ++txn.beat_count;
                txn.resp = idx.rresp >= 0 ? vals[idx.rresp] : "";
                txn.last_data_time = t;
                bool last = idx.rlast >= 0 ? is_active(vals[idx.rlast]) : true;
                if (last) {
                    txn.completion_time = t;
                    dec_osd(read_outstanding, read_outstanding_by_id, txn.id);
                    accept_txn(txn);
                    it_fifo->second.pop_front();
                    if (it_fifo->second.empty()) pending_reads.erase(it_fifo);
                }
            }
        }
    };

    TimeBasedVcIterGuard guard;
    npiFsdbTimeBasedVcIter& iter = guard.iter();
    iter.add(clk_sig);
    for (auto sig : sig_handles) iter.add(sig);
    guard.start(min_time, max_time);

    bool have_group = false;
    bool clk_changed = false;
    std::string old_clk_val;
    std::string new_clk_val;
    npiFsdbTime group_time = 0;
    std::vector<std::string> group_start_values = values;
    npiFsdbTime curr_time = 0;
    npiFsdbSigHandle changed_sig = nullptr;
    bool sample_before_edge =
        clock_sample.edge != ClockEdgeKind::Negedge &&
        clock_sample.sample_point == ClockSamplePointKind::Before;

    auto finish_group = [&]() {
        if (!have_group || !clk_changed) return;
        bool is_target_edge = false;
        is_target_edge = clock_edge_transition_matches(clock_sample.edge,
                                                       old_clk_val == "1",
                                                       new_clk_val == "1");
        if (is_target_edge) process_edge(group_time, sample_before_edge ? group_start_values : values);
    };

    while (iter.iter_next(curr_time, changed_sig) > 0) {
        if (!have_group) {
            have_group = true;
            group_time = curr_time;
            group_start_values = values;
        } else if (curr_time != group_time) {
            finish_group();
            group_time = curr_time;
            clk_changed = false;
            group_start_values = values;
        }

        npiFsdbValue val;
        val.format = npiFsdbHexStrVal;
        std::string val_str;
        if (iter.get_value(val) && val.value.str) val_str = val.value.str;

        if (changed_sig == clk_sig) {
            old_clk_val = prev_clk_val;
            new_clk_val = val_str;
            prev_clk_val = val_str;
            clk_changed = true;
        } else {
            for (size_t i = 0; i < sig_handles.size(); ++i) {
                if (sig_handles[i] == changed_sig) {
                    values[i] = val_str;
                    break;
                }
            }
        }
    }
    finish_group();
    npi_fsdb_release_vct(vct);

    result.incomplete_write_count = static_cast<int>(pending_writes.size());
    for (const auto& kv : pending_reads) result.incomplete_read_count += static_cast<int>(kv.second.size());

    std::sort(result.writes.begin(), result.writes.end(), txn_less);
    std::sort(result.reads.begin(), result.reads.end(), txn_less);
    return true;
}

bool AxiExporter::write_files(const std::string& output_prefix,
                              const AxiExportResult& result,
                              std::string& write_file,
                              std::string& read_file,
                              std::string& meta_file,
                              std::string& error) const {
    std::string suffix = result.format == "csv" ? ".csv" : ".tsv";
    write_file = output_prefix + ".write" + suffix;
    read_file = output_prefix + ".read" + suffix;
    meta_file = output_prefix + ".meta.json";
    ensure_parent_dir(write_file);
    char sep = sep_for(result.format);

    {
        std::ofstream out(write_file.c_str());
        if (!out) {
            error = "failed to write AXI write export: " + write_file;
            return false;
        }
        write_header(out, sep);
        for (const auto& txn : result.writes) write_txn(out, sep, txn);
    }
    {
        std::ofstream out(read_file.c_str());
        if (!out) {
            error = "failed to write AXI read export: " + read_file;
            return false;
        }
        write_header(out, sep);
        for (const auto& txn : result.reads) write_txn(out, sep, txn);
    }
    {
        std::ofstream out(meta_file.c_str());
        if (!out) {
            error = "failed to write AXI export meta: " + meta_file;
            return false;
        }
        out << axi_export_meta_json(result, write_file, read_file, meta_file).dump(2) << "\n";
    }
    return true;
}

Json axi_export_meta_json(const AxiExportResult& result,
                          const std::string& write_file,
                          const std::string& read_file,
                          const std::string& meta_file) {
    Json meta;
    meta["name"] = result.name;
    meta["format"] = result.format;
    meta["begin"] = format_time(result.begin);
    meta["end"] = format_time(result.end);
    meta["scan_begin"] = format_time(result.scan_begin);
    meta["scan_end"] = format_time(result.scan_end);
    meta["write_file"] = write_file;
    meta["read_file"] = read_file;
    meta["meta_file"] = meta_file;
    meta["write_count"] = result.writes.size();
    meta["read_count"] = result.reads.size();
    meta["total_count"] = result.writes.size() + result.reads.size();
    meta["unique_write_ids"] = ids_json(result.write_count_by_id);
    meta["unique_read_ids"] = ids_json(result.read_count_by_id);
    meta["write_count_by_id"] = map_to_json(result.write_count_by_id);
    meta["read_count_by_id"] = map_to_json(result.read_count_by_id);
    meta["max_write_outstanding_by_id"] = map_to_json(result.max_write_outstanding_by_id);
    meta["max_read_outstanding_by_id"] = map_to_json(result.max_read_outstanding_by_id);
    meta["max_total_write_outstanding"] = result.max_total_write_outstanding;
    meta["max_total_read_outstanding"] = result.max_total_read_outstanding;
    meta["burst_histogram"] = map_to_json(result.burst_histogram);
    meta["beat_count_mismatch_count"] = result.beat_count_mismatch_count;
    meta["incomplete_write_count"] = result.incomplete_write_count;
    meta["incomplete_read_count"] = result.incomplete_read_count;
    meta["reset_cleared_write_count"] = result.reset_cleared_write_count;
    meta["reset_cleared_read_count"] = result.reset_cleared_read_count;
    return meta;
}

} // namespace xdebug_waveform
