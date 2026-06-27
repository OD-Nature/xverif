#include "../server_internal.h"

namespace xdebug_waveform {

int direction_filter(const Json& args) {
    std::string direction = args.value("direction", std::string("all"));
    if (direction == "wr" || direction == "write") return 1;
    if (direction == "rd" || direction == "read") return 2;
    return 0;
}

bool ensure_apb_analyzed_for_ai(const std::string& name, std::string& error) {
    xdebug_waveform::ApbConfig config;
    if (!read_apb_from_registry(g_session_id, name.c_str(), config)) {
        error = "APB config not found: " + name;
        return false;
    }
    if (!g_apb_analyzer.analyze(name, g_fsdb_file, config)) {
        error = "Failed to analyze APB: " + name;
        return false;
    }
    return true;
}

bool ensure_axi_analyzed_for_ai(const std::string& name, std::string& error) {
    xdebug_waveform::AxiConfig config;
    if (!read_axi_from_registry(g_session_id, name.c_str(), config)) {
        error = "AXI config not found: " + name;
        return false;
    }
    if (!g_axi_analyzer.analyze(name, g_fsdb_file, config)) {
        error = "Failed to analyze AXI: " + name;
        return false;
    }
    return true;
}

Json ai_apb_transfer_window(const Json& args, std::string& error) {
    std::string name = args.value("name", std::string());
    if (name.empty()) {
        error = "apb.transfer_window requires args.name";
        return Json();
    }
    npiFsdbTime begin = 0, end = 0;
    if (!json_time_range(args, begin, end, error)) return Json();
    if (!ensure_apb_analyzed_for_ai(name, error)) return Json();
    std::vector<xdebug_waveform::ApbContextTransaction> txns;
    int filter = direction_filter(args);
    int limit = args.value("max_rows", args.value("limit", 1000));
    int fetch_limit = (filter == 0 && limit >= 0) ? limit + 1 : -1;
    if (!g_apb_analyzer.get_transactions_in_range(name, begin, end, txns, fetch_limit)) {
        error = "APB config not analyzed: " + name;
        return Json();
    }
    Json arr = Json::array();
    bool truncated = false;
    for (const auto& item : txns) {
        if (!item.txn) continue;
        if (filter == 1 && !item.txn->is_write) continue;
        if (filter == 2 && item.txn->is_write) continue;
        if (limit >= 0 && static_cast<int>(arr.size()) >= limit) {
            truncated = true;
            break;
        }
        Json txn = apb_txn_to_json(item.txn, true);
        txn["time_ps"] = item.txn->time;
        arr.push_back(txn);
    }
    Json out;
    out["summary"] = {{"name", name},
                      {"begin", format_time(begin)},
                      {"end", format_time(end)},
                      {"transaction_count", arr.size()}};
    if (truncated) out["summary"]["truncated"] = true;
    out["transactions"] = arr;
    if (truncated) out["truncated"] = true;
    return out;
}

Json ai_axi_transactions_window(const Json& args, std::string& error) {
    std::string name = args.value("name", std::string());
    if (name.empty()) {
        error = "AXI action requires args.name";
        return Json();
    }
    npiFsdbTime begin = 0, end = 0;
    if (!json_time_range(args, begin, end, error)) return Json();
    if (!ensure_axi_analyzed_for_ai(name, error)) return Json();
    std::vector<xdebug_waveform::AxiContextTransaction> txns;
    int filter = direction_filter(args);
    int limit = args.value("max_rows", args.value("limit", 1000));
    int fetch_limit = (filter == 0 && limit >= 0) ? limit + 1 : -1;
    if (!g_axi_analyzer.get_transactions_in_range(name, begin, end, txns, fetch_limit)) {
        error = "AXI config not analyzed: " + name;
        return Json();
    }
    Json arr = Json::array();
    bool truncated = false;
    for (const auto& item : txns) {
        if (!item.txn) continue;
        if (filter == 1 && !item.txn->is_write) continue;
        if (filter == 2 && item.txn->is_write) continue;
        if (limit >= 0 && static_cast<int>(arr.size()) >= limit) {
            truncated = true;
            break;
        }
        Json txn = axi_txn_to_json(item.txn);
        txn["match_time"] = format_time(item.match_time);
        txn["match_time_ps"] = item.match_time;
        txn["latency_ps"] = item.txn->resp_time >= item.txn->addr_time ? item.txn->resp_time - item.txn->addr_time : 0;
        arr.push_back(txn);
    }
    return Json{{"name", name}, {"begin", format_time(begin)}, {"end", format_time(end)},
                {"transaction_count", arr.size()}, {"truncated", truncated}, {"transactions", arr}};
}

Json ai_axi_latency_outlier(const Json& args, std::string& error) {
    Json data = ai_axi_transactions_window(args, error);
    if (!error.empty()) return Json();
    Json txns = data["transactions"];
    std::vector<Json> vec;
    for (const auto& t : txns) vec.push_back(t);
    std::sort(vec.begin(), vec.end(), [](const Json& a, const Json& b) {
        return a.value("latency_ps", 0ULL) > b.value("latency_ps", 0ULL);
    });
    int top_n = args.value("top_n", 10);
    Json out = Json::array();
    for (size_t i = 0; i < vec.size() && static_cast<int>(i) < top_n; ++i) out.push_back(vec[i]);
    data["outliers"] = out;
    data.erase("transactions");
    data["outlier_count"] = out.size();
    return data;
}

Json ai_axi_outstanding_timeline(const Json& args, std::string& error) {
    std::string name = args.value("name", std::string());
    if (name.empty()) {
        error = "axi.outstanding_timeline requires args.name";
        return Json();
    }
    npiFsdbTime begin = 0, end = 0;
    if (!json_time_range(args, begin, end, error)) return Json();
    if (!ensure_axi_analyzed_for_ai(name, error)) return Json();
    std::vector<xdebug_waveform::AxiOutstandingSample> samples;
    int limit = args.value("max_rows", args.value("limit", 1000));
    int fetch_limit = limit >= 0 ? limit + 1 : -1;
    if (!g_axi_analyzer.get_outstanding_samples_in_range(name, begin, end, samples, fetch_limit)) {
        error = "AXI config not analyzed: " + name;
        return Json();
    }
    int filter = direction_filter(args);
    Json arr = Json::array();
    bool truncated = false;
    for (const auto& s : samples) {
        if (limit >= 0 && static_cast<int>(arr.size()) >= limit) {
            truncated = true;
            break;
        }
        Json item;
        item["time"] = format_time(s.time);
        item["time_ps"] = s.time;
        if (filter == 0 || filter == 2) item["read"] = s.read;
        if (filter == 0 || filter == 1) item["write"] = s.write;
        arr.push_back(item);
    }
    return Json{{"name", name}, {"sample_count", arr.size()}, {"truncated", truncated}, {"samples", arr}};
}

Json ai_axi_channel_stall(const Json& args, std::string& error) {
    std::string name = args.value("name", std::string());
    std::string channel = args.value("channel", std::string("ar"));
    xdebug_waveform::AxiConfig cfg;
    if (name.empty()) {
        error = "axi.channel_stall requires args.name";
        return Json();
    }
    if (!read_axi_from_registry(g_session_id, name.c_str(), cfg)) {
        error = "AXI config not found: " + name;
        return Json();
    }
    npiFsdbTime begin = 0, end = 0;
    if (!json_time_range(args, begin, end, error)) return Json();
    std::string valid, ready;
    if (channel == "aw") { valid = cfg.awvalid; ready = cfg.awready; }
    else if (channel == "w") { valid = cfg.wvalid; ready = cfg.wready; }
    else if (channel == "b") { valid = cfg.bvalid; ready = cfg.bready; }
    else if (channel == "r") { valid = cfg.rvalid; ready = cfg.rready; }
    else { valid = cfg.arvalid; ready = cfg.arready; channel = "ar"; }

    npiFsdbSigHandle clk_h = npi_fsdb_sig_by_name(g_fsdb_file, cfg.clk.c_str(), NULL);
    npiFsdbSigHandle valid_h = npi_fsdb_sig_by_name(g_fsdb_file, valid.c_str(), NULL);
    npiFsdbSigHandle ready_h = npi_fsdb_sig_by_name(g_fsdb_file, ready.c_str(), NULL);
    if (!clk_h || !valid_h || !ready_h) {
        error = "AXI channel signal not found for channel: " + channel;
        return Json();
    }

    Json rules = args.value("rules", Json::object());
    int max_wait = rules.value("max_wait_cycles", 100);
    int max_samples = args.value("max_samples", 1000000);
    int sample_count = 0, transfers = 0, ready_only = 0, max_stall = 0;
    bool truncated = false;
    Json findings = Json::array();

    fsdbSigVec_t state_handles;
    state_handles.push_back(valid_h);
    state_handles.push_back(ready_h);
    fsdbValVec_t init_values;
    if (!npi_fsdb_sig_hdl_vec_value_at(state_handles, begin, init_values, npiFsdbBinStrVal) ||
        init_values.size() != state_handles.size()) {
        error = "Failed to read AXI channel initial values";
        return Json();
    }
    std::string valid_value = with_value_prefix(init_values[0], 'b');
    std::string ready_value = with_value_prefix(init_values[1], 'b');

    auto visit_interval = [&](npiFsdbTime start, npiFsdbTime stop) -> bool {
        if (stop < start) return true;
        ExprTri v = xdebug_waveform::expr_truth_value(valid_value);
        ExprTri r = xdebug_waveform::expr_truth_value(ready_value);
        bool interesting = (v == ExprTri::True || r == ExprTri::True);
        if (!interesting) return true;
        ClockEdgeCursor edge_cursor(clk_h, cfg.posedge);
        if (!edge_cursor.valid()) {
            error = "Failed to create AXI channel clock cursor";
            return false;
        }
        npiFsdbTime edge_time = 0;
        if (!edge_cursor.first_at_or_after(start, edge_time)) return true;
        int stall_cycles = 0;
        npiFsdbTime stall_begin = 0;
        while (edge_time <= stop) {
            if (max_samples >= 0 && sample_count >= max_samples) {
                truncated = true;
                return false;
            }
            ++sample_count;
            if (v == ExprTri::True && r == ExprTri::True) {
                ++transfers;
                if (stall_cycles > 0) {
                    if (stall_cycles > max_stall) max_stall = stall_cycles;
                    if (stall_cycles > max_wait) {
                        findings.push_back({{"type", "long_stall"}, {"severity", "warning"},
                                            {"begin", format_time(stall_begin)}, {"end", format_time(edge_time)},
                                            {"cycles", stall_cycles}});
                    }
                    stall_cycles = 0;
                }
            } else if (v == ExprTri::True && r == ExprTri::False) {
                if (stall_cycles == 0) stall_begin = edge_time;
                ++stall_cycles;
            } else if (r == ExprTri::True && v == ExprTri::False) {
                ++ready_only;
            }
            npiFsdbTime next_edge = 0;
            if (!edge_cursor.next(next_edge)) break;
            if (next_edge == edge_time) break;
            edge_time = next_edge;
        }
        if (stall_cycles > 0) {
            if (stall_cycles > max_stall) max_stall = stall_cycles;
            if (stall_cycles > max_wait) {
                findings.push_back({{"type", "long_stall"}, {"severity", "warning"},
                                    {"begin", format_time(stall_begin)}, {"end", format_time(stop)},
                                    {"cycles", stall_cycles}});
            }
        }
        return true;
    };

    TimeBasedVcIterGuard guard;
    npiFsdbTimeBasedVcIter& iter = guard.iter();
    iter.add(valid_h);
    iter.add(ready_h);
    guard.start(begin, end);
    npiFsdbTime interval_begin = begin;
    npiFsdbTime curr_time = 0;
    npiFsdbSigHandle changed_sig = nullptr;
    bool keep = true;
    while (keep && iter.iter_next(curr_time, changed_sig) > 0) {
        if (curr_time > end) break;
        if (curr_time > interval_begin) {
            keep = visit_interval(interval_begin, curr_time - 1);
            if (!keep) break;
            interval_begin = curr_time;
        }
        npiFsdbValue val;
        val.format = npiFsdbBinStrVal;
        if (iter.get_value(val) && val.value.str) {
            if (changed_sig == valid_h) valid_value = with_value_prefix(val.value.str, 'b');
            else if (changed_sig == ready_h) ready_value = with_value_prefix(val.value.str, 'b');
        }
    }
    if (keep && interval_begin <= end) visit_interval(interval_begin, end);

    Json data;
    data["sample_count"] = sample_count;
    data["transfer_count"] = transfers;
    data["max_stall_cycles"] = max_stall;
    data["ready_without_valid_cycles"] = ready_only;
    data["data_stability_violations"] = 0;
    data["truncated"] = truncated;
    data["findings"] = findings;
    data["name"] = name;
    data["channel"] = channel;
    return data;
}

Json cursor_to_json(const Cursor& c) {
    Json j;
    j["name"] = c.name;
    j["time"] = c.time;
    j["time_text"] = c.time_text.empty() ? format_time(c.time) : c.time_text;
    j["note"] = c.note;
    j["origin"] = c.origin;
    j["clock"] = c.clock;
    j["created_at"] = c.created_at;
    j["updated_at"] = c.updated_at;
    return j;
}

Json resolved_time_json(const std::string& spec, npiFsdbTime time) {
    Json j;
    j["source"] = spec;
    j["time"] = format_time(time);
    j["time_value"] = time;
    return j;
}

Json ai_cursor_action(const std::string& action, const Json& args, std::string& error) {
    CursorManager cm;
    if (action == "cursor.set") {
        std::string name = args.value("name", std::string());
        std::string spec = args.value("time", args.value("at", std::string()));
        if (name.empty() || spec.empty()) {
            error = "cursor.set requires args.name and args.time";
            return Json();
        }
        npiFsdbTime t = 0;
        if (!parse_user_time(spec.c_str(), false, t, error)) return Json();
        Cursor c;
        c.name = name;
        c.time = t;
        c.time_text = format_time(t);
        c.note = args.value("note", std::string());
        c.origin = args.value("origin", std::string("manual"));
        c.clock = args.value("clock", std::string());
        if (!cm.set_cursor(g_session_id, c, args.value("active", true))) {
            error = "failed to save cursor: " + name;
            return Json();
        }
        Cursor saved;
        cm.get_cursor(g_session_id, name, saved);
        Json data;
        data["cursor"] = cursor_to_json(saved);
        data["resolved_time"] = resolved_time_json(spec, t);
        data["status"] = "set";
        return data;
    }
    if (action == "cursor.get") {
        std::string name = args.value("name", std::string());
        if (name.empty()) {
            error = "cursor.get requires args.name";
            return Json();
        }
        Cursor c;
        if (!cm.get_cursor(g_session_id, name, c)) {
            error = "CURSOR_NOT_FOUND: Cursor '" + name + "' does not exist";
            return Json();
        }
        Json data;
        data["cursor"] = cursor_to_json(c);
        return data;
    }
    if (action == "cursor.list") {
        Json arr = Json::array();
        for (const auto& c : cm.list_cursors(g_session_id)) arr.push_back(cursor_to_json(c));
        std::string active;
        cm.get_active_cursor(g_session_id, active);
        Json data;
        data["cursors"] = arr;
        data["active_cursor"] = active;
        data["cursor_count"] = arr.size();
        return data;
    }
    if (action == "cursor.delete") {
        std::string name = args.value("name", std::string());
        if (name.empty()) {
            error = "cursor.delete requires args.name";
            return Json();
        }
        if (!cm.delete_cursor(g_session_id, name)) {
            error = "CURSOR_NOT_FOUND: Cursor '" + name + "' does not exist";
            return Json();
        }
        Json data;
        data["status"] = "deleted";
        data["name"] = name;
        return data;
    }
    if (action == "cursor.use") {
        std::string name = args.value("name", std::string());
        if (name.empty()) {
            error = "cursor.use requires args.name";
            return Json();
        }
        if (!cm.use_cursor(g_session_id, name)) {
            error = "CURSOR_NOT_FOUND: Cursor '" + name + "' does not exist";
            return Json();
        }
        Cursor c;
        cm.get_cursor(g_session_id, name, c);
        Json data;
        data["status"] = "active";
        data["active_cursor"] = name;
        data["cursor"] = cursor_to_json(c);
        return data;
    }
    error = "Unsupported cursor action: " + action;
    return Json();
}

Json ai_dispatch_query(const Json& req, std::string& error) {
    std::string action = req.value("action", std::string());
    Json args = req.value("args", Json::object());
    Json limits = req.value("limits", Json::object());
    for (auto it = limits.begin(); it != limits.end(); ++it) {
        if (!args.contains(it.key())) args[it.key()] = it.value();
    }
    if (action == "expr.eval_at") return ai_expr_eval_at(args, error);
    if (action == "window.verify") return ai_window_verify(args, error);
    if (action == "signal.changes") return ai_signal_changes(args, error);
    if (action == "signal.stability") return ai_signal_stability(args, error);
    if (action == "signal.trend") return ai_signal_trend(args, error);
    if (action == "signal.statistics") return ai_signal_statistics(args, error);
    if (action == "counter.statistics") return ai_counter_statistics(args, error);
    if (action == "sampled_pulse.inspect") return ai_sampled_pulse_inspect(args, error);
    if (action == "inspect_signal") return ai_inspect_signal(args, error);
    if (action == "detect_anomaly") return ai_detect_anomaly(args, error);
    if (action == "handshake.inspect") return ai_handshake_inspect(args, error);
    if (action == "apb.transfer_window") return ai_apb_transfer_window(args, error);
    if (action == "axi.request_response_pair") return ai_axi_transactions_window(args, error);
    if (action == "axi.latency_outlier") return ai_axi_latency_outlier(args, error);
    if (action == "axi.outstanding_timeline") return ai_axi_outstanding_timeline(args, error);
    if (action == "axi.channel_stall") return ai_axi_channel_stall(args, error);
    if (action.compare(0, 7, "cursor.") == 0) return ai_cursor_action(action, args, error);
    error = "Unsupported AI action in server: " + action;
    return Json();
}


}  // namespace xdebug_waveform
