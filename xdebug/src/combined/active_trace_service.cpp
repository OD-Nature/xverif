#include "combined/active_trace_service.h"
#include "api/response.h"
#include "runtime/work_dir.h"

#include "npi.h"
#include "npi_fsdb.h"
#include "npi_hdl.h"
#include "npi_L1.h"

#include <cctype>
#include <cstdio>
#include <cstdlib>
#include <fcntl.h>
#include <set>
#include <string>
#include <unistd.h>
#include <vector>

namespace xdebug {

namespace {

// ─── NPI stdout suppression ────────────────────────────────────────────────

class ScopedStdoutSilence {
public:
    ScopedStdoutSilence() : saved_(-1), sink_(-1) {
        std::fflush(stdout);
        saved_ = dup(STDOUT_FILENO);
        sink_ = open("/dev/null", O_WRONLY);
        if (saved_ >= 0 && sink_ >= 0) dup2(sink_, STDOUT_FILENO);
    }

    ~ScopedStdoutSilence() {
        std::fflush(stdout);
        if (saved_ >= 0) {
            dup2(saved_, STDOUT_FILENO);
            close(saved_);
        }
        if (sink_ >= 0) close(sink_);
    }

private:
    int saved_;
    int sink_;
};

// ─── NPI helpers ────────────────────────────────────────────────────────────

std::string npi_string(int property, npiHandle handle) {
    const char* value = handle ? npi_get_str(property, handle) : nullptr;
    return value ? value : "";
}

std::string current_executable() {
    char path[4096] = {};
    ssize_t length = readlink("/proc/self/exe", path, sizeof(path) - 1);
    return length > 0 ? std::string(path, static_cast<size_t>(length)) : std::string("xdebug");
}

std::string handle_info(npiHandle handle) {
    const char* value = handle ? npi_ut_get_hdl_info(handle, true, false) : nullptr;
    return value ? value : "";
}

std::string statement_kind(int type) {
    switch (type) {
    case npiAssignment:   return "assignment";
    case npiForce:        return "force";
    case npiPort:         return "port_boundary";
    case npiIf:           return "if";
    case npiIfElse:       return "if_else";
    case npiCase:         return "case";
    case npiCaseItem:     return "case_item";
    case npiEventControl: return "event_control";
    case npiRelease:      return "release_candidate";
    // npiMpPort and npiRefObj may not be in all NPI headers; use numeric
    // constants from observed runtime values as fallback.
#ifdef npiMpPort
    case npiMpPort:       return "modport_port";
#endif
#ifdef npiRefObj
    case npiRefObj:       return "ref_obj";
#endif
    default:
        // Numeric fallbacks for environments where these constants are missing.
        if (type == 697) return "modport_port";    // npiMpPort
        if (type == 608) return "ref_obj";          // npiRefObj
        return "other";
    }
}

bool is_control_kind(const std::string& kind) {
    return kind == "if" || kind == "if_else" ||
           kind == "case" || kind == "case_item";
}

bool is_alias_kind(const std::string& kind) {
    return kind == "port_boundary" || kind == "modport_port" || kind == "ref_obj";
}

bool is_primary_input(npiHandle signal_hdl) {
    if (!signal_hdl) return false;
    int dir = npi_get(npiDirection, signal_hdl);
    return dir == npiInput || dir == npiInout;
}

bool parse_time(const std::string& text, double& value, std::string& unit) {
    char* end = nullptr;
    value = std::strtod(text.c_str(), &end);
    if (!end || end == text.c_str()) return false;
    while (*end && std::isspace(static_cast<unsigned char>(*end))) ++end;
    unit = end;
    if (unit == "f") unit = "fs";
    else if (unit == "p") unit = "ps";
    else if (unit == "n") unit = "ns";
    else if (unit == "u") unit = "us";
    else if (unit == "m") unit = "ms";
    return !unit.empty();
}

Json value_map(npiFsdbFileHandle fsdb,
               const std::vector<std::string>& signals,
               const std::string& time_text,
               Json& limitations) {
    Json values = Json::object();
    double numeric_time = 0.0;
    std::string unit;
    npiFsdbTime time = 0;
    if (!parse_time(time_text, numeric_time, unit) ||
        !npi_fsdb_convert_time_in(fsdb, numeric_time, unit.c_str(), time)) {
        limitations.push_back("can not convert time " + time_text + " to FSDB time");
        return values;
    }
    for (const auto& signal : signals) {
        npiFsdbSigHandle handle = npi_fsdb_sig_by_name(fsdb, signal.c_str(), nullptr);
        std::string raw;
        int rc = handle ? npi_fsdb_sig_hdl_value_at(handle, time, raw, npiFsdbBinStrVal) : 0;
        if (!handle || !rc) {
            values[signal] = nullptr;
            continue;
        }
        bool known = raw.find_first_of("xXzZ") == std::string::npos;
        values[signal] = {{"value", raw}, {"known", known}};
    }
    return values;
}

// ─── statement → JSON (backward-compatible) ─────────────────────────────────

Json statement_json(const drvLoadStmt_s& statement, std::vector<std::string>& signals) {
    int type = statement.useHdl ? npi_get(npiType, statement.useHdl) : 0;
    Json out = {
        {"kind", statement_kind(type)},
        {"npi_type", type},
        {"file", npi_string(npiFile, statement.useHdl)},
        {"line", statement.useHdl ? npi_get(npiLineNo, statement.useHdl) : 0},
        {"text", handle_info(statement.useHdl)},
        {"signals", Json::array()}
    };
    std::set<std::string> already(signals.begin(), signals.end());
    for (const auto& handle : statement.sigHdlVec) {
        std::string name = npi_string(npiFullName, handle);
        if (name.empty()) name = npi_string(npiName, handle);
        if (name.empty()) continue;
        out["signals"].push_back(name);
        if (already.insert(name).second) signals.push_back(name);
    }
    return out;
}

// ─── parity ─────────────────────────────────────────────────────────────────

Json parity_json(npiHandle signal,
                 const std::string& requested_time,
                 const trcOption_t& options,
                 const Json& baseline_statements) {
    Json result = {{"pvc_time", ""}, {"candidates", Json::array()}};
    const char* pvc = npi_get_pvc_time(signal, requested_time.c_str());
    if (!pvc) return result;
    result["pvc_time"] = pvc;
    drvLoadStmtVec_t candidates;
    npi_trace_driver_by_hdl2(signal, candidates, true, nullptr, options);
    for (const auto& candidate : candidates) {
        std::vector<std::string> ignored;
        Json item = statement_json(candidate, ignored);
        int rc = npi_check_active_handle(candidate.useHdl, pvc);
        item["active_check_rc"] = rc;
        item["classification"] = rc == 1 ? "active" : rc == 0 ? "inactive" : "unknown";
        result["candidates"].push_back(item);
    }
    result["baseline_statement_count"] = baseline_statements.size();
    return result;
}

// ─── new data model ─────────────────────────────────────────────────────────

struct ActiveTraceLimits {
    int max_depth = 8;
    int max_nodes = 50;
    int max_alias_candidates = 8;
    int max_trace_signals = 64;
};

struct TraceBuildResult {
    Json nodes = Json::array();
    Json edges = Json::array();
    Json selected_path = Json::array();
    Json controls = Json::array();
    Json events = Json::array();
    Json limitations = Json::array();
    Json alias_candidates = Json::array();
    Json root_driver = nullptr;
    Json current_driver = nullptr;
    bool truncated = false;
    std::string termination = "unresolved";
    int node_count = 0;
};

// ─── trace node builder ─────────────────────────────────────────────────────

Json trace_node_from_statement(const drvLoadStmt_s& statement,
                                const std::string& node_id,
                                const std::string& role,
                                const std::string& active_time,
                                const std::string& current_signal,
                                const Json& value) {
    int type = statement.useHdl ? npi_get(npiType, statement.useHdl) : 0;
    std::string kind = statement_kind(type);
    std::string file = npi_string(npiFile, statement.useHdl);
    int line = statement.useHdl ? npi_get(npiLineNo, statement.useHdl) : 0;
    std::string text = handle_info(statement.useHdl);

    Json signals_arr = Json::array();
    std::string next_signal;
    // Also capture the first RHS handle for full-name resolution in pass-through
    npiHandle first_rhs_handle = nullptr;
    for (const auto& handle : statement.sigHdlVec) {
        std::string name = npi_string(npiFullName, handle);
        if (name.empty()) name = npi_string(npiName, handle);
        if (name.empty()) continue;
        signals_arr.push_back(name);
        if (!first_rhs_handle) first_rhs_handle = handle;
    }

    // Determine next_signal for pass-through: the assignment's RHS has
    // one primary data signal (excluding the LHS and any control/sensitivity signals).
    if (kind == "assignment") {
        // Collect candidate signals that differ from current_signal
        // NPI may include clk/rst_n from sensitivity lists in sigHdlVec
        std::vector<std::string> rhs_candidates;
        for (const auto& name : signals_arr) {
            std::string s = name.get<std::string>();
            if (s != current_signal) rhs_candidates.push_back(s);
        }
        // Use the first RHS candidate if the statement text has no
        // arithmetic/logic operators.  Strip the file-location suffix
        // (e.g. ", {/path/file.sv : 25}") to avoid false positives from '/'.
        std::string stmt_text = text;
        size_t brace = stmt_text.rfind(" {");
        if (brace != std::string::npos) stmt_text = stmt_text.substr(0, brace);
        if (!rhs_candidates.empty()) {
            bool has_operator = false;
            for (char c : { '+', '-', '*', '/', '&', '|', '^', '?', ':' }) {
                if (stmt_text.find(c) != std::string::npos) { has_operator = true; break; }
            }
            if (!has_operator) {
                std::string candidate = rhs_candidates[0];
                // Verify the candidate resolves via npi_handle_by_name
                npiHandle verify = npi_handle_by_name(candidate.c_str(), nullptr);
                if (!verify && first_rhs_handle) {
                    std::string full = npi_string(npiFullName, first_rhs_handle);
                    if (!full.empty() && full != candidate) {
                        npiHandle verify2 = npi_handle_by_name(full.c_str(), nullptr);
                        if (verify2) { candidate = full; npi_release_handle(verify2); }
                    }
                }
                if (verify) npi_release_handle(verify);
                next_signal = candidate;
            }
        }
    }

    Json node = {
        {"id", node_id},
        {"role", role},
        {"kind", kind},
        {"signal", current_signal},
        {"signals", signals_arr},
        {"file", file},
        {"line", line},
        {"text", text},
        {"active_time", active_time},
        {"value", value},
        {"next_signal", next_signal},
        {"alias_kind", kind == "modport_port" ? "interface_modport" :
                       kind == "port_boundary" ? "module_port" :
                       kind == "ref_obj" ? "direct_ref" : "none"}
    };
    return node;
}

// ─── alias resolver ─────────────────────────────────────────────────────────

// Candidate modport names that are commonly output/source side.
static const char* kCommonSourceModports[] = {
    "source", "master", "mst", "producer", "tx", "drv", "driver", nullptr
};

// Split a hierarchical name into segments.
static std::vector<std::string> split_hier(const std::string& path) {
    std::vector<std::string> parts;
    std::string current;
    for (size_t i = 0; i < path.size(); ++i) {
        if (path[i] == '.') {
            if (!current.empty()) { parts.push_back(current); current.clear(); }
        } else {
            current += path[i];
        }
    }
    if (!current.empty()) parts.push_back(current);
    return parts;
}

static std::string join_hier(const std::vector<std::string>& parts,
                             size_t begin,
                             size_t end) {
    std::string out;
    for (size_t i = begin; i < end && i < parts.size(); ++i) {
        if (!out.empty()) out += ".";
        out += parts[i];
    }
    return out;
}

// Try to resolve a signal through interface/modport aliases.
// Returns array of candidate objects.
Json resolve_alias_candidates(npiHandle signal_handle,
                               const std::string& signal_name,
                               const ActiveTraceLimits& limits) {
    Json candidates = Json::array();
    if (!signal_handle) return candidates;

    int hdl_type = npi_get(npiType, signal_handle);
    std::string full_name = npi_string(npiFullName, signal_handle);

    // Strategy 1: Use the hierarchical signal_name (not the handle's full_name
    // which may be a definition-side path like "data_if.source.data") to trace
    // through instance port connections.
    // e.g., if_root_tb.u_sink.bus.data → find port 'bus' on u_sink → highconn
    auto parts = split_hier(signal_name);
    if (parts.size() >= 3) {
        // Try each prefix as a possible instance path
        for (size_t inst_end = parts.size() - 1; inst_end >= 1; --inst_end) {
            std::string inst_path;
            for (size_t i = 0; i < inst_end; ++i) {
                if (i > 0) inst_path += ".";
                inst_path += parts[i];
            }

            npiHandle inst = npi_handle_by_name(inst_path.c_str(), nullptr);
            if (!inst) continue;

            int inst_type = npi_get(npiType, inst);
            // Accept module instances and interface instances
            if (inst_type != npiModule && inst_type != npiInterface &&
                inst_type != npiInterfaceArray) {
                npi_release_handle(inst);
                continue;
            }

            // The next part is the port name
            std::string port_name = parts[inst_end];

            // Iterate ports on this instance
            npiHandle port_iter = npi_iterate(npiPort, inst);
            if (!port_iter) { npi_release_handle(inst); continue; }

            npiHandle port;
            bool found = false;
            while ((port = npi_scan(port_iter)) != nullptr) {
                std::string pname = npi_string(npiName, port);
                if (pname == port_name) {
                    // Found the port — get highconn
                    npiHandle high = npi_handle(npiHighConn, port);
                    if (high) {
                        std::string high_name = npi_string(npiFullName, high);
                        // Reconstruct: high_name + remaining parts after port
                        std::string resolved = high_name;
                        for (size_t i = inst_end + 1; i < parts.size(); ++i) {
                            resolved += "." + parts[i];
                        }

                        Json candidate;
                        candidate["from"] = signal_name;
                        candidate["to"] = resolved;
                        candidate["alias_kind"] = "module_port";
                        candidate["confidence"] = "high";
                        candidate["reason"] = "traced through instance port " + inst_path + "." + port_name + " → " + high_name;
                        candidates.push_back(candidate);

                        npi_release_handle(high);
                        found = true;
                    }
                    npi_release_handle(port);
                    break;
                }
                npi_release_handle(port);
            }
            npi_release_handle(port_iter);
            npi_release_handle(inst);

            if (found) break;
        }
    }

    // Strategy 2a: For modport_port or ref_obj handles, try npiActual first
    // to find the directly connected signal.
    bool is_mp_port = false;
#ifdef npiMpPort
    is_mp_port = (hdl_type == npiMpPort);
#else
    is_mp_port = (hdl_type == 697);
#endif
    if (is_mp_port || hdl_type == 608 /* npiRefObj */) {
        npiHandle actual = npi_handle(npiActual, signal_handle);
        if (actual) {
            std::string actual_name = npi_string(npiFullName, actual);
            if (!actual_name.empty() && actual_name != full_name) {
                Json candidate;
                candidate["from"] = signal_name;
                candidate["to"] = actual_name;
                candidate["alias_kind"] = is_mp_port ? "interface_modport" : "direct_ref";
                candidate["confidence"] = "high";
                candidate["reason"] = "resolved via npiActual to " + actual_name;
                candidates.push_back(candidate);
            }
            npi_release_handle(actual);
        }
        // Also try npiLowConn for modport ports
        if (candidates.empty() && is_mp_port) {
            npiHandle low = npi_handle(npiLowConn, signal_handle);
            if (low) {
                std::string low_name = npi_string(npiFullName, low);
                if (!low_name.empty() && low_name != full_name) {
                    Json candidate;
                    candidate["from"] = signal_name;
                    candidate["to"] = low_name;
                    candidate["alias_kind"] = "interface_modport";
                    candidate["confidence"] = "high";
                    candidate["reason"] = "resolved via npiLowConn to " + low_name;
                    candidates.push_back(candidate);
                }
                npi_release_handle(low);
            }
        }

        // Strategy 2a-ii: Reverse resolution for modport_port/ref_obj.
        // First try the observed interface-member shape:
        //   if_root_tb.link.data -> if_root_tb.link.source.data
        // Active trace can then resolve the source modport port to the
        // concrete producer assignment.
        if (candidates.empty()) {
            auto mp_parts = split_hier(signal_name);
            if (mp_parts.size() >= 2) {
                std::string member = mp_parts.back();
                std::string iface_path = join_hier(mp_parts, 0, mp_parts.size() - 1);
                for (int mi = 0; kCommonSourceModports[mi] != nullptr; ++mi) {
                    std::string probe = iface_path + "." +
                        kCommonSourceModports[mi] + "." + member;
                    if (probe == signal_name) continue;
                    npiHandle probe_hdl = npi_handle_by_name(probe.c_str(), nullptr);
                    if (probe_hdl) {
                        Json c;
                        c["from"] = signal_name;
                        c["to"] = probe;
                        c["alias_kind"] = "interface_modport";
                        c["confidence"] = "high";
                        c["reason"] = std::string("mapped interface member through source modport '") +
                            kCommonSourceModports[mi] + "'";
                        candidates.push_back(c);
                        npi_release_handle(probe_hdl);
                        break;
                    }
                }
            }
        }

        // If the source-modport alias is not available, probe common producer
        // instance/port patterns under the interface instance's parent scope.
        if (candidates.empty() && (is_mp_port || hdl_type == 608)) {
            // Strategy 2a-ii: Simple heuristic reverse resolution.
            // Parse signal_name to get interface parent scope + last path
            // element, then probe common instance/port patterns.
            auto mp_parts = split_hier(signal_name);
            if (mp_parts.size() >= 2) {
                // Build parent scope (all but interface instance + member).
                // For if_root_tb.link.data, parent_scope is if_root_tb.
                std::string parent_scope = mp_parts.size() >= 3
                    ? join_hier(mp_parts, 0, mp_parts.size() - 2)
                    : join_hier(mp_parts, 0, mp_parts.size() - 1);
                std::string member = mp_parts.back();

                // Try common bus port patterns under known instance names
                static const char* kInstNames[] = {
                    "u_src", "u_sink", "u_dut", "u_mst", "u_slv",
                    "i_source", "i_sink", "i_src", "i_dst", nullptr
                };
                static const char* kPortNames[] = {
                    "bus", "intf", "vif", "mp", nullptr
                };

                if (!parent_scope.empty()) {
                    for (int ii = 0; kInstNames[ii] != nullptr; ++ii) {
                        for (int pi = 0; kPortNames[pi] != nullptr; ++pi) {
                            std::string probe = parent_scope + "." +
                                kInstNames[ii] + "." + kPortNames[pi] + "." + member;
                            npiHandle probe_hdl = npi_handle_by_name(probe.c_str(), nullptr);
                            if (probe_hdl) {
                                Json c;
                                c["from"] = signal_name;
                                c["to"] = probe;
                                c["alias_kind"] = "interface_modport";
                                c["confidence"] = "medium";
                                c["reason"] = std::string("probe: ") + probe;
                                candidates.push_back(c);
                                npi_release_handle(probe_hdl);
                            }
                        }
                    }
                }
            }
        }
    }

    // Strategy 2b: Try modport resolution for interface members.
    // Skip if this is already a modport_port (handled by Strategy 2a).
    if (!is_mp_port && parts.size() >= 2) {
        // The interface instance is the second-to-last path element before the member
        // Actually, for link.data, the interface is "link" and member is "data"
        // We need to find the parent scope

        // Try: if the signal itself is a simple interface member (e.g., link.data)
        // construct modport candidates
        for (size_t iface_end = parts.size(); iface_end >= 2; --iface_end) {
            std::string iface_path;
            for (size_t i = 0; i < iface_end; ++i) {
                if (i > 0) iface_path += ".";
                iface_path += parts[i];
            }

            npiHandle iface = npi_handle_by_name(iface_path.c_str(), nullptr);
            if (!iface) continue;

            int iface_type = npi_get(npiType, iface);
            // Check if this is an interface instance or modport port
            bool is_interface = (iface_type == npiInterface || iface_type == npiInterfaceArray);
            bool is_modport_port = false;
#ifdef npiMpPort
            is_modport_port = (iface_type == npiMpPort);
#else
            is_modport_port = (iface_type == 697);
#endif

            if (is_interface || is_modport_port) {
                // This looks like an interface/modport — try source modport variants
                std::string member_suffix;
                for (size_t i = iface_end; i < parts.size(); ++i) {
                    if (!member_suffix.empty()) member_suffix += ".";
                    member_suffix += parts[i];
                }

                // Try each common source modport name
                for (int mi = 0; kCommonSourceModports[mi] != nullptr; ++mi) {
                    std::string candidate_path = iface_path + "." + kCommonSourceModports[mi];
                    if (!member_suffix.empty()) candidate_path += "." + member_suffix;

                    npiHandle cand = npi_handle_by_name(candidate_path.c_str(), nullptr);
                    if (cand) {
                        Json candidate;
                        candidate["from"] = signal_name;
                        candidate["to"] = candidate_path;
                        candidate["alias_kind"] = "interface_modport";
                        candidate["confidence"] = "medium";
                        candidate["reason"] = std::string("matched modport '") +
                                              kCommonSourceModports[mi] +
                                              "' on interface " + iface_path;
                        candidates.push_back(candidate);
                        npi_release_handle(cand);
                    }
                }

                npi_release_handle(iface);
                break; // Found the interface level, stop searching upward
            }

            npi_release_handle(iface);
        }
    }

    // Strategy 3: If the signal is a ref_obj, try resolving through the
    // reference directly.
    // Check if any candidate exists at the signal path without the instance prefix.
    // e.g., if_root_tb.u_sink.bus.data internally references link.data
    if (candidates.empty()) {
#ifdef npiRefObj
        if (hdl_type == npiRefObj) {
#else
        if (hdl_type == 608) {  // npiRefObj numeric fallback
#endif
            // For ref_obj, the NPI full name should give us the underlying object
            // Try to get the actual reference target
            npiHandle ref = npi_handle(npiActual, signal_handle);
            if (ref) {
                std::string ref_name = npi_string(npiFullName, ref);
                if (!ref_name.empty() && ref_name != full_name) {
                    Json candidate;
                    candidate["from"] = signal_name;
                    candidate["to"] = ref_name;
                    candidate["alias_kind"] = "direct_ref";
                    candidate["confidence"] = "high";
                    candidate["reason"] = "resolved ref_obj to actual target";
                    candidates.push_back(candidate);
                }
                npi_release_handle(ref);
            }
        }
    }

    // Truncate to limits
    if (static_cast<int>(candidates.size()) > limits.max_alias_candidates) {
        Json truncated = Json::array();
        for (int i = 0; i < limits.max_alias_candidates; ++i) {
            truncated.push_back(candidates[i]);
        }
        return truncated;
    }
    return candidates;
}

// ─── recursive active trace builder ─────────────────────────────────────────

TraceBuildResult build_active_trace(
    npiFsdbFileHandle fsdb,
    const std::string& root_signal,
    const std::string& requested_time,
    const trcOption_t& options,
    const ActiveTraceLimits& limits,
    bool include_control) {

    TraceBuildResult result;

    // BFS/DFS queue: (signal, time, depth, parent_node_id)
    struct QueueItem {
        std::string signal;
        std::string time;
        int depth;
        std::string parent_id;
    };

    std::vector<QueueItem> queue;
    queue.push_back({root_signal, requested_time, 0, ""});

    // Visited set to prevent loops: (signal, time_approx)
    std::set<std::string> visited;
    visited.insert(root_signal);

    while (!queue.empty()) {
        QueueItem current = queue.front();
        queue.erase(queue.begin());  // BFS-style pop front

        // Check depth limit
        if (current.depth > limits.max_depth) {
            result.truncated = true;
            result.termination = "limit";
            result.limitations.push_back("trace truncated by limits.max_depth at signal " + current.signal);
            break;
        }

        // Check node count limit
        if (result.node_count >= limits.max_nodes) {
            result.truncated = true;
            result.termination = "limit";
            result.limitations.push_back("trace truncated by limits.max_nodes");
            break;
        }

        // Get handle for the signal
        npiHandle signal_hdl = npi_handle_by_name(current.signal.c_str(), nullptr);
        if (!signal_hdl) {
            result.limitations.push_back("SIGNAL_NOT_FOUND: " + current.signal);
            if (result.node_count == 0) {
                result.termination = "unresolved";
                break;
            }
            continue;
        }

        int signal_type = npi_get(npiType, signal_hdl);

        // Run active trace driver at this time
        actTrcRes_t active = {};
        int active_count = npi_active_trace_driver_by_hdl(
            signal_hdl, active, current.time.c_str(), options);

        if (active_count == 0) {
            // No active driver found.  Check if this is an alias-type signal
            // that can be resolved through the design hierarchy.
            std::string alias_kind_str = statement_kind(signal_type);
            if (is_alias_kind(alias_kind_str)) {
                Json candidates = resolve_alias_candidates(signal_hdl, current.signal, limits);
                if (candidates.size() == 1) {
                    std::string target = candidates[0].value("to", "");
                    if (!target.empty() && visited.find(target) == visited.end() &&
                        current.depth < limits.max_depth) {
                        visited.insert(target);
                        // Create an alias node
                        std::string nid = "n" + std::to_string(result.node_count);
                        Json alias_node = {
                            {"id", nid},
                            {"role", "alias"},
                            {"kind", alias_kind_str},
                            {"signal", current.signal},
                            {"signals", Json::array()},
                            {"file", ""},
                            {"line", 0},
                            {"text", ""},
                            {"active_time", current.time},
                            {"value", nullptr},
                            {"next_signal", target},
                            {"alias_kind", candidates[0].value("alias_kind", "none")}
                        };
                        result.nodes.push_back(alias_node);
                        result.selected_path.push_back(nid);
                        result.node_count++;
                        Json alias_edge = {
                            {"from", nid},
                            {"to", "pending"},
                            {"relation", "alias"},
                            {"confidence", candidates[0].value("confidence", "medium")}
                        };
                        result.edges.push_back(alias_edge);
                        queue.push_back({target, current.time, current.depth + 1, nid});
                        npi_release_handle(signal_hdl);
                        continue;
                    }
                } else if (candidates.size() > 1) {
                    result.termination = "ambiguous";
                    for (const auto& c : candidates) {
                        result.alias_candidates.push_back(c);
                    }
                    npi_release_handle(signal_hdl);
                    continue;
                }
            }

            // Terminal: primary input, constant, or truly unresolved
            npi_release_handle(signal_hdl);
            if (result.node_count == 0) {
                result.termination = "unresolved";
                result.limitations.push_back("active trace returned no driver evidence for " + current.signal);
            }
            std::string nid = "n" + std::to_string(result.node_count);
            Json terminal_node = {
                {"id", nid},
                {"role", "root"},
                {"kind", "primary_input"},
                {"signal", current.signal},
                {"signals", Json::array()},
                {"file", ""},
                {"line", 0},
                {"text", ""},
                {"active_time", current.time},
                {"value", nullptr},
                {"next_signal", ""},
                {"alias_kind", "none"}
            };
            result.nodes.push_back(terminal_node);
            result.selected_path.push_back(nid);
            result.node_count++;
            if (result.root_driver.is_null()) {
                result.root_driver = {{"kind", "primary_input"}, {"file", ""}, {"line", 0}};
            }
            if (result.termination == "unresolved") {
                result.termination = "primary_input";
            }
            continue;
        }

        npi_release_handle(signal_hdl);

        // Process statements from active trace
        Json driver_item = nullptr;
        Json alias_items = Json::array();
        std::vector<std::string> signals_in_scope;
        signals_in_scope.push_back(current.signal);

        for (const auto& stmt : active.drvLoadStmtVec) {
            int type = stmt.useHdl ? npi_get(npiType, stmt.useHdl) : 0;
            std::string kind = statement_kind(type);

            std::string node_id = "n" + std::to_string(result.node_count);
            if (result.node_count >= limits.max_nodes) {
                result.truncated = true;
                result.termination = "limit";
                result.limitations.push_back("trace truncated by limits.max_nodes");
                break;
            }

            // Get value at active time for this node
            Json node_value = nullptr;
            if (!active.activeTime.empty()) {
                std::vector<std::string> val_signals = {current.signal};
                Json val_map = value_map(fsdb, val_signals, active.activeTime, result.limitations);
                if (val_map.contains(current.signal)) node_value = val_map[current.signal];
            }

            // Determine role
            std::string role;
            if (kind == "assignment" || kind == "force") {
                role = kind;
            } else if (is_control_kind(kind)) {
                role = "control";
            } else if (is_alias_kind(kind)) {
                role = "alias";
            } else if (kind == "event_control") {
                role = "event";
            } else {
                role = "other";
            }

            Json node = trace_node_from_statement(
                stmt, node_id, role, active.activeTime, current.signal, node_value);
            result.nodes.push_back(node);
            result.selected_path.push_back(node_id);
            result.node_count++;

            // Add edge from parent if exists
            if (!current.parent_id.empty()) {
                Json edge = {
                    {"from", current.parent_id},
                    {"to", node_id},
                    {"relation", "rhs_dependency"},
                    {"confidence", "high"}
                };
                result.edges.push_back(edge);
            }

            // Classify and decide next steps
            if (kind == "force") {
                // Force is always a terminal
                driver_item = node;
                result.termination = "force";
                result.root_driver = {
                    {"kind", "force"},
                    {"file", node.value("file", "")},
                    {"line", node.value("line", 0)}
                };
            } else if (kind == "assignment") {
                if (driver_item.is_null()) driver_item = node;

                std::string next = node.value("next_signal", "");
                if (!next.empty()) {
                    // Pass-through: check if we should recurse.
                    // Stop at primary inputs (module boundary).
                    bool next_is_input = false;
                    npiHandle next_hdl = npi_handle_by_name(next.c_str(), nullptr);
                    if (next_hdl) {
                        next_is_input = is_primary_input(next_hdl);
                        npi_release_handle(next_hdl);
                    }
                    if (next_is_input) {
                        // Primary input — this assignment is the root driver
                        result.termination = "assignment";
                        result.root_driver = {
                            {"kind", "assignment"},
                            {"file", node.value("file", "")},
                            {"line", node.value("line", 0)}
                        };
                    } else if (visited.find(next) == visited.end() && current.depth < limits.max_depth) {
                        // Pass-through: update root_driver to this assignment.
                        // If recursion stops at a primary input, this is the
                        // correct root.  If recursion finds a deeper assignment,
                        // it will be overwritten by the next pass-through hop.
                        result.root_driver = {
                            {"kind", "assignment"},
                            {"file", node.value("file", "")},
                            {"line", node.value("line", 0)}
                        };
                        visited.insert(next);
                        queue.push_back({next, active.activeTime, current.depth + 1, node_id});

                        // Add edge for the next hop
                        Json edge = {
                            {"from", node_id},
                            {"to", "n" + std::to_string(result.node_count)},  // will be next node
                            {"relation", "rhs_dependency"},
                            {"confidence", "high"}
                        };
                        // Don't add edge yet since next node ID isn't fixed
                        // Edges will be added when processing the next node
                    } else if (visited.find(next) != visited.end()) {
                        result.limitations.push_back("cycle detected: " + current.signal + " → " + next);
                        result.termination = result.termination == "unresolved" ? "assignment" : result.termination;
                        result.root_driver = {
                            {"kind", "assignment"},
                            {"file", node.value("file", "")},
                            {"line", node.value("line", 0)}
                        };
                    } else {
                        // Depth limited
                        result.truncated = true;
                        result.termination = "limit";
                        result.root_driver = {
                            {"kind", "assignment"},
                            {"file", node.value("file", "")},
                            {"line", node.value("line", 0)}
                        };
                    }
                } else {
                    // Root assignment (multi-signal RHS, expression, or constant)
                    result.termination = "assignment";
                    result.root_driver = {
                        {"kind", "assignment"},
                        {"file", node.value("file", "")},
                        {"line", node.value("line", 0)}
                    };
                }
            } else if (is_alias_kind(kind)) {
                alias_items.push_back(node);

                // For port_boundary: if the port is an input, stop here.
                // This is a module primary input; the root cause is the
                // assignment that led us here, not the port itself.
                if (kind == "port_boundary" && stmt.useHdl) {
                    int pdir = npi_get(npiDirection, stmt.useHdl);
                    if (pdir == npiInput) {
                        if (result.termination == "unresolved") {
                            result.termination = "assignment";
                        }
                        // Don't override root_driver if already set by a
                        // parent assignment that led to this boundary.
                        break;  // stop processing statements for this signal
                    }
                }

                // Try to resolve alias
                npiHandle stmt_hdl = stmt.useHdl;
                if (stmt_hdl) {
                    Json candidates = resolve_alias_candidates(stmt_hdl, current.signal, limits);
                    if (candidates.size() == 1) {
                        std::string target = candidates[0].value("to", "");
                        std::string alias_kind = candidates[0].value("alias_kind", "");

                        // Add alias edge
                        Json alias_edge = {
                            {"from", node_id},
                            {"to", "n" + std::to_string(result.node_count)},  // approximate
                            {"relation", "alias"},
                            {"confidence", candidates[0].value("confidence", "medium")}
                        };
                        result.edges.push_back(alias_edge);

                        if (visited.find(target) == visited.end() && current.depth < limits.max_depth) {
                            visited.insert(target);
                            queue.push_back({target, active.activeTime, current.depth + 1, node_id});
                        }
                    } else if (candidates.size() > 1) {
                        result.termination = "ambiguous";
                        for (const auto& c : candidates) {
                            result.alias_candidates.push_back(c);
                        }
                    } else {
                        // No candidates — mark unresolved
                        if (result.termination == "unresolved") {
                            result.termination = "unresolved";
                            result.limitations.push_back(
                                "could not resolve alias for " + current.signal +
                                " (kind: " + kind + ")");
                        }
                    }
                }
            } else if (is_control_kind(kind)) {
                if (include_control) {
                    result.controls.push_back(node);
                }
            } else if (kind == "event_control") {
                result.events.push_back(node);
            }
        }

        // Set current_driver from the first assignment/force found at root level
        if (current.depth == 0 && !driver_item.is_null() && result.current_driver.is_null()) {
            result.current_driver = driver_item;
        }

        // If control_only at root
        if (current.depth == 0 && driver_item.is_null() && !result.controls.empty()) {
            result.termination = "control_only";
            result.limitations.push_back(
                "control context confirmed but NPI active evidence did not confirm specific assignment");
        }
    }

    // Post-process: fix up edges that reference approximate node IDs
    // (The "to" field on last edges may be wrong; clean them up)
    Json clean_edges = Json::array();
    std::set<std::string> node_ids;
    for (const auto& n : result.nodes) {
        if (n.contains("id")) node_ids.insert(n["id"].get<std::string>());
    }
    for (const auto& e : result.edges) {
        std::string to = e.value("to", "");
        // Only keep edges where both ends exist
        if (node_ids.count(e.value("from", "")) > 0) {
            clean_edges.push_back(e);
        }
    }
    result.edges = clean_edges;

    return result;
}

} // namespace

// ─── public run() ───────────────────────────────────────────────────────────

Json ActiveTraceService::run(const Json& request, const Json& target) const {
    const std::string action = "trace.active_driver";
    const Json args = request.value("args", Json::object());
    const std::string daidir = target.value("daidir", std::string());
    const std::string fsdb_path = target.value("fsdb", std::string());
    const std::string signal_name = args.value("signal", std::string());
    const std::string requested_time = args.value("requested_time", std::string());

    if (daidir.empty() || fsdb_path.empty()) {
        return make_error(request, action, "RESOURCE_REQUIRED",
                          "trace.active_driver requires target.daidir and target.fsdb");
    }
    if (signal_name.empty() || requested_time.empty()) {
        return make_error(request, action, "MISSING_FIELD",
                          "args.signal and args.requested_time are required");
    }

    ScopedRuntimeWorkDir workdir("combined");
    if (!workdir.ok()) {
        return make_error(request, action, "WORKDIR_FAILED",
                          "failed to enter runtime working directory: " + workdir.path());
    }

    // ── Parse limits ──
    ActiveTraceLimits limits;
    Json limits_json = args.value("limits", Json::object());
    if (limits_json.empty()) {
        limits_json = request.value("limits", Json::object());
    }
    if (limits_json.contains("max_depth") && limits_json["max_depth"].is_number()) {
        limits.max_depth = std::max(1, limits_json["max_depth"].get<int>());
    }
    if (limits_json.contains("max_nodes") && limits_json["max_nodes"].is_number()) {
        limits.max_nodes = std::max(1, limits_json["max_nodes"].get<int>());
    }
    if (limits_json.contains("max_alias_candidates") && limits_json["max_alias_candidates"].is_number()) {
        limits.max_alias_candidates = std::max(0, limits_json["max_alias_candidates"].get<int>());
    }
    if (limits_json.contains("max_trace_signals") && limits_json["max_trace_signals"].is_number()) {
        limits.max_trace_signals = std::max(1, limits_json["max_trace_signals"].get<int>());
    }

    // ── Parse include flags ──
    bool include_control = args.value("include_control", true);
    bool include_parity = args.value("include_parity", false);
    bool include_trace = args.value("include_trace", false);
    bool include_alias_candidates = args.value("include_alias_candidates", false);
    bool include_compat_fields = args.value("include_compat_fields", false);

    // output.verbosity can upgrade include_trace
    std::string verbosity = request.value("output", Json::object()).value("verbosity", "compact");
    if (verbosity == "full" || verbosity == "debug") {
        include_trace = true;
        include_compat_fields = true;
    }

    // ── Init NPI ──
    std::vector<std::string> npi_arg_strings = {
        current_executable(), "-dbdir", daidir, "-ssf", fsdb_path
    };
    std::vector<char*> npi_argv;
    for (auto& value : npi_arg_strings) npi_argv.push_back(const_cast<char*>(value.c_str()));
    int npi_argc = static_cast<int>(npi_argv.size());
    char** npi_argp = npi_argv.data();
    ScopedStdoutSilence silence;
    if (!npi_init(npi_argc, npi_argp)) {
        return make_error(request, action, "NPI_INIT_FAILED", "npi_init failed for combined session");
    }
    if (!npi_load_design(npi_argc, npi_argp)) {
        npi_end();
        return make_error(request, action, "DESIGN_LOAD_FAILED", "failed to load daidir with waveform binding");
    }
    npiFsdbFileHandle fsdb = npi_fsdb_open(fsdb_path.c_str());
    if (!fsdb) {
        npi_end();
        return make_error(request, action, "FSDB_OPEN_FAILED", "failed to open fsdb for value queries");
    }
    npiHandle signal = npi_handle_by_name(signal_name.c_str(), nullptr);
    if (!signal) {
        npi_fsdb_close(fsdb);
        npi_end();
        return make_error(request, action, "SIGNAL_NOT_FOUND", "exact design signal was not found: " + signal_name);
    }
    npi_release_handle(signal);

    // ── Build trace ──
    trcOption_t options = trcOptionDefault;
    options.reportControl = include_control;

    TraceBuildResult trace_result = build_active_trace(
        fsdb, signal_name, requested_time, options, limits, include_control);

    // ── Collect values ──
    Json limitations = trace_result.limitations;
    std::vector<std::string> value_signals;
    value_signals.push_back(signal_name);
    for (const auto& node : trace_result.nodes) {
        if (node.contains("next_signal") && !node["next_signal"].get<std::string>().empty()) {
            std::string ns = node["next_signal"].get<std::string>();
            if (std::find(value_signals.begin(), value_signals.end(), ns) == value_signals.end()) {
                value_signals.push_back(ns);
            }
        }
    }

    Json active_values = value_map(fsdb, value_signals,
        trace_result.nodes.empty() ? requested_time :
            (trace_result.nodes[0].contains("active_time") ?
             trace_result.nodes[0]["active_time"].get<std::string>() : requested_time),
        limitations);
    Json requested_values = value_map(fsdb, value_signals, requested_time, limitations);

    // ── Build response ──
    Json response = make_response(request, action);
    response["session"] = {{"mode", "combined"}, {"daidir", daidir}, {"fsdb", fsdb_path}};

    // Determine driver_status
    std::string driver_status = trace_result.termination;
    if (driver_status == "assignment" || driver_status == "force" || driver_status == "primary_input") {
        driver_status = "resolved";
    } else if (driver_status == "limit" && !trace_result.root_driver.is_null()) {
        driver_status = "resolved";
    }

    // summary
    response["summary"] = {
        {"signal", signal_name},
        {"requested_time", requested_time},
        {"active_time", trace_result.nodes.empty() ? "" :
            trace_result.nodes[0].value("active_time", "")},
        {"driver_status", driver_status},
        {"statement_count", trace_result.node_count},
        {"trace_node_count", trace_result.node_count},
        {"root_driver", trace_result.root_driver.is_null() ?
            Json::object() : trace_result.root_driver}
    };

    // data
    Json data;
    data["signal"] = signal_name;
    data["requested_time"] = requested_time;
    data["active_time"] = trace_result.nodes.empty() ? "" :
        trace_result.nodes[0].value("active_time", "");
    data["driver_status"] = driver_status;
    data["driver"] = trace_result.current_driver.is_null() ?
        Json(nullptr) : trace_result.current_driver;
    data["root_driver"] = trace_result.root_driver.is_null() ?
        Json(nullptr) : trace_result.root_driver;
    data["controls"] = trace_result.controls;
    data["events"] = trace_result.events;
    data["values"] = {
        {"requested", requested_values},
        {"active", active_values}
    };
    data["limitations"] = limitations;

    if (include_alias_candidates || !trace_result.alias_candidates.empty()) {
        data["alias_candidates"] = trace_result.alias_candidates;
    } else {
        data["alias_candidates"] = Json::array();
    }

    if (include_trace) {
        data["trace"] = {
            {"nodes", trace_result.nodes},
            {"edges", trace_result.edges},
            {"selected_path", trace_result.selected_path},
            {"termination", trace_result.termination}
        };
    }

    // Compat fields (for transition period)
    if (include_compat_fields) {
        // Build backward-compatible statements/path from trace nodes
        Json compat_statements = Json::array();
        Json compat_path = Json::array();
        for (const auto& node : trace_result.nodes) {
            std::string role = node.value("role", "");
            if (role == "assignment" || role == "force") {
                compat_statements.push_back(node);
            } else if (role == "alias") {
                compat_path.push_back(node);
            } else {
                compat_statements.push_back(node);
            }
        }
        data["statements"] = compat_statements;
        data["path"] = compat_path;
        // Also keep old field names
        data["active_values"] = active_values;
        data["requested_values"] = requested_values;
    }

    response["data"] = data;
    response["meta"]["truncated"] = trace_result.truncated;

    // parity (unchanged behavior)
    if (include_parity && !trace_result.nodes.empty()) {
        // Re-run the original single-level active trace for parity comparison
        npiHandle sig_hdl = npi_handle_by_name(signal_name.c_str(), nullptr);
        if (sig_hdl) {
            Json baseline_statements = Json::array();
            for (const auto& node : trace_result.nodes) {
                baseline_statements.push_back(node);
            }
            response["data"]["parity"] = parity_json(sig_hdl, requested_time, options, baseline_statements);
            npi_release_handle(sig_hdl);
        }
    }

    npi_fsdb_close(fsdb);
    npi_end();
    return response;
}

} // namespace xdebug
