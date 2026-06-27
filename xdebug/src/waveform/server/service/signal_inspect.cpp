#include "../server_internal.h"

namespace xdebug_waveform {

struct SampledEdgeRecord {
    npiFsdbTime time = 0;
    std::map<std::string, std::string> values;
};

Json sample_edge_json(const std::vector<SampledEdgeRecord>& edges, int idx) {
    if (idx < 0 || idx >= static_cast<int>(edges.size())) return Json(nullptr);
    return format_time(edges[idx].time);
}

int lower_sample_edge(const std::vector<SampledEdgeRecord>& edges, npiFsdbTime t) {
    auto it = std::lower_bound(edges.begin(), edges.end(), t,
        [](const SampledEdgeRecord& e, npiFsdbTime value) { return e.time < value; });
    return static_cast<int>(it - edges.begin());
}

int nearest_sample_edge(const std::vector<SampledEdgeRecord>& edges, npiFsdbTime t) {
    if (edges.empty()) return -1;
    int next = lower_sample_edge(edges, t);
    if (next <= 0) return 0;
    if (next >= static_cast<int>(edges.size())) return static_cast<int>(edges.size()) - 1;
    npiFsdbTime prev_dt = t >= edges[next - 1].time ? t - edges[next - 1].time : edges[next - 1].time - t;
    npiFsdbTime next_dt = edges[next].time >= t ? edges[next].time - t : t - edges[next].time;
    return prev_dt <= next_dt ? next - 1 : next;
}

Json sampled_valid_json(const std::vector<SampledEdgeRecord>& edges, int idx) {
    if (idx < 0 || idx >= static_cast<int>(edges.size())) return Json(nullptr);
    auto it = edges[idx].values.find("valid");
    if (it == edges[idx].values.end()) return Json(nullptr);
    return wave_value_json(it->second, 'b');
}

Json sampled_payloads_json(const std::vector<SampledEdgeRecord>& edges,
                                  int idx,
                                  const Json& payload_aliases) {
    Json out = Json::array();
    if (idx < 0 || idx >= static_cast<int>(edges.size())) return out;
    for (const auto& p : payload_aliases) {
        std::string alias = p.value("alias", std::string());
        std::string signal = p.value("signal", std::string());
        auto it = edges[idx].values.find(alias);
        if (it == edges[idx].values.end()) continue;
        out.push_back({{"alias", alias}, {"signal", signal}, {"value", wave_value_json(it->second, 'b')}});
    }
    return out;
}

Json ai_sampled_pulse_inspect(const Json& args, std::string& error) {
    std::string clock = args.value("clock", std::string());
    std::string valid = args.value("valid", std::string());
    if (clock.empty() || valid.empty()) {
        error = "sampled_pulse.inspect requires args.clock and args.valid";
        return Json();
    }
    npiFsdbTime begin = 0, end = 0;
    if (!json_time_range(args, begin, end, error)) return Json();

    Json signals = {{"valid", valid}};
    Json payload_aliases = Json::array();
    auto add_payload = [&](const std::string& path) {
        if (path.empty()) return;
        std::string alias = "payload" + std::to_string(payload_aliases.size());
        signals[alias] = path;
        payload_aliases.push_back({{"alias", alias}, {"signal", path}});
    };
    if (args.contains("payload") && args["payload"].is_string()) {
        add_payload(args["payload"].get<std::string>());
    }
    if (args.contains("payloads") && args["payloads"].is_array()) {
        for (const auto& p : args["payloads"]) {
            if (p.is_string()) add_payload(p.get<std::string>());
        }
    }

    std::vector<std::string> aliases, paths;
    fsdbSigVec_t handles;
    if (!build_signal_alias_handles(signals, aliases, paths, handles, error)) return Json();

    bool posedge = args.value("sampling", std::string("posedge")) != "negedge";
    int max_samples = args.value("max_samples", 1000000);
    int max_events = args.value("max_events", 100000);
    int max_findings = args.value("max_findings", args.value("limit", 100));
    npiFsdbValType fmt = json_value_format(args);
    char value_prefix = json_value_prefix(fmt);

    std::vector<SampledEdgeRecord> edges;
    int sample_count = 0;
    bool sample_truncated = false;
    int sampled_high = 0, sampled_low = 0, sampled_unknown = 0;
    npiFsdbTime first_high = 0, last_high = 0;
    if (!sample_on_clock(clock, posedge, aliases, handles, begin, end, max_samples,
        [&](npiFsdbTime t, const std::map<std::string, std::string>& values) -> bool {
            SampledEdgeRecord rec;
            rec.time = t;
            rec.values = values;
            edges.push_back(rec);
            auto it = values.find("valid");
            ExprTri v = it == values.end() ? ExprTri::Unknown : xdebug_waveform::expr_truth_value(it->second);
            if (v == ExprTri::True) {
                sampled_high++;
                if (first_high == 0) first_high = t;
                last_high = t;
            } else if (v == ExprTri::False) {
                sampled_low++;
            } else {
                sampled_unknown++;
            }
            return true;
        }, error, sample_count, sample_truncated)) return Json();

    fsdbTimeValPairVec_t valid_changes;
    bool valid_truncated = false;
    int read_limit = max_events >= 0 ? max_events + 1 : -1;
    if (!read_signal_changes(valid, begin, end, npiFsdbBinStrVal, valid_changes, error, read_limit, &valid_truncated)) return Json();

    std::string init_valid;
    if (!read_sig_value_at(g_fsdb_file, valid.c_str(), begin, 'B', init_valid)) {
        error = "Failed to read initial valid value: " + valid;
        return Json();
    }
    std::string current_valid = with_value_prefix(init_valid, 'b');
    npiFsdbTime segment_begin = begin;
    Json findings = Json::array();
    bool findings_truncated = false;
    auto push_finding = [&](const Json& item) {
        if (max_findings >= 0 && static_cast<int>(findings.size()) >= max_findings) {
            findings_truncated = true;
            return;
        }
        findings.push_back(item);
    };

    auto valid_sampled_high_between = [&](npiFsdbTime lo, npiFsdbTime hi) {
        int idx = lower_sample_edge(edges, lo);
        while (idx >= 0 && idx < static_cast<int>(edges.size()) && edges[idx].time < hi) {
            auto it = edges[idx].values.find("valid");
            if (it != edges[idx].values.end() && xdebug_waveform::expr_truth_value(it->second) == ExprTri::True) return true;
            ++idx;
        }
        return false;
    };
    auto emit_unsampled_pulse = [&](npiFsdbTime lo, npiFsdbTime hi, const std::string& raw_value) {
        if (hi <= lo) return;
        if (valid_sampled_high_between(lo, hi)) return;
        int next = lower_sample_edge(edges, lo);
        int prev = next - 1;
        int near = nearest_sample_edge(edges, lo);
        Json item;
        item["type"] = "unsampled_valid_pulse";
        item["severity"] = "warning";
        item["raw_begin"] = format_time(lo);
        item["raw_end"] = format_time(hi);
        item["previous_sample_edge"] = sample_edge_json(edges, prev);
        item["next_sample_edge"] = sample_edge_json(edges, next);
        item["nearest_sample_edge"] = sample_edge_json(edges, near);
        item["raw_valid"] = wave_value_json(raw_value, 'b');
        item["sampled_valid"] = sampled_valid_json(edges, near);
        item["sampled_payloads"] = sampled_payloads_json(edges, near, payload_aliases);
        item["reason"] = "valid was high between sample edges but not high at any sampled edge";
        push_finding(item);
    };

    for (const auto& ch : valid_changes) {
        npiFsdbTime change_time = ch.first;
        std::string next_valid = with_value_prefix(ch.second, 'b');
        if (xdebug_waveform::expr_truth_value(current_valid) == ExprTri::True) {
            emit_unsampled_pulse(segment_begin, change_time, current_valid);
        }
        current_valid = next_valid;
        segment_begin = change_time;
    }
    if (xdebug_waveform::expr_truth_value(current_valid) == ExprTri::True) {
        emit_unsampled_pulse(segment_begin, end, current_valid);
    }

    int payload_transition_count = 0;
    bool payload_truncated = false;
    for (const auto& p : payload_aliases) {
        std::string alias = p.value("alias", std::string());
        std::string signal = p.value("signal", std::string());
        fsdbTimeValPairVec_t changes;
        bool one_truncated = false;
        if (!read_signal_changes(signal, begin, end, fmt, changes, error, read_limit, &one_truncated)) return Json();
        payload_transition_count += static_cast<int>(changes.size());
        if (one_truncated) payload_truncated = true;
        for (const auto& ch : changes) {
            int near = nearest_sample_edge(edges, ch.first);
            ExprTri sampled_valid = ExprTri::Unknown;
            if (near >= 0) {
                auto it = edges[near].values.find("valid");
                if (it != edges[near].values.end()) sampled_valid = xdebug_waveform::expr_truth_value(it->second);
            }
            if (sampled_valid == ExprTri::True) continue;
            int next = lower_sample_edge(edges, ch.first);
            int prev = next - 1;
            Json item;
            item["type"] = "payload_changed_without_sampled_valid";
            item["severity"] = "warning";
            item["raw_time"] = format_time(ch.first);
            item["previous_sample_edge"] = sample_edge_json(edges, prev);
            item["next_sample_edge"] = sample_edge_json(edges, next);
            item["nearest_sample_edge"] = sample_edge_json(edges, near);
            item["payload"] = {{"alias", alias}, {"signal", signal}, {"value", wave_value_json(ch.second, value_prefix)}};
            item["sampled_valid"] = sampled_valid_json(edges, near);
            item["sampled_payloads"] = sampled_payloads_json(edges, near, payload_aliases);
            item["reason"] = sampled_valid == ExprTri::Unknown
                ? "payload changed but sampled valid was unknown"
                : "payload changed but valid was not sampled high by the DUT clock";
            push_finding(item);
        }
    }

    bool truncated = sample_truncated || valid_truncated || payload_truncated || findings_truncated;
    Json data;
    data["clock"] = clock;
    data["valid"] = valid;
    data["payloads"] = payload_aliases;
    data["sampling"] = posedge ? "posedge" : "negedge";
    data["begin"] = format_time(begin);
    data["end"] = format_time(end);
    data["sample_count"] = sample_count;
    data["sampled_high_cycles"] = sampled_high;
    data["sampled_low_cycles"] = sampled_low;
    data["sampled_unknown_cycles"] = sampled_unknown;
    data["raw_valid_transition_count"] = valid_changes.size();
    data["payload_transition_count"] = payload_transition_count;
    data["risk_count"] = findings.size() + (findings_truncated ? 1 : 0);
    data["first_sampled_high_time"] = first_high == 0 ? Json(nullptr) : Json(format_time(first_high));
    data["last_sampled_high_time"] = last_high == 0 ? Json(nullptr) : Json(format_time(last_high));
    data["first_risk"] = findings.empty() ? Json(nullptr) : findings.front();
    data["findings"] = findings;
    data["truncated"] = truncated;
    return data;
}

Json ai_handshake_inspect(const Json& args, std::string& error) {
    std::string clock = args.value("clock", std::string());
    std::string valid = args.value("valid", std::string());
    std::string ready = args.value("ready", std::string());
    if (clock.empty() || valid.empty() || ready.empty()) {
        error = "handshake.inspect requires args.clock, args.valid and args.ready";
        return Json();
    }
    npiFsdbTime begin = 0, end = 0;
    if (!json_time_range(args, begin, end, error)) return Json();
    Json signals = {{"valid", valid}, {"ready", ready}};
    if (args.contains("data") && args["data"].is_array()) {
        int idx = 0;
        for (const auto& d : args["data"]) if (d.is_string()) signals["data" + std::to_string(idx++)] = d.get<std::string>();
    }
    std::vector<std::string> aliases, paths;
    fsdbSigVec_t handles;
    if (!build_signal_alias_handles(signals, aliases, paths, handles, error)) return Json();
    bool posedge = args.value("sampling", std::string("posedge")) != "negedge";
    Json rules = args.value("rules", Json::object());
    int max_wait = rules.value("max_wait_cycles", 100);
    bool check_data = rules.value("check_data_stable_when_stalled", false);
    int samples = 0, transfers = 0, stall_cycles = 0, max_stall = 0, ready_only = 0, data_violations = 0;
    bool in_stall = false, truncated = false;
    npiFsdbTime stall_begin = 0;
    std::map<std::string, std::string> stall_data;
    Json findings = Json::array();
    if (!sample_on_clock(clock, posedge, aliases, handles, begin, end, args.value("max_samples", 1000000),
        [&](npiFsdbTime t, const std::map<std::string, std::string>& values) -> bool {
            ExprTri v = xdebug_waveform::expr_truth_value(values.at("valid"));
            ExprTri r = xdebug_waveform::expr_truth_value(values.at("ready"));
            bool transfer = v == ExprTri::True && r == ExprTri::True;
            bool stall = v == ExprTri::True && r == ExprTri::False;
            if (transfer) transfers++;
            if (r == ExprTri::True && v == ExprTri::False) ready_only++;
            if (stall) {
                stall_cycles++;
                if (!in_stall) {
                    in_stall = true;
                    stall_begin = t;
                    stall_data = values;
                } else if (check_data) {
                    for (const auto& kv : values) {
                        if (kv.first.find("data") == 0 && stall_data[kv.first] != kv.second) data_violations++;
                    }
                }
            } else if (in_stall) {
                int cycles = stall_cycles;
                if (cycles > max_stall) max_stall = cycles;
                if (cycles > max_wait) {
                    findings.push_back({{"type", "long_stall"}, {"severity", "warning"},
                                        {"begin", format_time(stall_begin)}, {"end", format_time(t)}, {"cycles", cycles}});
                }
                in_stall = false;
                stall_cycles = 0;
            }
            return true;
        }, error, samples, truncated)) return Json();
    if (in_stall && stall_cycles > max_stall) max_stall = stall_cycles;
    Json data;
    data["summary"] = {
        {"sample_count", samples},
        {"transfer_count", transfers},
        {"max_stall_cycles", max_stall},
        {"truncated", truncated}
    };
    data["sample_count"] = samples;
    data["transfer_count"] = transfers;
    data["max_stall_cycles"] = max_stall;
    data["ready_without_valid_cycles"] = ready_only;
    data["data_stability_violations"] = data_violations;
    data["truncated"] = truncated;
    data["findings"] = findings;
    return data;
}

Json ai_inspect_signal(const Json& args, std::string& error) {
    Json data = ai_signal_changes(args, error);
    if (!error.empty()) return Json();
    npiFsdbTime glitch_threshold = 0;
    std::string threshold = args.value("glitch_threshold", std::string("1ns"));
    parse_user_time(threshold.c_str(), false, glitch_threshold, error);
    if (!error.empty()) return Json();
    fsdbTimeValPairVec_t raw_changes;
    std::string signal = args.value("signal", std::string());
    npiFsdbTime begin = 0, end = 0;
    if (!json_time_range(args, begin, end, error)) return Json();
    bool raw_truncated = false;
    read_signal_changes(signal, begin, end, npiFsdbBinStrVal, raw_changes, error, -1, &raw_truncated);
    if (!error.empty()) return Json();
    Json arr = data["changes"];
    Json period;
    double total_period = 0.0;
    int period_count = 0;
    int glitch_count = 0;
    const size_t change_count = raw_changes.empty() ? 0 : raw_changes.size();
    for (size_t i = 1; i < change_count; ++i) {
        npiFsdbTime t0 = raw_changes[i - 1].first;
        npiFsdbTime t1 = raw_changes[i].first;
        npiFsdbTime width = t1 >= t0 ? t1 - t0 : 0;
        if (width > 0) {
            total_period += static_cast<double>(width);
            period_count++;
            if (width < glitch_threshold) glitch_count++;
        }
    }
    data["edge_count"] = arr.size();
    data["glitch"] = {{"count", glitch_count}, {"threshold", format_time(glitch_threshold)}};
    if (period_count > 0) {
        period["avg"] = format_duration(static_cast<npiFsdbTime>(std::llround(total_period / period_count)));
        period["samples"] = period_count;
        data["period"] = period;
    }
    return data;
}

Json ai_detect_anomaly(const Json& args, std::string& error) {
    if (!args.contains("signals") || !args["signals"].is_array()) {
        error = "detect_anomaly requires args.signals[]";
        return Json();
    }
    npiFsdbTime begin = 0, end = 0;
    if (!json_time_range(args, begin, end, error)) return Json();
    Json checks = args.value("checks", Json::array());
    npiFsdbTime glitch_width = 0, stuck_duration = 0;
    bool check_glitch = false, check_stuck = false, check_unknown = false;
    for (const auto& c : checks) {
        std::string type = c.value("type", std::string());
        if (type == "glitch") {
            check_glitch = true;
            std::string v = c.value("min_pulse_width", std::string("1ns"));
            if (!parse_user_time(v.c_str(), false, glitch_width, error)) return Json();
        } else if (type == "stuck") {
            check_stuck = true;
            std::string v = c.value("min_duration", std::string("1us"));
            if (!parse_user_time(v.c_str(), false, stuck_duration, error)) return Json();
        } else if (type == "unknown_xz") {
            check_unknown = true;
        }
    }
    if (checks.empty()) {
        check_unknown = true;
        check_stuck = true;
        parse_user_time("1us", false, stuck_duration, error);
        if (!error.empty()) return Json();
    }
    int max_findings = args.value("max_findings", 50);
    Json findings = Json::array();
    for (const auto& s : args["signals"]) {
        if (max_findings >= 0 && static_cast<int>(findings.size()) >= max_findings) break;
        if (!s.is_string()) continue;
        std::string signal = s.get<std::string>();
        fsdbTimeValPairVec_t changes;
        if (!read_signal_changes(signal, begin, end, npiFsdbBinStrVal, changes, error)) return Json();
        for (size_t i = 0; i < changes.size(); ++i) {
            if (max_findings >= 0 && static_cast<int>(findings.size()) >= max_findings) break;
            if (check_unknown && contains_xz_value(changes[i].second)) {
                findings.push_back({{"type", "unknown_xz"}, {"signal", signal}, {"severity", "warning"},
                                    {"time", format_time(changes[i].first)}, {"value", wave_value_json(changes[i].second, 'b')}});
            }
            if (check_glitch && i + 1 < changes.size()) {
                npiFsdbTime width = changes[i + 1].first >= changes[i].first ? changes[i + 1].first - changes[i].first : 0;
                if (width > 0 && width < glitch_width) {
                    findings.push_back({{"type", "glitch"}, {"signal", signal}, {"severity", "info"},
                                        {"time", format_time(changes[i].first)}, {"pulse_width", format_time(width)}});
                }
            }
            if (check_stuck && i + 1 < changes.size()) {
                npiFsdbTime width = changes[i + 1].first >= changes[i].first ? changes[i + 1].first - changes[i].first : 0;
                if (width >= stuck_duration) {
                    findings.push_back({{"type", "stuck"}, {"signal", signal}, {"severity", "warning"},
                                        {"begin", format_time(changes[i].first)}, {"end", format_time(changes[i + 1].first)},
                                        {"duration", format_time(width)}, {"value", wave_value_json(changes[i].second, 'b')}});
                }
            }
        }
    }
    Json data;
    data["summary"] = {
        {"finding_count", findings.size()},
        {"truncated", max_findings >= 0 && static_cast<int>(findings.size()) >= max_findings}
    };
    data["finding_count"] = findings.size();
    data["findings"] = findings;
    data["truncated"] = max_findings >= 0 && static_cast<int>(findings.size()) >= max_findings;
    return data;
}


}  // namespace xdebug_waveform
