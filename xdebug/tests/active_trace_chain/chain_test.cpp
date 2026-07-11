#include "chain_test.h"

#include "npi.h"
#include "npi_hdl.h"
#include "npi_fsdb.h"
#include "npi_L1.h"

#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <iostream>
#include <set>
#include <sstream>
#include <string>
#include <vector>

// ═══════════════════════════════════════════════════════════════════
// helpers
// ═══════════════════════════════════════════════════════════════════

static std::string npi_str(int prop, npiHandle h) {
    const char* s = h ? npi_get_str(prop, h) : nullptr;
    return s ? s : "";
}

static std::string hdl_text(npiHandle h) {
    const char* s = h ? npi_ut_get_hdl_info(h, true, false) : nullptr;
    return s ? s : "";
}

static std::string stmt_kind(int type) {
    switch (type) {
    case npiContAssign:   return "cont_assign";
    case npiAssignment:   return "proc_assign";
    case npiForce:        return "force";
    case npiPort:         return "port_boundary";
    case npiIf:           return "if";
    case npiIfElse:       return "if_else";
    case npiCase:         return "case";
    case npiCaseItem:     return "case_item";
    case npiEventControl: return "event_control";
    case npiRelease:      return "release";
    default:
        if (type == 697) return "modport_port";
        if (type == 608) return "ref_obj";
        return "type_" + std::to_string(type);
    }
}

static bool is_data_kind(const std::string& k) {
    return k == "cont_assign" || k == "proc_assign" || k == "force";
}

static bool is_control_kind(const std::string& k) {
    return k == "if" || k == "if_else" || k == "case" || k == "case_item";
}

// parse "10ns" / "5.00n" → (value, unit)
static bool parse_time(const std::string& s, double& val, std::string& unit) {
    char* end = nullptr;
    val = std::strtod(s.c_str(), &end);
    if (!end || end == s.c_str()) return false;
    while (*end && std::isspace(static_cast<unsigned char>(*end))) ++end;
    unit = end;
    if (unit == "f") unit = "fs";
    else if (unit == "p") unit = "ps";
    else if (unit == "n") unit = "ns";
    else if (unit == "u") unit = "us";
    else if (unit == "m") unit = "ms";
    return !unit.empty();
}

// ═══════════════════════════════════════════════════════════════════
// FSDB value helpers
// ═══════════════════════════════════════════════════════════════════

static std::string fsdb_value_at(npiFsdbFileHandle fsdb,
                                  const std::string& sig_name,
                                  const std::string& time_str) {
    npiFsdbSigHandle sh = npi_fsdb_sig_by_name(fsdb, sig_name.c_str(), nullptr);
    if (!sh) return "";

    double tv; std::string unit;
    if (!parse_time(time_str, tv, unit)) return "";

    npiFsdbTime ft = 0;
    if (!npi_fsdb_convert_time_in(fsdb, tv, unit.c_str(), ft)) return "";

    std::string raw;
    int rc = npi_fsdb_sig_hdl_value_at(sh, ft, raw, npiFsdbBinStrVal);
    return rc ? raw : "";
}

static std::string make_time_str(double val, const std::string& unit,
                                  const std::string& fallback) {
    char buf[64];
    std::snprintf(buf, sizeof(buf), "%.2f%s", val, unit.c_str());
    return buf;
}

// ═══════════════════════════════════════════════════════════════════
// filter_toggled_candidates — ±0.5ns value comparison
// ═══════════════════════════════════════════════════════════════════

static std::vector<Candidate> filter_toggled(
    npiFsdbFileHandle fsdb,
    const std::vector<Candidate>& candidates,
    const std::string& time_str)
{
    std::vector<Candidate> out;
    double tv; std::string unit;
    if (!parse_time(time_str, tv, unit)) return out;

    std::string t_before = make_time_str(tv - 0.5, unit, time_str);
    std::string t_after  = make_time_str(tv + 0.5, unit, time_str);

    for (auto c : candidates) {
        c.value_before = fsdb_value_at(fsdb, c.name, t_before);
        c.value_at     = fsdb_value_at(fsdb, c.name, t_after);
        c.toggled      = (c.value_before != c.value_at);
        out.push_back(c);
    }
    return out;
}

// ═══════════════════════════════════════════════════════════════════
// statement → JSON helper
// ═══════════════════════════════════════════════════════════════════

static std::string stmt_to_json(const drvLoadStmt_s& stmt,
                                 const std::string& indent = "      ") {
    int type = stmt.useHdl ? npi_get(npiType, stmt.useHdl) : 0;
    std::ostringstream js;
    js << indent << "{\n"
       << indent << "  \"kind\": \"" << stmt_kind(type) << "\",\n"
       << indent << "  \"npi_type\": " << type << ",\n"
       << indent << "  \"file\": \"" << npi_str(npiFile, stmt.useHdl) << "\",\n"
       << indent << "  \"line\": " << (stmt.useHdl ? npi_get(npiLineNo, stmt.useHdl) : 0) << ",\n"
       << indent << "  \"text\": \"" << hdl_text(stmt.useHdl) << "\",\n"
       << indent << "  \"isPassThrough\": " << (stmt.isPassThrough ? "true" : "false") << ",\n"
       << indent << "  \"signals\": [";
    for (size_t i = 0; i < stmt.sigHdlVec.size(); ++i) {
        if (i > 0) js << ", ";
        js << "\"" << npi_str(npiFullName, stmt.sigHdlVec[i]) << "\"";
    }
    js << "]\n" << indent << "}";
    return js.str();
}

// ═══════════════════════════════════════════════════════════════════
// PROBE mode — compare edgeCheck=true vs false
// ═══════════════════════════════════════════════════════════════════

static void run_probe(npiFsdbFileHandle fsdb,
                      const std::string& signal,
                      const std::string& time) {
    npiHandle hdl = npi_handle_by_name(signal.c_str(), nullptr);
    if (!hdl) {
        std::cout << "{\"error\":\"signal not found: " << signal << "\"}\n";
        return;
    }

    auto probe_one = [&](bool edge) -> ProbeResult::ModeResult {
        ProbeResult::ModeResult r;
        r.edge_check = edge;
        trcOption_t opt = trcOptionDefault;
        opt.edgeCheck = edge;
        opt.reportControl = true;
        actTrcRes_t active = {};
        r.statement_count = npi_active_trace_driver_by_hdl(
            hdl, active, time.c_str(), opt);
        for (auto& stmt : active.drvLoadStmtVec) {
            int t = stmt.useHdl ? npi_get(npiType, stmt.useHdl) : 0;
            std::string k = stmt_kind(t);
            r.kinds.push_back(k);
            if (is_data_kind(k)) {
                for (auto& sh : stmt.sigHdlVec) {
                    std::string n = npi_str(npiFullName, sh);
                    if (!n.empty() && n != signal)
                        r.data_signals.push_back(n);
                }
            } else if (is_control_kind(k)) {
                for (auto& sh : stmt.sigHdlVec) {
                    std::string n = npi_str(npiFullName, sh);
                    if (!n.empty())
                        r.control_signals.push_back(n);
                }
            }
        }
        return r;
    };

    ProbeResult pr;
    pr.signal = signal;
    pr.time = time;
    pr.with_edge_check    = probe_one(true);
    pr.without_edge_check = probe_one(false);

    // ±0.5ns check on all unique data signals
    std::set<std::string> seen;
    std::vector<Candidate> all_data;
    for (auto& s : pr.without_edge_check.data_signals) {
        if (seen.insert(s).second)
            all_data.push_back({s, "data", "", "", false});
    }
    pr.toggled_check = filter_toggled(fsdb, all_data, time);

    // ── output JSON ──
    std::cout << "{\n"
              << "  \"signal\": \"" << signal << "\",\n"
              << "  \"time\": \"" << time << "\",\n";

    auto print_mode = [](const char* label, const ProbeResult::ModeResult& m) {
        std::cout << "  \"" << label << "\": {\n"
                  << "    \"edgeCheck\": " << (m.edge_check ? "true" : "false") << ",\n"
                  << "    \"statement_count\": " << m.statement_count << ",\n"
                  << "    \"kinds\": [";
        for (size_t i = 0; i < m.kinds.size(); ++i) {
            if (i) std::cout << ", ";
            std::cout << "\"" << m.kinds[i] << "\"";
        }
        std::cout << "],\n"
                  << "    \"data_signals\": [";
        for (size_t i = 0; i < m.data_signals.size(); ++i) {
            if (i) std::cout << ", ";
            std::cout << "\"" << m.data_signals[i] << "\"";
        }
        std::cout << "],\n"
                  << "    \"control_signals\": [";
        for (size_t i = 0; i < m.control_signals.size(); ++i) {
            if (i) std::cout << ", ";
            std::cout << "\"" << m.control_signals[i] << "\"";
        }
        std::cout << "]\n  }";
    };

    print_mode("with_edge_check", pr.with_edge_check);
    std::cout << ",\n";
    print_mode("without_edge_check", pr.without_edge_check);
    std::cout << ",\n"
              << "  \"toggled_check\": [\n";
    for (size_t i = 0; i < pr.toggled_check.size(); ++i) {
        auto& c = pr.toggled_check[i];
        std::cout << "    {\"name\":\"" << c.name
                  << "\", \"before\":\"" << c.value_before
                  << "\", \"after\":\"" << c.value_at
                  << "\", \"toggled\":" << (c.toggled ? "true" : "false") << "}";
        if (i + 1 < pr.toggled_check.size()) std::cout << ",";
        std::cout << "\n";
    }
    std::cout << "  ]\n}\n";

    npi_release_handle(hdl);
}

// ═══════════════════════════════════════════════════════════════════
// CHAIN mode — repeated active trace
// ═══════════════════════════════════════════════════════════════════

static ChainResult build_chain(npiFsdbFileHandle fsdb,
                                const std::string& signal,
                                const std::string& time,
                                int max_depth, int max_nodes,
                                bool stop_on_temporal) {
    ChainResult result;

    struct Hop {
        std::string sig, t;
        int depth;
    };
    std::vector<Hop> queue;
    queue.push_back({signal, time, 0});
    std::set<std::string> visited;
    visited.insert(signal);

    while (!queue.empty()) {
        Hop cur = queue.front();
        queue.erase(queue.begin());

        // ── limits check ──
        if (cur.depth > max_depth) {
            result.truncated = true;
            result.termination = "limit";
            result.limitations.push_back("max_depth reached at " + cur.sig);
            break;
        }
        if (static_cast<int>(result.chain.size()) >= max_nodes) {
            result.truncated = true;
            result.termination = "limit";
            result.limitations.push_back("max_nodes reached at " + cur.sig);
            break;
        }

        // ── lookup signal ──
        npiHandle hdl = npi_handle_by_name(cur.sig.c_str(), nullptr);
        if (!hdl) {
            result.limitations.push_back("signal not found: " + cur.sig);
            result.termination = "signal_not_found";
            break;
        }

        // ── native active trace ──
        actTrcRes_t active = {};
        trcOption_t opt = trcOptionDefault;
        opt.reportControl = true;
        int active_count = npi_active_trace_driver_by_hdl(
            hdl, active, cur.t.c_str(), opt);
        result.active_trace_call_count++;
        npi_release_handle(hdl);

        bool temporal = (active.activeTime != cur.t);
        if (temporal) result.temporal_boundary_count++;

        // ── read value at active time ──
        std::string node_value = fsdb_value_at(fsdb, cur.sig, active.activeTime);

        // ── classify statements ──
        std::vector<Candidate> data_candidates;
        std::vector<Candidate> control_candidates;
        std::string best_kind, best_file, best_text;
        int best_line = 0;

        for (auto& stmt : active.drvLoadStmtVec) {
            int type = stmt.useHdl ? npi_get(npiType, stmt.useHdl) : 0;
            std::string kind = stmt_kind(type);

            if (is_data_kind(kind)) {
                if (best_kind.empty()) {
                    best_kind = kind;
                    best_file = npi_str(npiFile, stmt.useHdl);
                    best_line = stmt.useHdl ? npi_get(npiLineNo, stmt.useHdl) : 0;
                    best_text = hdl_text(stmt.useHdl);
                }
                for (auto& sh : stmt.sigHdlVec) {
                    std::string n = npi_str(npiFullName, sh);
                    if (!n.empty() && n != cur.sig)
                        data_candidates.push_back({n, "data", "", "", false});
                }
            } else if (is_control_kind(kind)) {
                if (best_kind.empty()) best_kind = kind;
                for (auto& sh : stmt.sigHdlVec) {
                    std::string n = npi_str(npiFullName, sh);
                    if (!n.empty())
                        control_candidates.push_back({n, "control", "", "", false});
                }
            } else if (kind == "force") {
                best_kind = "force";
                best_file = npi_str(npiFile, stmt.useHdl);
                best_line = stmt.useHdl ? npi_get(npiLineNo, stmt.useHdl) : 0;
                best_text = hdl_text(stmt.useHdl);
            }
        }

        // ── determine next signal ──
        std::string next_signal;
        if (best_kind == "force") {
            result.termination = "force";
        }

        if (data_candidates.size() == 1) {
            next_signal = data_candidates[0].name;
            result.edgecheck_direct_count++;
        } else if (data_candidates.size() > 1) {
            result.fallback_0_5ns_count++;
            // edgeCheck=true still returned multiple → ±0.5ns fallback
            auto toggled = filter_toggled(fsdb, data_candidates, cur.t);
            int toggled_count = 0;
            for (auto& c : toggled) if (c.toggled) toggled_count++;

            if (toggled_count == 1) {
                for (auto& c : toggled)
                    if (c.toggled) { next_signal = c.name; break; }
            } else if (toggled_count == 0) {
                // no data toggled → check control
                auto ctrl_toggled = filter_toggled(fsdb, control_candidates, cur.t);
                int ctrl_count = 0;
                for (auto& c : ctrl_toggled) if (c.toggled) ctrl_count++;
                if (ctrl_count == 1) {
                    for (auto& c : ctrl_toggled)
                        if (c.toggled) { next_signal = c.name; break; }
                } else {
                    result.termination = "control_only";
                    BranchEvidence be;
                    be.signal = cur.sig; be.time = cur.t;
                    be.candidates = toggled;
                    be.decision_reason = "no data toggled, control ambiguous";
                    result.branch_evidence.push_back(be);
                }
            } else {
                // multiple toggled → ambiguous
                result.termination = "ambiguous";
                BranchEvidence be;
                be.signal = cur.sig; be.time = cur.t;
                be.candidates = toggled;
                be.decision_reason = std::to_string(toggled_count) + " signals toggled simultaneously";
                result.branch_evidence.push_back(be);
            }
        }

        // ── build chain node ──
        ChainNode node;
        node.hop = static_cast<int>(result.chain.size());
        node.signal = cur.sig;
        node.requested_time = cur.t;
        node.active_time = active.activeTime;
        node.value = node_value;
        node.value_known = (node_value.find_first_of("xXzZ") == std::string::npos);
        node.driver_kind = best_kind;
        node.file = best_file;
        node.line = best_line;
        node.text = best_text;
        node.hop_type = temporal ? "temporal_boundary" : "same_time";
        node.next_signal = next_signal;
        node.next_time = next_signal.empty() ? "" : active.activeTime;
        result.chain.push_back(node);

        if (temporal && stop_on_temporal) {
            result.temporal_boundary_stops++;
            result.termination = "temporal_boundary";
        }

        // ── control_only upgrade: scan branch_evidence ──
        if (result.termination == "control_only") {
            for (auto& be : result.branch_evidence) {
                int toggled = 0;
                std::string last;
                for (auto& c : be.candidates) {
                    if (c.toggled) { toggled++; last = c.name; }
                }
                if (toggled == 1) {
                    result.control_boundary_kind = "single_candidate_toggled";
                    result.likely_source = last;
                } else if (toggled > 1)
                    result.control_boundary_kind = "multiple_candidates_toggled";
                else
                    result.control_boundary_kind = "no_causal_toggle";
            }
        }

        // ── termination check ──
        if (!result.termination.empty()) break;

        if (next_signal.empty()) {
            result.termination = active_count == 0 ? "unresolved" : "primary_input";
            break;
        }

        if (visited.count(next_signal)) {
            result.termination = "loop_detected";
            result.limitations.push_back("loop: " + cur.sig + " → " + next_signal);
            break;
        }
        visited.insert(next_signal);
        queue.push_back({next_signal, active.activeTime, cur.depth + 1});
    }

    if (result.termination.empty()) result.termination = "unresolved";
    result.total_hops = static_cast<int>(result.chain.size());
    return result;
}

// ═══════════════════════════════════════════════════════════════════
// JSON output
// ═══════════════════════════════════════════════════════════════════

static void print_chain_json(const ChainResult& r) {
    std::cout << "{\n"
              << "  \"chain\": [\n";
    for (size_t i = 0; i < r.chain.size(); ++i) {
        auto& n = r.chain[i];
        std::cout << "    {\n"
                  << "      \"hop\": " << n.hop << ",\n"
                  << "      \"signal\": \"" << n.signal << "\",\n"
                  << "      \"requested_time\": \"" << n.requested_time << "\",\n"
                  << "      \"active_time\": \"" << n.active_time << "\",\n"
                  << "      \"value\": \"" << n.value << "\",\n"
                  << "      \"value_known\": " << (n.value_known ? "true" : "false") << ",\n"
                  << "      \"driver_kind\": \"" << n.driver_kind << "\",\n"
                  << "      \"file\": \"" << n.file << "\",\n"
                  << "      \"line\": " << n.line << ",\n"
                  << "      \"text\": \"" << n.text << "\",\n"
                  << "      \"hop_type\": \"" << n.hop_type << "\",\n"
                  << "      \"next_signal\": \"" << n.next_signal << "\",\n"
                  << "      \"next_time\": \"" << n.next_time << "\"\n"
                  << "    }";
        if (i + 1 < r.chain.size()) std::cout << ",";
        std::cout << "\n";
    }
    std::cout << "  ],\n"
              << "  \"branch_evidence\": [\n";
    for (size_t i = 0; i < r.branch_evidence.size(); ++i) {
        auto& be = r.branch_evidence[i];
        std::cout << "    {\n"
                  << "      \"signal\": \"" << be.signal << "\",\n"
                  << "      \"time\": \"" << be.time << "\",\n"
                  << "      \"reason\": \"" << be.decision_reason << "\",\n"
                  << "      \"candidates\": [\n";
        for (size_t j = 0; j < be.candidates.size(); ++j) {
            auto& c = be.candidates[j];
            std::cout << "        {\"name\":\"" << c.name
                      << "\", \"role\":\"" << c.role
                      << "\", \"before\":\"" << c.value_before
                      << "\", \"after\":\"" << c.value_at
                      << "\", \"toggled\":" << (c.toggled ? "true" : "false") << "}";
            if (j + 1 < be.candidates.size()) std::cout << ",";
            std::cout << "\n";
        }
        std::cout << "      ]\n    }";
        if (i + 1 < r.branch_evidence.size()) std::cout << ",";
        std::cout << "\n";
    }
    std::cout << "  ],\n"
              << "  \"limitations\": [";
    for (size_t i = 0; i < r.limitations.size(); ++i) {
        if (i) std::cout << ", ";
        std::cout << "\"" << r.limitations[i] << "\"";
    }
    std::cout << "],\n"
              << "  \"termination\": \"" << r.termination << "\",\n"
              << "  \"control_boundary_kind\": \"" << r.control_boundary_kind << "\",\n"
              << "  \"likely_source\": \"" << r.likely_source << "\",\n"
              << "  \"active_trace_calls\": " << r.active_trace_call_count << ",\n"
              << "  \"edgecheck_direct_count\": " << r.edgecheck_direct_count << ",\n"
              << "  \"fallback_0_5ns_count\": " << r.fallback_0_5ns_count << ",\n"
              << "  \"temporal_boundary_stops\": " << r.temporal_boundary_stops << ",\n"
              << "  \"temporal_boundaries\": " << r.temporal_boundary_count << ",\n"
              << "  \"total_hops\": " << r.total_hops << ",\n"
              << "  \"truncated\": " << (r.truncated ? "true" : "false") << "\n"
              << "}\n";
}

// ═══════════════════════════════════════════════════════════════════
// usage
// ═══════════════════════════════════════════════════════════════════

static void usage(const char* prog) {
    std::cerr << "Usage:\n"
              << "  " << prog << " -dbdir <path> -ssf <fsdb> -signal <name> -time <t> [options]\n"
              << "  " << prog << " -dbdir <path> -ssf <fsdb> -signal <name> -time <t> --mode=probe\n"
              << "\nOptions:\n"
              << "  -max_depth N   max chain hops (default 20)\n"
              << "  -max_nodes N   max chain nodes (default 50)\n"
              << "  --mode=chain   build trace chain (default)\n"
              << "  --mode=probe   compare edgeCheck true vs false\n"
              << "  --stop-on-temporal  stop after the first temporal boundary\n";
}

// ═══════════════════════════════════════════════════════════════════
// main
// ═══════════════════════════════════════════════════════════════════

int main(int argc, char** argv) {
    std::string daidir, fsdb_path, signal, time;
    int max_depth = 20, max_nodes = 50;
    std::string mode = "chain";
    bool stop_on_temporal = false;

    for (int i = 1; i < argc; ++i) {
        std::string a = argv[i];
        if (a == "-dbdir" && i + 1 < argc) daidir = argv[++i];
        else if (a == "-ssf" && i + 1 < argc) fsdb_path = argv[++i];
        else if (a == "-signal" && i + 1 < argc) signal = argv[++i];
        else if (a == "-time" && i + 1 < argc) time = argv[++i];
        else if (a == "-max_depth" && i + 1 < argc) max_depth = std::atoi(argv[++i]);
        else if (a == "-max_nodes" && i + 1 < argc) max_nodes = std::atoi(argv[++i]);
        else if (a.rfind("--mode=", 0) == 0) mode = a.substr(7);
        else if (a == "--stop-on-temporal") stop_on_temporal = true;
        else if (a == "-h" || a == "--help") { usage(argv[0]); return 0; }
        else { std::cerr << "Unknown: " << a << "\n"; usage(argv[0]); return 1; }
    }

    if (daidir.empty() || fsdb_path.empty() || signal.empty() || time.empty()) {
        usage(argv[0]);
        return 1;
    }

    // ── init NPI ──
    std::vector<std::string> npi_args_str = {
        std::string(argv[0]), "-dbdir", daidir, "-ssf", fsdb_path
    };
    std::vector<char*> npi_argv;
    for (auto& s : npi_args_str) npi_argv.push_back(const_cast<char*>(s.c_str()));
    int npi_argc = static_cast<int>(npi_argv.size());

    char** npi_argv_ptr = npi_argv.data();
    if (!npi_init(npi_argc, npi_argv_ptr)) {
        std::cerr << "npi_init failed\n";
        return 2;
    }
    if (!npi_load_design(npi_argc, npi_argv_ptr)) {
        std::cerr << "npi_load_design failed\n";
        npi_end();
        return 2;
    }

    npiFsdbFileHandle fsdb = npi_fsdb_open(fsdb_path.c_str());
    if (!fsdb) {
        std::cerr << "npi_fsdb_open failed\n";
        npi_end();
        return 2;
    }

    // ── run ──
    if (mode == "probe") {
        run_probe(fsdb, signal, time);
    } else {
        ChainResult r = build_chain(fsdb, signal, time, max_depth, max_nodes,
                                    stop_on_temporal);
        print_chain_json(r);
    }

    npi_fsdb_close(fsdb);
    npi_end();
    return 0;
}
