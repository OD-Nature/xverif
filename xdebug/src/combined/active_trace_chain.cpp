#include "combined/active_trace_chain.h"
#include "combined/active_trace_common.h"
#include "api/response.h"
#include "core/ai/common_blocks.h"
#include "core/npi/time_contract.h"
#include "runtime/work_dir.h"

#include <set>

namespace xdebug {

namespace {

// ═══════════════════════════════════════════════════════════════════
// data types
// ═══════════════════════════════════════════════════════════════════

struct Candidate {
    std::string name;
    std::string value_before, value_at;
    bool toggled = false;
};

struct BranchEvidence {
    std::string signal, time, reason;
    std::vector<Candidate> candidates;
};

struct ChainNode {
    int index = 0;
    std::string signal, time, active_time;
    std::string value_str;
    bool value_known = false;
    std::string driver_kind, driver, file;
    int line = 0;
    std::string hop;
    std::string next;
};

struct ChainStats {
    int calls = 0;
    int edgecheck_direct = 0;
    int fallback = 0;
    int temporal_boundaries = 0;
};

struct ChainResult {
    std::vector<ChainNode> chain;
    std::vector<BranchEvidence> branch_evidence;
    std::vector<std::string> limitations;
    std::string termination = "unresolved";
    std::string evidence_source;
    int static_candidate_count = 0;
    int active_check_count = 0;
    ChainStats stats;
    bool truncated = false;
};

struct Decision {
    bool stop = false;
    std::string reason;
    std::string next_signal;
    BranchEvidence evidence;
};

// ═══════════════════════════════════════════════════════════════════
// decide_next
// ═══════════════════════════════════════════════════════════════════

Decision decide_next(npiFsdbFileHandle fsdb,
                      const std::string& signal,
                      const std::string& time,
                      const std::string& clk_period,
                      const std::vector<std::string>& data_signals,
                      const std::string& driver_kind,
                      bool current_is_primary_input,
                      ChainStats& stats) {
    Decision d;

    if (driver_kind == "force") { d.stop = true; d.reason = "force"; return d; }
    if (data_signals.empty()) {
        d.stop = true;
        if (driver_kind.empty() || driver_kind == "unresolved" ||
            driver_kind == "other" || driver_kind == "port_boundary" ||
            driver_kind == "modport_port" || driver_kind == "ref_obj") {
            d.reason = current_is_primary_input ? "primary_input" : "unresolved";
        } else {
            d.reason = "primary_input";
        }
        return d;
    }

    if (data_signals.size() == 1) {
        d.next_signal = data_signals[0];
        stats.edgecheck_direct++;
        return d;
    }

    stats.fallback++;
    npiFsdbTime center = 0;
    npiFsdbTime period = 0;
    std::string time_error;
    xdebug_core::TimeParseOptions options;
    options.default_unit = "ns";
    if (!xdebug_core::parse_time(fsdb, time, options, center, time_error) ||
        !xdebug_core::parse_time(fsdb, clk_period, options, period, time_error)) {
        d.stop = true;
        d.reason = "unresolved";
        return d;
    }

    npiFsdbTime half = period / 2;
    npiFsdbTime before = center > half ? center - half : 0;
    npiFsdbTime after = center + half;

    BranchEvidence ev;
    ev.signal = signal; ev.time = time;
    int toggled_count = 0;
    std::string last_toggled;

    for (auto& name : data_signals) {
        Candidate c;
        c.name = name;
        c.value_before = fsdb_value_at(fsdb, name, before);
        c.value_at     = fsdb_value_at(fsdb, name, after);
        c.toggled = (c.value_before != c.value_at);
        if (c.toggled) { toggled_count++; last_toggled = name; }
        ev.candidates.push_back(c);
    }

    if (toggled_count == 1) { d.next_signal = last_toggled; return d; }

    d.stop = true;
    d.reason = "ambiguous";
    d.evidence = ev;
    d.evidence.reason = std::to_string(toggled_count) + " signals toggled simultaneously";
    return d;
}

// ═══════════════════════════════════════════════════════════════════
// build_chain
// ═══════════════════════════════════════════════════════════════════

ChainResult build_chain(npiFsdbFileHandle fsdb,
                         const std::string& signal,
                         const std::string& time,
                         const std::string& clk_period,
                         int max_depth, int max_nodes) {
    ChainResult result;
    auto vkey = [](const std::string& sig, const std::string& t) { return sig + "\x1f" + t; };
    std::set<std::string> visited;
    visited.insert(vkey(signal, time));

    std::string cur_sig = signal, cur_time = time;
    int depth = 0;

    trcOption_t opt = trcOptionDefault;
    opt.reportControl = true;

    while (depth <= max_depth && static_cast<int>(result.chain.size()) < max_nodes) {
        // ── trace ──
        NpiHandleGuard hdl(npi_handle_by_name(cur_sig.c_str(), nullptr));
        if (!hdl) {
            result.termination = "signal_not_found";
            result.limitations.push_back("signal not found: " + cur_sig);
            break;
        }
        PortConnectionInfo input_port = resolve_input_port_connection(cur_sig);

        result.stats.calls++;
        ActiveTraceResolveResult resolved = resolve_active_driver_precise(
            fsdb, hdl.get(), cur_sig, cur_time, opt);
        actTrcRes_t active = resolved.active;
        int rc = resolved.count;
        for (const auto& limitation : resolved.limitations) {
            result.limitations.push_back(limitation);
        }
        if (depth == 0) {
            result.evidence_source = resolved.evidence_source;
            result.static_candidate_count = resolved.static_candidate_count;
            result.active_check_count = resolved.active_check_count;
        }
        if (resolved.ambiguous) {
            result.termination = "ambiguous";
            break;
        }

        bool temporal = (active.activeTime != cur_time);
        if (temporal) result.stats.temporal_boundaries++;

        std::string active_time = active.activeTime.empty() ? cur_time : active.activeTime;
        npiFsdbTime active_tick = 0;
        std::string active_time_error;
        xdebug_core::TimeParseOptions active_time_options;
        active_time_options.default_unit = "ns";
        if (!xdebug_core::parse_time(fsdb, active_time, active_time_options, active_tick, active_time_error)) {
            result.termination = "unresolved";
            result.limitations.push_back("could not convert active time " + active_time);
            break;
        }

        if (rc == 0) {
            std::string raw_val = fsdb_value_at(fsdb, cur_sig, active_tick);
            ChainNode node;
            node.index = static_cast<int>(result.chain.size());
            node.signal = cur_sig;
            node.time = cur_time;
            node.active_time = active_time;
            node.value_str = format_value(raw_val);
            node.value_known = raw_val.find_first_of("xXzZ") == std::string::npos;
            node.driver_kind = "unresolved";
            node.driver = "(no driver)";

            if (input_port.is_input_like && !input_port.target_signal.empty()) {
                node.hop = temporal ? "⏱" : "→";
                node.next = input_port.target_signal;
                result.chain.push_back(node);
                if (visited.count(vkey(input_port.target_signal, active_time))) {
                    result.termination = "loop_detected";
                    result.limitations.push_back("loop: " + cur_sig + " -> " + input_port.target_signal);
                    break;
                }
                visited.insert(vkey(input_port.target_signal, active_time));
                cur_sig = input_port.target_signal;
                cur_time = active_time;
                depth++;
                continue;
            }

            node.hop = "■";
            result.termination = input_port.is_input_like ? "primary_input" : "unresolved";
            if (!input_port.is_input_like) {
                result.limitations.push_back("active trace returned no driver evidence for " + cur_sig);
            }
            result.chain.push_back(node);
            break;
        }

        // ── classify ──
        std::string best_kind, best_driver, best_file;
        int best_line = 0;
        std::vector<std::string> all_signals;
        std::vector<std::string> best_data_signals;

        for (auto& stmt : active.drvLoadStmtVec) {
            int type = stmt.useHdl ? npi_get(npiType, stmt.useHdl) : 0;
            std::string kind = statement_kind(type);
            if (best_kind.empty() || kind == "assignment" || kind == "force") {
                best_kind = kind;
                best_driver = driver_text(stmt.useHdl, kind);
                best_file = npi_string(npiFile, stmt.useHdl);
                best_line = stmt.useHdl ? npi_get(npiLineNo, stmt.useHdl) : 0;
                best_data_signals.clear();
                for (auto& sh : stmt.sigHdlVec) {
                    std::string n = npi_string(npiFullName, sh);
                    if (!n.empty()) best_data_signals.push_back(n);
                }
            }
            for (auto& sh : stmt.sigHdlVec) {
                std::string n = npi_string(npiFullName, sh);
                if (!n.empty()) all_signals.push_back(n);
            }
        }
        std::sort(all_signals.begin(), all_signals.end());
        all_signals.erase(std::unique(all_signals.begin(), all_signals.end()), all_signals.end());
        std::sort(best_data_signals.begin(), best_data_signals.end());
        best_data_signals.erase(std::unique(best_data_signals.begin(), best_data_signals.end()),
                                best_data_signals.end());

        std::vector<std::string> data_signals;
        const bool best_is_assignment =
            best_kind == "assignment" || best_kind == "force";
        const std::vector<std::string>& source_signals =
            best_is_assignment && !best_data_signals.empty()
                ? best_data_signals : all_signals;
        for (auto& s : source_signals)
            if (s != cur_sig) data_signals.push_back(s);
        if (input_port.is_input_like && !input_port.target_signal.empty()) {
            data_signals.clear();
            data_signals.push_back(input_port.target_signal);
        }

        std::string raw_val = fsdb_value_at(fsdb, cur_sig, active_tick);
        std::string val_disp = format_value(raw_val);
        bool known = raw_val.find_first_of("xXzZ") == std::string::npos;

        // ── decide ──
        Decision d = decide_next(fsdb, cur_sig, cur_time, clk_period,
                                  data_signals, best_kind,
                                  input_port.is_input_like && input_port.target_signal.empty(),
                                  result.stats);

        // ── record node ──
        ChainNode node;
        node.index = static_cast<int>(result.chain.size());
        node.signal = cur_sig; node.time = cur_time;
        node.active_time = active_time;
        node.value_str = val_disp; node.value_known = known;
        node.driver_kind = best_kind.empty() ? "unresolved" : best_kind;
        node.driver = best_driver.empty() ? "(no driver)" : best_driver;
        node.file = best_file; node.line = best_line;

        if (d.stop) {
            result.termination = d.reason;
            node.hop = "■";
            if (!d.evidence.candidates.empty())
                result.branch_evidence.push_back(d.evidence);
            result.chain.push_back(node);
            break;
        }

        node.hop = temporal ? "⏱" : "→";
        node.next = d.next_signal;
        result.chain.push_back(node);

        if (visited.count(vkey(d.next_signal, active_time))) {
            result.termination = "loop_detected";
            result.limitations.push_back("loop: " + cur_sig + " -> " + d.next_signal);
            break;
        }
        visited.insert(vkey(d.next_signal, active_time));
        cur_sig = d.next_signal;
        cur_time = active_time;
        depth++;
    }

    if (result.termination == "unresolved"
        && (depth > max_depth || static_cast<int>(result.chain.size()) >= max_nodes)) {
        result.truncated = true;
        result.termination = "limit";
        result.limitations.push_back("trace limit reached");
    }
    return result;
}

// ═══════════════════════════════════════════════════════════════════
// JSON output
// ═══════════════════════════════════════════════════════════════════

Json chain_to_json(const ChainResult& r) {
    Json arr = Json::array();
    for (auto& n : r.chain) {
        Json j;
        j["index"] = n.index; j["signal"] = n.signal;
        j["time"] = n.time; j["active_time"] = n.active_time;
        j["value"] = n.value_str; j["value_known"] = n.value_known;
        j["driver_kind"] = n.driver_kind; j["driver"] = n.driver;
        j["file"] = n.file; j["line"] = n.line;
        j["hop"] = n.hop; j["next"] = n.next;
        arr.push_back(j);
    }
    Json be = Json::array();
    for (auto& b : r.branch_evidence) {
        Json bj; bj["signal"] = b.signal; bj["time"] = b.time; bj["reason"] = b.reason;
        Json cs = Json::array();
        for (auto& c : b.candidates) {
            Json cj; cj["name"] = c.name;
            cj["before"] = c.value_before; cj["after"] = c.value_at; cj["toggled"] = c.toggled;
            cs.push_back(cj);
        }
        bj["candidates"] = cs; be.push_back(bj);
    }
    Json st; st["calls"] = r.stats.calls;
    st["edgecheck_direct"] = r.stats.edgecheck_direct;
    st["fallback"] = r.stats.fallback;
    st["temporal_boundaries"] = r.stats.temporal_boundaries;

    Json data; data["chain"] = arr; data["branch_evidence"] = be;
    data["stats"] = st; data["limitations"] = r.limitations;
    data["evidence_source"] = r.evidence_source.empty() ? Json(nullptr) : Json(r.evidence_source);
    data["static_candidate_count"] = r.static_candidate_count;
    data["active_check_count"] = r.active_check_count;
    data["truncated"] = r.truncated;
    return data;
}

} // namespace

nlohmann::ordered_json build_active_driver_chain_payload(const Json& request,
                                                         const std::string& daidir,
                                                         const std::string& fsdb_path,
                                                         npiFsdbFileHandle fsdb) {
    (void)daidir;
    (void)fsdb_path;
    Json args = request.value("args", Json::object());
    std::string signal = args.value("signal", "");
    std::string req_time = args.value("time", "");
    std::string clk_period = args.value("clk_period", "10ns");

    if (signal.empty() || req_time.empty())
        return nlohmann::ordered_json{{"error", "MISSING_FIELD"},
            {"message", "requires args.signal and args.time"}};
    if (!fsdb)
        return nlohmann::ordered_json{{"error", "FSDB_NOT_OPEN"},
            {"message", "FSDB handle is null"}};

    Json limits_j = request.value("limits", args.value("limits", Json::object()));
    int max_depth = std::max(1, limits_j.value("max_depth", 20));
    int max_nodes = std::max(1, limits_j.value("max_nodes", 50));

    NpiHandleGuard sig_hdl(npi_handle_by_name(signal.c_str(), nullptr));
    if (!sig_hdl.get())
        return nlohmann::ordered_json{{"error", "SIGNAL_NOT_FOUND"},
            {"message", "signal not found: " + signal}};

    ChainResult result = build_chain(fsdb, signal, req_time, clk_period,
                                      max_depth, max_nodes);

    nlohmann::ordered_json resp;
    resp["summary"] = {
        {"signal", signal},
        {"start_time", req_time},
        {"chain_length", static_cast<int>(result.chain.size())},
        {"termination", result.termination},
        {"evidence_source", result.evidence_source.empty()
            ? nlohmann::ordered_json(nullptr) : nlohmann::ordered_json(result.evidence_source)},
        {"static_candidate_count", result.static_candidate_count},
        {"active_check_count", result.active_check_count}
    };
    resp["chain"] = chain_to_json(result);
    resp["truncated"] = result.truncated;
    append_common_blocks_to_payload(resp);
    return resp;
}

} // namespace xdebug
