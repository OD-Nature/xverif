#include "../server_internal.h"

namespace xdebug_waveform {

bool read_signal_changes(const std::string& signal,
                                npiFsdbTime begin,
                                npiFsdbTime end,
                                npiFsdbValType fmt,
                                fsdbTimeValPairVec_t& changes,
                                std::string& error,
                                int max_changes,
                                bool* truncated) {
    changes.clear();
    if (truncated) *truncated = false;
    npiFsdbSigHandle sig = npi_fsdb_sig_by_name(g_fsdb_file, signal.c_str(), NULL);
    if (!sig) {
        error = "Signal not found: " + signal;
        return false;
    }
    TimeBasedVcIterGuard guard;
    npiFsdbTimeBasedVcIter& iter = guard.iter();
    iter.add(sig);
    guard.start(begin, end);
    npiFsdbTime t = 0;
    npiFsdbSigHandle changed_sig = nullptr;
    while (iter.iter_next(t, changed_sig) > 0) {
        if (max_changes >= 0 && static_cast<int>(changes.size()) >= max_changes) {
            if (truncated) *truncated = true;
            break;
        }
        npiFsdbValue val;
        val.format = fmt;
        std::string value;
        if (!iter.get_value(val) || !val.value.str) continue;
        value = val.value.str;
        changes.push_back(std::make_pair(t, value));
    }
    return true;
}

Json changes_to_json(const fsdbTimeValPairVec_t& changes,
                            char prefix,
                            int limit,
                            bool& truncated) {
    Json arr = Json::array();
    truncated = false;
    for (size_t i = 0; i < changes.size(); ++i) {
        if (limit >= 0 && static_cast<int>(arr.size()) >= limit) {
            truncated = true;
            break;
        }
        Json item;
        item["time"] = format_time(changes[i].first);
        item["value"] = wave_value_json(changes[i].second, prefix);
        arr.push_back(item);
    }
    return arr;
}

bool build_signal_alias_handles(const Json& signals,
                                       std::vector<std::string>& aliases,
                                       std::vector<std::string>& paths,
                                       fsdbSigVec_t& handles,
                                       std::string& error) {
    if (!signals.is_object()) {
        error = "signals must be an object";
        return false;
    }
    std::map<std::string, std::string> seen;
    for (auto it = signals.begin(); it != signals.end(); ++it) {
        if (!it.value().is_string()) {
            error = "signal path must be string for alias: " + it.key();
            return false;
        }
        std::string alias = it.key();
        std::string path = it.value().get<std::string>();
        auto prev = seen.find(alias);
        if (prev != seen.end() && prev->second != path) {
            error = "alias maps to different signals: " + alias;
            return false;
        }
        if (prev != seen.end()) continue;
        npiFsdbSigHandle sig = npi_fsdb_sig_by_name(g_fsdb_file, path.c_str(), NULL);
        if (!sig) {
            error = "Signal not found: " + path;
            return false;
        }
        seen[alias] = path;
        aliases.push_back(alias);
        paths.push_back(path);
        handles.push_back(sig);
    }
    return true;
}

namespace {

std::string trim_copy(const std::string& text) {
    size_t begin = 0;
    while (begin < text.size() && std::isspace(static_cast<unsigned char>(text[begin]))) ++begin;
    size_t end = text.size();
    while (end > begin && std::isspace(static_cast<unsigned char>(text[end - 1]))) --end;
    return text.substr(begin, end - begin);
}

std::string bit_string_from_value(const std::string& value) {
    std::string bits = xdebug_waveform::expr_bits_only(value);
    for (char& c : bits) c = static_cast<char>(std::tolower(static_cast<unsigned char>(c)));
    return bits;
}

Json bit_value_json(const std::string& bits) {
    Json value;
    value["value"] = std::string("'b") + bits;
    value["known"] = !bits.empty() && !xdebug_waveform::expr_value_has_unknown(bits);
    value["width"] = bits.size();
    return value;
}

std::string pad_bits_for_compare(const std::string& bits, size_t width) {
    if (bits.size() >= width) return bits;
    return std::string(width - bits.size(), '0') + bits;
}

int compare_bit_strings(const std::string& lhs, const std::string& rhs) {
    size_t width = std::max(lhs.size(), rhs.size());
    std::string a = pad_bits_for_compare(lhs, width);
    std::string b = pad_bits_for_compare(rhs, width);
    if (a == b) return 0;
    return a < b ? -1 : 1;
}

bool bits_to_u64(const std::string& bits, uint64_t& out, std::string& error) {
    if (bits.empty()) {
        error = "INVALID_REQUEST: counter value is empty";
        return false;
    }
    if (bits.size() > 64) {
        error = "INVALID_REQUEST: counter width exceeds 64 bits";
        return false;
    }
    if (xdebug_waveform::expr_value_has_unknown(bits)) {
        return false;
    }
    uint64_t value = 0;
    for (char c : bits) {
        if (c != '0' && c != '1') {
            error = "INVALID_REQUEST: counter value contains non-binary data";
            return false;
        }
        value = (value << 1) | (c == '1' ? 1ULL : 0ULL);
    }
    out = value;
    return true;
}

std::string u64_to_decimal(uint64_t value) {
    std::ostringstream oss;
    oss << value;
    return oss.str();
}

std::string long_double_to_decimal(long double value) {
    std::ostringstream oss;
    oss.setf(std::ios::fixed);
    oss.precision(6);
    oss << static_cast<double>(value);
    std::string text = oss.str();
    while (text.size() > 1 && text.back() == '0') text.pop_back();
    if (!text.empty() && text.back() == '.') text.pop_back();
    return text;
}

bool add_signal_alias(Json& signals,
                      const std::string& alias,
                      const std::string& path,
                      std::string& error) {
    if (path.empty()) {
        error = "INVALID_REQUEST: signal path must not be empty";
        return false;
    }
    if (signals.contains(alias) && signals[alias].get<std::string>() != path) {
        error = "INVALID_REQUEST: duplicate alias maps to different signals: " + alias;
        return false;
    }
    signals[alias] = path;
    return true;
}

struct CounterInput {
    std::string expr;
    std::vector<std::string> aliases;
    std::vector<std::string> paths;
};

bool parse_counter_concat(const std::string& text,
                          CounterInput& out,
                          std::string& error) {
    std::string trimmed = trim_copy(text);
    if (trimmed.empty()) {
        error = "INVALID_REQUEST: counter.statistics requires non-empty args.cnt";
        return false;
    }
    if (trimmed.front() != '{') {
        out.aliases.push_back("__cnt0");
        out.paths.push_back(trimmed);
        return true;
    }
    if (trimmed.size() < 3 || trimmed.back() != '}') {
        error = "INVALID_REQUEST: counter concat must be {signal[,signal...]}";
        return false;
    }
    std::string body = trimmed.substr(1, trimmed.size() - 2);
    size_t start = 0;
    int index = 0;
    while (start <= body.size()) {
        size_t comma = body.find(',', start);
        std::string part = trim_copy(body.substr(start, comma == std::string::npos ? std::string::npos : comma - start));
        if (part.empty() || part.find('{') != std::string::npos || part.find('}') != std::string::npos ||
            part.find('\'') != std::string::npos) {
            error = "INVALID_REQUEST: counter concat supports signal paths only";
            return false;
        }
        out.aliases.push_back("__cnt" + std::to_string(index++));
        out.paths.push_back(part);
        if (comma == std::string::npos) break;
        start = comma + 1;
    }
    return !out.paths.empty();
}

bool build_counter_inputs(const Json& args,
                          Json& signal_union,
                          std::string& valid_expr,
                          CounterInput& counter,
                          std::string& error) {
    if (!args.contains("vld")) {
        error = "MISSING_FIELD: counter.statistics requires args.vld";
        return false;
    }
    if (!args.contains("cnt")) {
        error = "MISSING_FIELD: counter.statistics requires args.cnt";
        return false;
    }

    const Json& vld = args["vld"];
    if (vld.is_string()) {
        valid_expr = "__vld";
        if (!add_signal_alias(signal_union, "__vld", vld.get<std::string>(), error)) return false;
    } else if (vld.is_object()) {
        valid_expr = server_compact_expr_ws(vld.value("expr", std::string()));
        if (valid_expr.empty() || !vld.contains("signals") || !vld["signals"].is_object()) {
            error = "INVALID_REQUEST: object args.vld requires expr and signals";
            return false;
        }
        for (auto it = vld["signals"].begin(); it != vld["signals"].end(); ++it) {
            if (!it.value().is_string()) {
                error = "INVALID_REQUEST: args.vld.signals values must be string paths";
                return false;
            }
            if (!add_signal_alias(signal_union, it.key(), it.value().get<std::string>(), error)) return false;
        }
    } else {
        error = "INVALID_REQUEST: args.vld must be a signal path or expression object";
        return false;
    }

    if (!args["cnt"].is_string()) {
        error = "INVALID_REQUEST: counter.statistics args.cnt must be a signal path or concat string";
        return false;
    }
    if (!parse_counter_concat(args["cnt"].get<std::string>(), counter, error)) return false;
    for (size_t i = 0; i < counter.aliases.size(); ++i) {
        if (!add_signal_alias(signal_union, counter.aliases[i], counter.paths[i], error)) return false;
    }
    return true;
}

std::string counter_bits_from_values(const CounterInput& counter,
                                     const std::map<std::string, std::string>& values) {
    std::string bits;
    for (const auto& alias : counter.aliases) {
        auto it = values.find(alias);
        if (it == values.end()) return "";
        bits += bit_string_from_value(it->second);
    }
    return bits;
}

} // namespace

Json ai_signal_changes(const Json& args, std::string& error) {
    std::string signal = args.value("signal", std::string());
    if (signal.empty()) {
        error = "signal.changes requires args.signal";
        return Json();
    }
    npiFsdbTime begin = 0, end = 0;
    if (!json_time_range(args, begin, end, error)) return Json();
    int limit = args.value("limit", args.value("max_events", 1000));
    std::string mode = args.value("mode", std::string("head"));
    bool aggregate_only = args.value("aggregate_only", false);
    bool include_rows = args.value("include_rows", args.value("include_all_changes", false));
    npiFsdbValType fmt = json_value_format(args);
    fsdbTimeValPairVec_t changes;
    bool truncated = false;
    if (!read_signal_changes(signal, begin, end, fmt, changes, error, -1, &truncated)) return Json();
    size_t row_count = changes.size();
    bool includes_initial = row_count > 0;
    size_t actual_transitions = includes_initial ? row_count - 1 : 0;
    Json data;
    data["signal"] = signal;
    data["begin"] = format_time(begin);
    data["end"] = format_time(end);
    data["returned_change_rows"] = row_count;
    data["includes_initial_value"] = includes_initial;
    data["actual_transition_count"] = actual_transitions;
    data["semantic_note"] = "signal.changes returns value-change rows for timeline inspection. Do not use row counts as sampled high cycles; use signal.statistics.high_cycles for clock-sampled activity.";
    data["transition_count"] = actual_transitions;
    data["truncated"] = truncated;
    if (!changes.empty()) {
        data["initial_value"] = wave_value_json(changes.front().second, json_value_prefix(fmt));
        data["final_value"] = wave_value_json(changes.back().second, json_value_prefix(fmt));
        data["first_change"] = format_time(changes.front().first);
        data["last_change"] = format_time(changes.back().first);
    }
    if (row_count > 1000 && !include_rows && !aggregate_only) {
        data["warnings"] = Json::array({
            "signal.changes matched more than 1000 change rows. Compact output omits rows by default; use aggregate_only:true, mode:head/tail, or narrow time_range unless timeline rows are required."
        });
    }
    if (include_rows && !aggregate_only) {
        fsdbTimeValPairVec_t selected = changes;
        if (limit >= 0 && selected.size() > static_cast<size_t>(limit)) {
            if (mode == "tail") {
                selected.erase(selected.begin(), selected.end() - limit);
            } else {
                selected.erase(selected.begin() + limit, selected.end());
            }
            data["truncated"] = true;
        }
        data["mode"] = mode == "tail" ? "tail" : "head";
        bool rows_truncated = false;
        data["changes"] = changes_to_json(selected, json_value_prefix(fmt), -1, rows_truncated);
    }
    return data;
}

Json ai_signal_stability(const Json& args, std::string& error) {
    std::string signal = args.value("signal", std::string());
    if (signal.empty()) {
        error = "signal.stability requires args.signal";
        return Json();
    }
    npiFsdbTime begin = 0, end = 0;
    if (!json_time_range(args, begin, end, error)) return Json();
    npiFsdbValType fmt = json_value_format(args);
    bool truncated = false;
    npiFsdbSigHandle sig = npi_fsdb_sig_by_name(g_fsdb_file, signal.c_str(), NULL);
    if (!sig) {
        error = "Signal not found: " + signal;
        return Json();
    }
    Json arr = Json::array();
    bool stable = true;
    std::string first;
    TimeBasedVcIterGuard guard;
    npiFsdbTimeBasedVcIter& iter = guard.iter();
    iter.add(sig);
    guard.start(begin, end);
    npiFsdbTime change_time = 0;
    npiFsdbSigHandle changed_sig = nullptr;
    while (iter.iter_next(change_time, changed_sig) > 0) {
        npiFsdbValue val;
        val.format = fmt;
        if (!iter.get_value(val) || !val.value.str) continue;
        std::string text = value_with_prefix(val.value.str, json_value_prefix(fmt));
        Json item;
        item["time"] = format_time(change_time);
        item["value"] = wave_value_json(val.value.str, json_value_prefix(fmt));
        arr.push_back(item);
        if (first.empty()) {
            first = text;
        } else if (text != first) {
            stable = false;
            break;
        }
    }

    Json data;
    data["signal"] = signal;
    data["begin"] = format_time(begin);
    data["end"] = format_time(end);
    data["changes"] = arr;
    data["transition_count"] = arr.size();
    data["truncated"] = truncated;
    if (!arr.empty()) {
        data["initial_value"] = arr[0]["value"];
        data["final_value"] = arr[arr.size() - 1]["value"];
        data["first_change"] = arr[0]["time"];
        data["last_change"] = arr[arr.size() - 1]["time"];
    }
    if (!stable) {
        for (const auto& item : arr) {
            if (item["value"]["value"].get<std::string>() != first) {
                data["first_change_time"] = item["time"];
                break;
            }
        }
    }
    data["stable"] = stable;
    if (stable && !arr.empty()) data["value"] = arr[0]["value"];
    return data;
}

bool sample_on_clock(const std::string& clock_path,
                            bool posedge,
                            const std::vector<std::string>& aliases,
                            const fsdbSigVec_t& signal_handles,
                            npiFsdbTime begin,
                            npiFsdbTime end,
                            int max_samples,
                            std::function<bool(npiFsdbTime, const std::map<std::string, std::string>&)> cb,
                            std::string& error,
                            int& sample_count,
                            bool& truncated) {
    sample_count = 0;
    truncated = false;
    npiFsdbSigHandle clk = npi_fsdb_sig_by_name(g_fsdb_file, clock_path.c_str(), NULL);
    if (!clk) {
        error = "Clock signal not found: " + clock_path;
        return false;
    }
    fsdbSigVec_t all_handles;
    all_handles.push_back(clk);
    for (auto h : signal_handles) all_handles.push_back(h);
    fsdbValVec_t init_values;
    npiFsdbTime init_time = begin > 0 ? begin - 1 : begin;
    if (!npi_fsdb_sig_hdl_vec_value_at(all_handles, init_time, init_values, npiFsdbBinStrVal) ||
        init_values.size() != all_handles.size()) {
        error = "Failed to read initial sampled values";
        return false;
    }
    std::string prev_clk = with_value_prefix(init_values[0], 'b');
    std::vector<std::string> values(signal_handles.size(), "'b0");
    for (size_t i = 0; i < signal_handles.size(); ++i) values[i] = with_value_prefix(init_values[i + 1], 'b');

    TimeBasedVcIterGuard guard;
    npiFsdbTimeBasedVcIter& iter = guard.iter();
    iter.add(clk);
    for (auto h : signal_handles) iter.add(h);
    guard.start(begin, end);

    bool have_group = false;
    bool edge = false;
    npiFsdbTime group_time = 0;
    auto finish_group = [&]() -> bool {
        if (!have_group || !edge) return true;
        std::map<std::string, std::string> value_map;
        for (size_t i = 0; i < aliases.size(); ++i) value_map[aliases[i]] = values[i];
        ++sample_count;
        if (max_samples >= 0 && sample_count > max_samples) {
            truncated = true;
            return false;
        }
        return cb(group_time, value_map);
    };

    npiFsdbTime curr_time = 0;
    npiFsdbSigHandle changed_sig = nullptr;
    bool keep = true;
    while (keep && iter.iter_next(curr_time, changed_sig) > 0) {
        if (!have_group) {
            have_group = true;
            group_time = curr_time;
        } else if (curr_time != group_time) {
            keep = finish_group();
            if (!keep) break;
            group_time = curr_time;
            edge = false;
        }
        npiFsdbValue val;
        val.format = npiFsdbBinStrVal;
        if (!iter.get_value(val) || !val.value.str) continue;
        std::string v = with_value_prefix(val.value.str, 'b');
        if (changed_sig == clk) {
            ExprTri old_clk = xdebug_waveform::expr_truth_value(prev_clk);
            ExprTri new_clk = xdebug_waveform::expr_truth_value(v);
            edge = posedge ? (old_clk == ExprTri::False && new_clk == ExprTri::True)
                           : (old_clk == ExprTri::True && new_clk == ExprTri::False);
            prev_clk = v;
        } else {
            for (size_t i = 0; i < signal_handles.size(); ++i) {
                if (signal_handles[i] == changed_sig) {
                    values[i] = v;
                }
            }
        }
    }
    if (keep) finish_group();
    return error.empty();
}

Json ai_expr_eval_at(const Json& args, std::string& error) {
    std::string time_s = args.value("at", args.value("time", std::string()));
    std::string expr = server_compact_expr_ws(args.value("expr", std::string()));
    if (time_s.empty() || expr.empty() || !args.contains("signals")) {
        error = "expr.eval_at requires args.time/args.at, args.expr and args.signals";
        return Json();
    }
    npiFsdbTime t = 0;
    if (!parse_user_time(time_s.c_str(), false, t, error)) return Json();
    std::vector<std::string> aliases, paths;
    fsdbSigVec_t handles;
    if (!build_signal_alias_handles(args["signals"], aliases, paths, handles, error)) return Json();
    fsdbValVec_t values;
    if (!npi_fsdb_sig_hdl_vec_value_at(handles, t, values, npiFsdbBinStrVal) || values.size() != handles.size()) {
        error = "Failed to read expression operands";
        return Json();
    }
    std::map<std::string, std::string> value_map;
    Json operands = Json::array();
    for (size_t i = 0; i < aliases.size(); ++i) {
        std::string v = with_value_prefix(values[i], 'b');
        value_map[aliases[i]] = v;
        operands.push_back({{"alias", aliases[i]}, {"signal", paths[i]}, {"value", wave_value_json(v, 'b')}});
    }
    ExprTri result = ExprTri::Unknown;
    if (!xdebug_waveform::eval_event_expression(expr, value_map, result, error)) return Json();
    Json data;
    data["summary"] = {
        {"expr", expr},
        {"time", format_time(t)},
        {"status", xdebug_waveform::expr_tri_text(result)},
        {"known", result != ExprTri::Unknown}
    };
    data["expr"] = expr;
    data["time"] = format_time(t);
    data["status"] = xdebug_waveform::expr_tri_text(result);
    data["known"] = result != ExprTri::Unknown;
    data["expr_value"] = result == ExprTri::True ? Json(true) : result == ExprTri::False ? Json(false) : Json(nullptr);
    data["operands"] = operands;
    return data;
}

Json ai_window_verify(const Json& args, std::string& error) {
    std::string clock = args.value("clock", std::string());
    if (clock.empty() || !args.contains("conditions") || !args["conditions"].is_array()) {
        error = "window.verify requires args.clock and args.conditions[]";
        return Json();
    }
    npiFsdbTime begin = 0, end = 0;
    if (!json_time_range(args, begin, end, error)) return Json();
    bool posedge = args.value("sampling", std::string("posedge")) != "negedge";
    int max_samples = args.value("max_samples", 1000000);

    Json signal_union = Json::object();
    for (const auto& cond : args["conditions"]) {
        if (!cond.contains("expr") || !cond.contains("signals")) {
            error = "each condition requires expr and signals";
            return Json();
        }
        for (auto it = cond["signals"].begin(); it != cond["signals"].end(); ++it) {
            if (signal_union.contains(it.key()) && signal_union[it.key()] != it.value()) {
                error = "duplicate alias maps to different signals: " + it.key();
                return Json();
            }
            signal_union[it.key()] = it.value();
        }
    }
    std::vector<std::string> aliases, paths;
    fsdbSigVec_t handles;
    if (!build_signal_alias_handles(signal_union, aliases, paths, handles, error)) return Json();

    struct CondState { std::string expr; std::string mode; int pass = 0; int fail = 0; int unknown = 0; };
    std::vector<CondState> states;
    for (const auto& cond : args["conditions"]) {
        CondState st;
        st.expr = server_compact_expr_ws(cond.value("expr", std::string()));
        st.mode = cond.value("mode", std::string("always"));
        states.push_back(st);
    }

    int samples = 0;
    bool truncated = false;
    bool ok = sample_on_clock(clock, posedge, aliases, handles, begin, end, max_samples,
        [&](npiFsdbTime, const std::map<std::string, std::string>& values) -> bool {
            bool has_eventually = false;
            bool all_eventually_seen = true;
            for (auto& st : states) {
                ExprTri r = ExprTri::Unknown;
                std::string eval_error;
                if (!xdebug_waveform::eval_event_expression(st.expr, values, r, eval_error)) {
                    error = eval_error;
                    return false;
                }
                bool pass = false;
                if (st.mode == "eventually") pass = (r == ExprTri::True);
                else if (st.mode == "never") pass = (r == ExprTri::False);
                else pass = (r == ExprTri::True);
                if (r == ExprTri::Unknown) st.unknown++;
                else if (pass) st.pass++;
                else st.fail++;
                if (st.mode == "eventually") {
                    has_eventually = true;
                    if (st.pass == 0) all_eventually_seen = false;
                } else if (r == ExprTri::Unknown || !pass) {
                    return false;
                }
            }
            return !(has_eventually && all_eventually_seen);
        }, error, samples, truncated);
    if (!ok) return Json();

    Json conds = Json::array();
    bool all_passed = true;
    int failed_samples = 0, unknown_samples = 0;
    for (const auto& st : states) {
        bool passed = false;
        if (st.mode == "eventually") passed = st.pass > 0;
        else passed = st.fail == 0 && st.unknown == 0;
        if (!passed) all_passed = false;
        failed_samples += st.fail;
        unknown_samples += st.unknown;
        conds.push_back({{"expr", st.expr}, {"mode", st.mode}, {"passed", passed},
                         {"pass_samples", st.pass}, {"failed_samples", st.fail}, {"unknown_samples", st.unknown}});
    }
    Json data;
    data["summary"] = {
        {"all_passed", all_passed},
        {"sample_count", samples},
        {"failed_samples", failed_samples},
        {"unknown_samples", unknown_samples},
        {"truncated", truncated}
    };
    data["all_passed"] = all_passed;
    data["sample_count"] = samples;
    data["failed_samples"] = failed_samples;
    data["unknown_samples"] = unknown_samples;
    data["truncated"] = truncated;
    data["conditions"] = conds;
    return data;
}

Json ai_signal_trend(const Json& args, std::string& error) {
    std::string signal = args.value("signal", std::string());
    std::string clock = args.value("clock", std::string());
    if (signal.empty() || clock.empty()) {
        error = "signal.trend requires args.signal and args.clock";
        return Json();
    }
    npiFsdbTime begin = 0, end = 0;
    if (!json_time_range(args, begin, end, error)) return Json();
    Json signals = {{"sig", signal}};
    std::vector<std::string> aliases, paths;
    fsdbSigVec_t handles;
    if (!build_signal_alias_handles(signals, aliases, paths, handles, error)) return Json();
    bool posedge = args.value("sampling", std::string("posedge")) != "negedge";
    int max_samples = args.value("max_samples", 1000000);
    bool have = false, stable = true, inc = true, dec = true;
    unsigned long long first = 0, last = 0, minv = 0, maxv = 0, prev = 0;
    int unknown = 0, samples = 0;
    bool truncated = false;
    if (!sample_on_clock(clock, posedge, aliases, handles, begin, end, max_samples,
        [&](npiFsdbTime, const std::map<std::string, std::string>& values) -> bool {
            auto it = values.find("sig");
            if (it == values.end() || contains_xz_value(it->second)) {
                unknown++;
                return true;
            }
            std::string bits = xdebug_waveform::expr_bits_only(it->second);
            unsigned long long v = 0;
            for (char c : bits) v = (v << 1) | (c == '1' ? 1ULL : 0ULL);
            if (!have) {
                first = last = minv = maxv = prev = v;
                have = true;
            } else {
                if (v != prev) stable = false;
                if (v < prev) inc = false;
                if (v > prev) dec = false;
                if (v < minv) minv = v;
                if (v > maxv) maxv = v;
                prev = v;
                last = v;
            }
            return true;
        }, error, samples, truncated)) return Json();
    Json data;
    data["signal"] = signal;
    data["sample_count"] = samples;
    data["unknown_count"] = unknown;
    data["stable"] = stable;
    data["truncated"] = truncated;
    if (have) {
        data["initial_value"] = first;
        data["final_value"] = last;
        data["min_value"] = minv;
        data["max_value"] = maxv;
        data["monotonic"] = stable ? "stable" : inc ? "increasing" : dec ? "decreasing" : "none";
    }
    return data;
}

Json ai_signal_statistics(const Json& args, std::string& error) {
    std::string signal = args.value("signal", std::string());
    std::string clock = args.value("clock", std::string());
    if (signal.empty()) {
        error = "signal.statistics requires args.signal";
        return Json();
    }
    npiFsdbTime begin = 0, end = 0;
    if (!json_time_range(args, begin, end, error)) return Json();

    if (clock.empty()) {
        npiFsdbValType fmt = json_value_format(args);
        fsdbTimeValPairVec_t changes;
        bool truncated = false;
        if (!read_signal_changes(signal, begin, end, fmt, changes, error, -1, &truncated)) return Json();
        Json data;
        data["signal"] = signal;
        data["sampling_mode"] = "raw_value_changes";
        data["begin"] = format_time(begin);
        data["end"] = format_time(end);
        data["sample_count"] = changes.size();
        data["returned_change_rows"] = changes.size();
        data["includes_initial_value"] = !changes.empty();
        data["transition_count"] = changes.empty() ? 0 : changes.size() - 1;
        data["truncated"] = truncated;
        int high_bursts = 0;
        npiFsdbTime first_high = 0, last_high = 0, last_fall = 0;
        bool prev_high = false;
        for (const auto& item : changes) {
            bool high = !contains_xz_value(item.second) && xdebug_waveform::expr_bits_only(item.second).find('1') != std::string::npos;
            if (high) {
                if (!prev_high) high_bursts++;
                if (first_high == 0) first_high = item.first;
                last_high = item.first;
            } else if (prev_high) {
                last_fall = item.first;
            }
            prev_high = high;
        }
        data["activity"] = {
            {"high_burst_count", high_bursts},
            {"first_high_time", first_high ? Json(format_time(first_high)) : Json(nullptr)},
            {"last_high_time", last_high ? Json(format_time(last_high)) : Json(nullptr)},
            {"last_fall_time", last_fall ? Json(format_time(last_fall)) : Json(nullptr)},
            {"max_high_cycles", nullptr}
        };
        if (!changes.empty()) {
            data["initial_value"] = wave_value_json(changes.front().second, json_value_prefix(fmt));
            data["final_value"] = wave_value_json(changes.back().second, json_value_prefix(fmt));
            data["first_change_time"] = format_time(changes.front().first);
            data["last_change_time"] = format_time(changes.back().first);
        }
        return data;
    }

    Json signals = {{"sig", signal}};
    std::vector<std::string> aliases, paths;
    fsdbSigVec_t handles;
    if (!build_signal_alias_handles(signals, aliases, paths, handles, error)) return Json();

    bool posedge = args.value("sampling", std::string("posedge")) != "negedge";
    int max_samples = args.value("max_samples", 1000000);
    int samples = 0, known = 0, unknown = 0;
    int high_cycles = 0, low_cycles = 0;
    int high_bursts = 0, current_high = 0, max_high_cycles = 0;
    int transitions = 0;
    bool truncated = false;
    bool have_known = false;
    std::string first_bits, final_bits, min_bits, max_bits, prev_bits;
    npiFsdbTime first_change_time = 0, last_change_time = 0;
    npiFsdbTime first_high_time = 0, last_high_time = 0, last_fall_time = 0;
    bool prev_high = false;

    if (!sample_on_clock(clock, posedge, aliases, handles, begin, end, max_samples,
        [&](npiFsdbTime t, const std::map<std::string, std::string>& values) -> bool {
            auto it = values.find("sig");
            if (it == values.end() || contains_xz_value(it->second)) {
                unknown++;
                if (prev_high) {
                    if (current_high > max_high_cycles) max_high_cycles = current_high;
                    current_high = 0;
                    last_fall_time = t;
                    prev_high = false;
                }
                return true;
            }
            std::string bits = bit_string_from_value(it->second);
            if (bits.empty()) {
                unknown++;
                return true;
            }
            known++;
            bool nonzero = bits.find('1') != std::string::npos;
            bool high = (nonzero && bits.size() == 1);
            if (!nonzero) low_cycles++;
            else if (high) high_cycles++;
            if (high) {
                if (!prev_high) {
                    high_bursts++;
                    current_high = 0;
                    if (first_high_time == 0) first_high_time = t;
                }
                current_high++;
                last_high_time = t;
            } else if (prev_high) {
                if (current_high > max_high_cycles) max_high_cycles = current_high;
                current_high = 0;
                last_fall_time = t;
            }
            prev_high = high;
            if (!have_known) {
                first_bits = final_bits = min_bits = max_bits = prev_bits = bits;
                have_known = true;
            } else {
                if (compare_bit_strings(bits, prev_bits) != 0) {
                    transitions++;
                    if (first_change_time == 0) first_change_time = t;
                    last_change_time = t;
                }
                if (compare_bit_strings(bits, min_bits) < 0) min_bits = bits;
                if (compare_bit_strings(bits, max_bits) > 0) max_bits = bits;
                prev_bits = final_bits = bits;
            }
            return true;
        }, error, samples, truncated)) return Json();
    if (prev_high && current_high > max_high_cycles) max_high_cycles = current_high;

    Json data;
    data["signal"] = signal;
    data["clock"] = clock;
    data["sampling"] = posedge ? "posedge" : "negedge";
    data["sampling_mode"] = "clock";
    data["begin"] = format_time(begin);
    data["end"] = format_time(end);
    data["sample_count"] = samples;
    data["known_count"] = known;
    data["unknown_count"] = unknown;
    data["transition_count"] = transitions;
    data["truncated"] = truncated;
    if (have_known) {
        data["first"] = bit_value_json(first_bits);
        data["final"] = bit_value_json(final_bits);
        data["min"] = bit_value_json(min_bits);
        data["max"] = bit_value_json(max_bits);
        data["low_cycles"] = low_cycles;
        data["high_cycles"] = high_cycles;
        data["high_ratio"] = known > 0 ? static_cast<double>(high_cycles) / static_cast<double>(known) : 0.0;
        if (first_change_time != 0) data["first_change_time"] = format_time(first_change_time);
        if (last_change_time != 0) data["last_change_time"] = format_time(last_change_time);
        data["activity"] = {
            {"high_burst_count", high_bursts},
            {"first_high_time", first_high_time ? Json(format_time(first_high_time)) : Json(nullptr)},
            {"last_high_time", last_high_time ? Json(format_time(last_high_time)) : Json(nullptr)},
            {"last_fall_time", last_fall_time ? Json(format_time(last_fall_time)) : Json(nullptr)},
            {"max_high_cycles", max_high_cycles}
        };
    }
    return data;
}

Json ai_counter_statistics(const Json& args, std::string& error) {
    std::string clock = args.value("clock", std::string());
    if (clock.empty()) {
        error = "MISSING_FIELD: counter.statistics requires args.clock";
        return Json();
    }
    if (!args.contains("time_range") && !args.contains("begin") && !args.contains("end") &&
        !args.contains("from") && !args.contains("to") && !args.contains("around")) {
        error = "MISSING_FIELD: counter.statistics requires args.time_range";
        return Json();
    }

    npiFsdbTime begin = 0, end = 0;
    if (!json_time_range(args, begin, end, error)) return Json();

    Json signal_union = Json::object();
    std::string valid_expr;
    CounterInput counter;
    if (!build_counter_inputs(args, signal_union, valid_expr, counter, error)) return Json();

    std::vector<std::string> aliases, paths;
    fsdbSigVec_t handles;
    if (!build_signal_alias_handles(signal_union, aliases, paths, handles, error)) return Json();

    bool posedge = args.value("sampling", std::string("posedge")) != "negedge";
    int max_samples = args.value("max_samples", 1000000);
    int samples = 0;
    bool truncated = false;
    int valid_count = 0, valid_false_count = 0, unknown_count = 0;
    bool have_value = false;
    uint64_t min_value = 0, max_value = 0;
    int min_count = 0, max_count = 0;
    npiFsdbTime min_first_time = 0, max_first_time = 0;
    long double sum = 0.0;

    if (!sample_on_clock(clock, posedge, aliases, handles, begin, end, max_samples,
        [&](npiFsdbTime t, const std::map<std::string, std::string>& values) -> bool {
            ExprTri valid = ExprTri::Unknown;
            std::string eval_error;
            if (!xdebug_waveform::eval_event_expression(valid_expr, values, valid, eval_error)) {
                error = eval_error;
                return false;
            }
            if (valid == ExprTri::False) {
                valid_false_count++;
                return true;
            }
            if (valid == ExprTri::Unknown) {
                unknown_count++;
                return true;
            }

            std::string bits = counter_bits_from_values(counter, values);
            uint64_t value = 0;
            std::string parse_error;
            if (!bits_to_u64(bits, value, parse_error)) {
                if (!parse_error.empty()) {
                    error = parse_error;
                    return false;
                }
                unknown_count++;
                return true;
            }

            valid_count++;
            sum += static_cast<long double>(value);
            if (!have_value) {
                have_value = true;
                min_value = max_value = value;
                min_count = max_count = 1;
                min_first_time = max_first_time = t;
                return true;
            }
            if (value < min_value) {
                min_value = value;
                min_count = 1;
                min_first_time = t;
            } else if (value == min_value) {
                min_count++;
            }
            if (value > max_value) {
                max_value = value;
                max_count = 1;
                max_first_time = t;
            } else if (value == max_value) {
                max_count++;
            }
            return true;
        }, error, samples, truncated)) return Json();

    Json data;
    data["clock"] = clock;
    data["sampling"] = posedge ? "posedge" : "negedge";
    data["begin"] = format_time(begin);
    data["end"] = format_time(end);
    data["sample_count"] = samples;
    data["valid_count"] = valid_count;
    data["valid_false_count"] = valid_false_count;
    data["unknown_count"] = unknown_count;
    data["truncated"] = truncated;
    data["cnt"] = args["cnt"];
    data["vld"] = args["vld"];
    if (have_value) {
        data["min_value"] = u64_to_decimal(min_value);
        data["max_value"] = u64_to_decimal(max_value);
        data["average_value"] = long_double_to_decimal(sum / static_cast<long double>(valid_count));
        data["min_count"] = min_count;
        data["max_count"] = max_count;
        data["min_first_time"] = format_time(min_first_time);
        data["max_first_time"] = format_time(max_first_time);
    }
    return data;
}


}  // namespace xdebug_waveform
