#include "combined/active_trace_chain.h"
#include "combined/active_trace_common.h"
#include "api/response.h"
#include "api/text_response_builder.h"
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
                      ChainStats& stats) {
    Decision d;

    if (driver_kind == "force") { d.stop = true; d.reason = "force"; return d; }
    if (data_signals.empty())   { d.stop = true; d.reason = "primary_input"; return d; }

    if (data_signals.size() == 1) {
        d.next_signal = data_signals[0];
        stats.edgecheck_direct++;
        return d;
    }

    stats.fallback++;
    double tv; std::string unit;
    if (!parse_time(time, tv, unit)) { d.stop = true; d.reason = "unresolved"; return d; }
    double cpv; std::string cpu;
    if (!parse_time(clk_period, cpv, cpu)) { d.stop = true; d.reason = "unresolved"; return d; }

    double half = cpv / 2.0;
    std::string tb = std::to_string(tv - half) + unit;
    std::string ta = std::to_string(tv + half) + unit;

    BranchEvidence ev;
    ev.signal = signal; ev.time = time;
    int toggled_count = 0;
    std::string last_toggled;

    for (auto& name : data_signals) {
        Candidate c;
        c.name = name;
        c.value_before = fsdb_value_at(fsdb, name, tb);
        c.value_at     = fsdb_value_at(fsdb, name, ta);
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
    std::set<std::string> visited;
    visited.insert(signal);

    std::string cur_sig = signal, cur_time = time;
    int depth = 0;

    trcOption_t opt = trcOptionDefault;
    opt.reportControl = true;

    while (depth <= max_depth && static_cast<int>(result.chain.size()) < max_nodes) {
        // ── trace ──
        npiHandle hdl = npi_handle_by_name(cur_sig.c_str(), nullptr);
        if (!hdl) {
            result.termination = "signal_not_found";
            result.limitations.push_back("signal not found: " + cur_sig);
            break;
        }

        actTrcRes_t active = {};
        result.stats.calls++;
        npi_active_trace_driver_by_hdl(hdl, active, cur_time.c_str(), opt);
        npi_release_handle(hdl);

        bool temporal = (active.activeTime != cur_time);
        if (temporal) result.stats.temporal_boundaries++;

        std::string active_time = active.activeTime.empty() ? cur_time : active.activeTime;

        // ── classify ──
        std::string best_kind, best_driver, best_file;
        int best_line = 0;
        std::vector<std::string> all_signals;

        for (auto& stmt : active.drvLoadStmtVec) {
            int type = stmt.useHdl ? npi_get(npiType, stmt.useHdl) : 0;
            std::string kind = statement_kind(type);
            if (best_kind.empty() || kind == "assignment" || kind == "force") {
                best_kind = kind;
                best_driver = driver_text(stmt.useHdl, kind);
                best_file = npi_string(npiFile, stmt.useHdl);
                best_line = stmt.useHdl ? npi_get(npiLineNo, stmt.useHdl) : 0;
            }
            for (auto& sh : stmt.sigHdlVec) {
                std::string n = npi_string(npiFullName, sh);
                if (!n.empty()) all_signals.push_back(n);
            }
        }
        std::sort(all_signals.begin(), all_signals.end());
        all_signals.erase(std::unique(all_signals.begin(), all_signals.end()), all_signals.end());

        std::vector<std::string> data_signals;
        for (auto& s : all_signals)
            if (s != cur_sig) data_signals.push_back(s);

        std::string raw_val = fsdb_value_at(fsdb, cur_sig, active_time);
        std::string val_disp = format_value(raw_val);
        bool known = raw_val.find_first_of("xXzZ") == std::string::npos;

        // ── decide ──
        Decision d = decide_next(fsdb, cur_sig, cur_time, clk_period,
                                  data_signals, best_kind, result.stats);

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

        if (visited.count(d.next_signal)) {
            result.termination = "loop_detected";
            result.limitations.push_back("loop: " + cur_sig + " -> " + d.next_signal);
            break;
        }
        visited.insert(d.next_signal);
        cur_sig = d.next_signal;
        cur_time = active_time;
        depth++;
    }

    if (depth > max_depth) { result.truncated = true; result.termination = "limit"; }
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
    data["truncated"] = r.truncated;
    return data;
}

// ═══════════════════════════════════════════════════════════════════
// XOUT output
// ═══════════════════════════════════════════════════════════════════

std::string chain_to_xout(const std::string& signal, const std::string& time,
                           const ChainResult& r) {
    TextResponseBuilder xout("xdebug");
    xout.emit_header(signal + " @" + time + " -> " + r.termination
                     + "  " + std::to_string(r.chain.size()) + " hops");
    xout.emit_section("chain");
    for (auto& n : r.chain) {
        std::string fl = n.file;
        if (n.line > 0) fl += ":" + std::to_string(n.line);
        if (fl.size() > 45) fl = "..." + fl.substr(fl.size() - 42);
        xout.emit_row({std::to_string(n.index) + " " + n.hop,
                        n.signal, n.active_time, n.value_str, n.driver, fl});
    }
    xout.emit_section("stats");
    xout.emit_kv("calls", r.stats.calls);
    xout.emit_kv("edgecheck_direct", r.stats.edgecheck_direct);
    xout.emit_kv("fallback", r.stats.fallback);
    xout.emit_kv("temporal_boundaries", r.stats.temporal_boundaries);
    if (r.truncated) xout.emit_kv("truncated", "true");
    if (!r.branch_evidence.empty()) {
        xout.emit_section("branch_evidence");
        for (auto& be : r.branch_evidence) {
            xout.emit_kv("signal", be.signal); xout.emit_kv("time", be.time);
            xout.emit_kv("reason", be.reason);
            for (auto& c : be.candidates) {
                xout.emit_row({c.toggled ? " [x]" : " [ ]",
                                c.name, c.value_before, "->", c.value_at});
            }
        }
    }
    return xout.str();
}

} // namespace

// ═══════════════════════════════════════════════════════════════════
// public run()
// ═══════════════════════════════════════════════════════════════════

Json ActiveTraceChainService::run(const Json& request, const Json& target) const {
    const std::string action = "trace.active_driver_chain";
    Json args = request.value("args", Json::object());
    std::string daidir = target.value("daidir", "");
    std::string fsdb_path = target.value("fsdb", "");
    std::string signal = args.value("signal", "");
    std::string req_time = args.value("requested_time", "");
    std::string clk_period = args.value("clk_period", "10ns");

    // resource validation already done by dispatcher; only check business params
    if (signal.empty() || req_time.empty())
        return make_error(request, action, "MISSING_FIELD",
                          "requires args.signal and args.requested_time");

    Json limits_j = args.value("limits", Json::object());
    int max_depth = std::max(1, limits_j.value("max_depth", 20));
    int max_nodes = std::max(1, limits_j.value("max_nodes", 50));

    ScopedRuntimeWorkDir workdir("combined");
    if (!workdir.ok())
        return make_error(request, action, "WORKDIR_FAILED", "failed to enter workdir");

    std::vector<std::string> npi_args = {current_executable(), "-dbdir", daidir, "-ssf", fsdb_path};
    std::vector<char*> npi_argv;
    for (auto& s : npi_args) npi_argv.push_back(const_cast<char*>(s.c_str()));
    int npi_argc = static_cast<int>(npi_argv.size());
    char** npi_argv_ptr = npi_argv.data();

    ScopedStdoutSilence silence;
    NpiSessionGuard npi;
    if (!npi.init(npi_argc, npi_argv_ptr))
        return make_error(request, action, "NPI_INIT_FAILED", "npi_init failed");
    if (!npi.load_design(npi_argc, npi_argv_ptr))
        return make_error(request, action, "DESIGN_LOAD_FAILED", "npi_load_design failed");
    FsdbFileGuard fsdb(fsdb_path);
    if (!fsdb)
        return make_error(request, action, "FSDB_OPEN_FAILED", "npi_fsdb_open failed");
    NpiHandleGuard sig_hdl(npi_handle_by_name(signal.c_str(), nullptr));
    if (!sig_hdl.get())
        return make_error(request, action, "SIGNAL_NOT_FOUND", "signal not found: " + signal);

    ChainResult result = build_chain(fsdb.get(), signal, req_time, clk_period,
                                      max_depth, max_nodes);

    Json resp = make_response(request, action);
    resp["session"] = {{"mode", "combined"}, {"daidir", daidir}, {"fsdb", fsdb_path}};
    resp["summary"] = {
        {"signal", signal}, {"start_time", req_time},
        {"chain_length", static_cast<int>(result.chain.size())},
        {"termination", result.termination},
        {"temporal_boundaries", result.stats.temporal_boundaries}
    };
    resp["data"] = chain_to_json(result);
    resp["text"] = chain_to_xout(signal, req_time, result);
    resp["meta"]["truncated"] = result.truncated;
    return resp;
}

Json ActiveTraceChainService::run_engine(const Json& request,
                                          const std::string& daidir,
                                          const std::string& fsdb_path,
                                          npiFsdbFileHandle fsdb) const {
    const std::string action = "trace.active_driver_chain";
    Json args = request.value("args", Json::object());
    std::string signal = args.value("signal", "");
    std::string req_time = args.value("requested_time", "");
    std::string clk_period = args.value("clk_period", "10ns");

    if (signal.empty() || req_time.empty())
        return make_error(request, action, "MISSING_FIELD",
                          "requires args.signal and args.requested_time");

    Json limits_j = args.value("limits", Json::object());
    int max_depth = std::max(1, limits_j.value("max_depth", 20));
    int max_nodes = std::max(1, limits_j.value("max_nodes", 50));

    NpiHandleGuard sig_hdl(npi_handle_by_name(signal.c_str(), nullptr));
    if (!sig_hdl.get())
        return make_error(request, action, "SIGNAL_NOT_FOUND", "signal not found: " + signal);

    ChainResult result = build_chain(fsdb, signal, req_time, clk_period,
                                      max_depth, max_nodes);

    Json resp = make_response(request, action);
    resp["session"] = {{"mode", "combined"}, {"daidir", daidir}, {"fsdb", fsdb_path}};
    resp["summary"] = {
        {"signal", signal}, {"start_time", req_time},
        {"chain_length", static_cast<int>(result.chain.size())},
        {"termination", result.termination},
        {"temporal_boundaries", result.stats.temporal_boundaries}
    };
    resp["data"] = chain_to_json(result);
    resp["text"] = chain_to_xout(signal, req_time, result);
    resp["meta"]["truncated"] = result.truncated;
    return resp;
}

} // namespace xdebug
