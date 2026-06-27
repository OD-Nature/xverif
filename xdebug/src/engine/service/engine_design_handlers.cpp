#include "engine_action_handler.h"
#include "engine_action_registry.h"
#include "engine_globals.h"
#include "design_postprocess.h"
#include "trace_bfs_engine.h"

#include "../../design/trace/trace_engine.h"
#include "../../design/signal/signal_finder.h"
#include "../../design/port/port_analyzer.h"
#include "../../design/service/action_support.h"

#include "npi.h"
#include "npi_fsdb.h"
#include "npi_L1.h"

#include <fstream>
#include <map>
#include <memory>
#include <set>

namespace xdebug_design {
namespace {

// ── helpers ──────────────────────────────────────────────────────────

static TraceOptions parse_trace_opts(const Json& args) {
    TraceOptions opts;
    opts.limit = args.value("limit", 0);
    opts.role = args.value("role", std::string());
    opts.no_statement_only = args.value("no_statement_only", false);
    if (args.contains("include_statement_only") && args["include_statement_only"].is_boolean())
        opts.no_statement_only = !args["include_statement_only"].get<bool>();
    return opts;
}

static nlohmann::json trace_one_signal(const std::string& signal,
                                        TraceMode mode,
                                        const TraceOptions& opts) {
    TraceEngine engine;
    TraceResult r = engine.trace(signal, mode, opts);
    return nlohmann::json::parse(engine.render_ai_json(r));
}

static TraceMode trace_mode_from_direction(const std::string& dir) {
    return dir == "load" ? TraceMode::Load : TraceMode::Driver;
}

static bool compact_mode(const Json& request) {
    return request.value("output", Json::object()).value("verbosity", "") == "compact";
}

static bool include_arg(const Json& request, const char* name) {
    return request.value("args", Json::object()).value(name, false);
}

static Json with_scalar_summary(Json out) {
    if (out.contains("summary") && out["summary"].is_object() && !out["summary"].empty())
        return out;
    Json summary = Json::object();
    for (auto it = out.begin(); it != out.end(); ++it) {
        if (it->is_string() || it->is_number() || it->is_boolean() || it->is_null())
            summary[it.key()] = it.value();
    }
    if (!summary.empty()) out["summary"] = summary;
    return out;
}

static Json trace_expand_summary(const std::string& root,
                                 const std::string& direction,
                                 const detail::BfsResult& bfs,
                                 const nlohmann::json& graph,
                                 const nlohmann::json& relation_edges,
                                 int aggregated_edge_count,
                                 bool compact) {
    if (compact) {
        return {{"root_signal", root}, {"direction", direction},
                {"node_count", graph["nodes"].size()}, {"edge_count", graph["edges"].size()},
                {"truncated", bfs.truncated}};
    }
    return {{"root_signal", root}, {"direction", direction},
            {"depth", bfs.reached_depth}, {"node_count", graph["nodes"].size()},
            {"edge_count", graph["edges"].size()}, {"raw_edge_count", bfs.raw_edge_count},
            {"deduped_edge_count", bfs.all_edges.size()},
            {"duplicate_edge_count", bfs.duplicate_edge_count},
            {"relation_group_count", relation_edges.size()},
            {"aggregated_edge_count", aggregated_edge_count},
            {"failed_query_count", bfs.failed_query_count},
            {"truncated", bfs.truncated}};
}

static void append_bfs_warnings(Json& out, const detail::BfsResult& bfs) {
    if (bfs.warnings.empty()) return;
    out["warnings"] = Json::array();
    for (const auto& warning : bfs.warnings) {
        try {
            out["warnings"].push_back(Json::parse(warning));
        } catch (...) {
            out["warnings"].push_back(warning);
        }
    }
}

class TraceDriverHandler : public EngineActionHandler {
public:
    const char* action_name() const override { return "trace.driver"; }
    bool needs_design() const override { return true; }
    bool needs_waveform() const override { return false; }

    Json run(const Json& request, EngineActionContext& ctx) const override {
        Json args = request.value("args", Json::object());
        std::string signal = args.value("signal", std::string());
        if (signal.empty()) return err("MISSING_FIELD", "args.signal is required");
        TraceEngine engine;
        TraceResult result = engine.trace(signal, TraceMode::Driver, parse_trace_opts(args));
        Json out = Json::parse(engine.render_ai_json(result));
        out["summary"] = {
            {"query", out.value("query", signal)},
            {"result_count", out.value("result_count", 0)},
            {"confidence", out.value("confidence", "unknown")},
            {"resolution", out.value("resolution", Json::object())}
        };
        return out;
    }

private:
    static Json err(const char* code, const std::string& msg) {
        Json e; e["error"] = code; e["message"] = msg; return e;
    }
};

class TraceLoadHandler : public EngineActionHandler {
public:
    const char* action_name() const override { return "trace.load"; }
    bool needs_design() const override { return true; }
    bool needs_waveform() const override { return false; }

    Json run(const Json& request, EngineActionContext& ctx) const override {
        Json args = request.value("args", Json::object());
        std::string signal = args.value("signal", std::string());
        if (signal.empty()) return err("MISSING_FIELD", "args.signal is required");
        TraceEngine engine;
        TraceResult result = engine.trace(signal, TraceMode::Load, parse_trace_opts(args));
        return Json::parse(engine.render_ai_json(result));
    }

private:
    static Json err(const char* code, const std::string& msg) {
        Json e; e["error"] = code; e["message"] = msg; return e;
    }
};

class SignalResolveHandler : public EngineActionHandler {
public:
    const char* action_name() const override { return "signal.resolve"; }
    bool needs_design() const override { return true; }
    bool needs_waveform() const override { return false; }

    Json run(const Json& request, EngineActionContext& ctx) const override {
        Json args = request.value("args", Json::object());
        std::string signal = args.value("signal", std::string());
        if (signal.empty()) return err("MISSING_FIELD", "args.signal is required");
        SignalFinder finder;
        SignalResolveResult result = finder.resolve(signal);
        return with_scalar_summary(Json::parse(finder.render_json(result)));
    }

private:
    static Json err(const char* code, const std::string& msg) {
        Json e; e["error"] = code; e["message"] = msg; return e;
    }
};

class PortTraceHandler : public EngineActionHandler {
public:
    const char* action_name() const override { return "port.trace"; }
    bool needs_design() const override { return true; }
    bool needs_waveform() const override { return false; }

    Json run(const Json& request, EngineActionContext& ctx) const override {
        Json args = request.value("args", Json::object());
        std::string path = args.value("path", std::string());
        if (path.empty()) return err("MISSING_FIELD", "args.path is required");
        Json limits = request.value("limits", Json::object());
        int limit = args.value("limit",
            limits.value("max_results", limits.value("max_rows", 0)));
        PortAnalyzer analyzer;
        return with_scalar_summary(Json::parse(analyzer.render_port_trace(path, limit)));
    }

private:
    static Json err(const char* code, const std::string& msg) {
        Json e; e["error"] = code; e["message"] = msg; return e;
    }
};

class InstanceMapHandler : public EngineActionHandler {
public:
    const char* action_name() const override { return "instance.map"; }
    bool needs_design() const override { return true; }
    bool needs_waveform() const override { return false; }

    Json run(const Json& request, EngineActionContext& ctx) const override {
        Json args = request.value("args", Json::object());
        std::string path = args.value("path", std::string());
        if (path.empty()) return err("MISSING_FIELD", "args.path is required");
        PortAnalyzer analyzer;
        return with_scalar_summary(Json::parse(analyzer.render_instance_map(path)));
    }

private:
    static Json err(const char* code, const std::string& msg) {
        Json e; e["error"] = code; e["message"] = msg; return e;
    }
};

class InterfaceResolveHandler : public EngineActionHandler {
public:
    const char* action_name() const override { return "interface.resolve"; }
    bool needs_design() const override { return true; }
    bool needs_waveform() const override { return false; }

    Json run(const Json& request, EngineActionContext& ctx) const override {
        Json args = request.value("args", Json::object());
        std::string path = args.value("path", std::string());
        if (path.empty()) return err("MISSING_FIELD", "args.path is required");
        PortAnalyzer analyzer;
        return with_scalar_summary(Json::parse(analyzer.render_interface_resolve(path)));
    }

private:
    static Json err(const char* code, const std::string& msg) {
        Json e; e["error"] = code; e["message"] = msg; return e;
    }
};

class TraceQueryHandler : public EngineActionHandler {
public:
    const char* action_name() const override { return "trace.query"; }
    bool needs_design() const override { return true; }
    bool needs_waveform() const override { return false; }
    Json run(const Json& request, EngineActionContext& ctx) const override {
        Json args = request.value("args", Json::object());
        std::string signal = args.value("signal", "");
        if (signal.empty()) return Json({{"error","MISSING_FIELD"},{"message","args.signal"}});
        std::string mode_str = args.value("mode", "driver");
        TraceMode mode = trace_mode_from_direction(mode_str);
        TraceOptions opts = parse_trace_opts(args);
        return Json::parse(trace_one_signal(signal, mode, opts).dump());
    }
};

// ── BFS-based handlers (trace.expand / trace.graph / trace.explain / trace.path) ──

class TraceExpandHandler : public EngineActionHandler {
public:
    const char* action_name() const override { return "trace.expand"; }
    bool needs_design() const override { return true; }
    bool needs_waveform() const override { return false; }
    Json run(const Json& request, EngineActionContext& ctx) const override {
        Json args = request.value("args", Json::object());
        std::string root = args.value("root_signal", args.value("signal", ""));
        std::string direction = args.value("direction", "driver");
        if (root.empty()) return Json({{"error","MISSING_FIELD"},{"message","args.signal"}});
        Json limits = request.value("limits", args.value("limits", Json::object()));

        detail::BfsOptions bopts;
        bopts.root = root;
        bopts.direction = direction;
        bopts.max_depth = std::max(1, limits.value("max_depth", 1));
        bopts.max_nodes = std::max(1, limits.value("max_nodes", 100));
        bopts.max_edges = std::max(1, limits.value("max_edges", limits.value("max_results", 200)));
        bopts.edge_type_filter = args;

        TraceMode mode = trace_mode_from_direction(direction);
        TraceOptions topts = parse_trace_opts(args);
        auto trace_fn = [&](const std::string& signal) -> nlohmann::json {
            return trace_one_signal(signal, mode, topts);
        };

        detail::BfsResult bfs = detail::run_trace_bfs(bopts, trace_fn);
        int agg_count = 0;
        int max_ev = std::max(1, limits.value("max_evidence_per_edge", 3));
        nlohmann::json rel_edges = detail::aggregate_edges_by_relation(bfs.all_edges, max_ev, agg_count);
        nlohmann::json trace;
        trace["query"] = root; trace["mode"] = direction;
        trace["dependency_edges"] = rel_edges;
        trace["confidence"] = bfs.first_confidence;
        trace["truncated"] = bfs.truncated;
        nlohmann::json graph = detail::graph_from_trace(trace, root);

        Json out;
        bool compact = compact_mode(request) && !include_arg(request, "include_debug");
        Json summary = trace_expand_summary(root, direction, bfs, graph, rel_edges, agg_count, compact);
        out["summary"] = summary;
        for (auto it = summary.begin(); it != summary.end(); ++it) {
            if (it.value().is_string() || it.value().is_number() || it.value().is_boolean())
                out[it.key()] = it.value();
        }
        out["meta"] = {{"truncated", bfs.truncated}};
        out["truncated"] = bfs.truncated;
        out["graph"] = Json::parse(graph.dump());
        if (!compact || include_arg(request, "include_trace"))
            out["trace"] = Json::parse(trace.dump());
        if (!compact || include_arg(request, "include_expanded_queries"))
            out["expanded_queries"] = Json::parse(bfs.expanded_queries.dump());
        append_bfs_warnings(out, bfs);
        if (!bfs.root_error.empty()) out["error"] = Json::parse(bfs.root_error.dump());
        return with_scalar_summary(out);
    }
};

class TraceGraphHandler : public EngineActionHandler {
public:
    const char* action_name() const override { return "trace.graph"; }
    bool needs_design() const override { return true; }
    bool needs_waveform() const override { return false; }
    Json run(const Json& request, EngineActionContext& ctx) const override {
        // trace.graph is an alias for trace.expand
        TraceExpandHandler h;
        return h.run(request, ctx);
    }
};

class TraceExplainHandler : public EngineActionHandler {
public:
    const char* action_name() const override { return "trace.explain"; }
    bool needs_design() const override { return true; }
    bool needs_waveform() const override { return false; }
    Json run(const Json& request, EngineActionContext& ctx) const override {
        Json args = request.value("args", Json::object());
        std::string root = args.value("root_signal", args.value("signal", ""));
        std::string direction = args.value("direction", "driver");
        if (root.empty()) return Json({{"error","MISSING_FIELD"},{"message","args.signal"}});
        Json limits = request.value("limits", args.value("limits", Json::object()));

        detail::BfsOptions bopts;
        bopts.root = root; bopts.direction = direction;
        bopts.max_depth = std::max(1, limits.value("max_depth", 1));
        bopts.max_nodes = std::max(1, limits.value("max_nodes", 100));
        bopts.max_edges = std::max(1, limits.value("max_edges", limits.value("max_results", 200)));
        bopts.edge_type_filter = args;

        TraceMode mode = trace_mode_from_direction(direction);
        TraceOptions topts = parse_trace_opts(args);
        auto trace_fn = [&](const std::string& signal) -> nlohmann::json {
            return trace_one_signal(signal, mode, topts);
        };

        detail::BfsResult bfs = detail::run_trace_bfs(bopts, trace_fn);
        int max_ev = std::max(1, limits.value("max_evidence_per_edge", 3));
        int agg_count = 0;
        nlohmann::json rel_edges = detail::aggregate_edges_by_relation(bfs.all_edges, max_ev, agg_count);

        nlohmann::json explanations = nlohmann::json::array();
        int skipped = 0;
        for (const auto& e : rel_edges) {
            nlohmann::json expl = detail::explanation_from_edge(e, root, direction, skipped);
            if (!expl.is_null()) explanations.push_back(expl);
        }

        nlohmann::json trace;
        trace["query"] = root;
        trace["mode"] = direction;
        trace["dependency_edges"] = rel_edges;
        trace["confidence"] = bfs.first_confidence;
        trace["truncated"] = bfs.truncated;

        Json out;
        bool compact = compact_mode(request);
        out["root_signal"] = root;
        out["direction"] = direction;
        out["explanation_count"] = explanations.size();
        out["edge_count"] = rel_edges.size();
        out["skipped_empty_dependency_count"] = skipped;
        out["truncated"] = bfs.truncated;
        out["explanations"] = Json::parse(explanations.dump());
        if (!compact || include_arg(request, "include_trace"))
            out["trace"] = Json::parse(trace.dump());
        if (!compact || include_arg(request, "include_expanded_queries"))
            out["expanded_queries"] = Json::parse(bfs.expanded_queries.dump());
        append_bfs_warnings(out, bfs);
        if (!bfs.root_error.empty()) out["error"] = Json::parse(bfs.root_error.dump());
        return with_scalar_summary(out);
    }
};

class TracePathHandler : public EngineActionHandler {
public:
    const char* action_name() const override { return "trace.path"; }
    bool needs_design() const override { return true; }
    bool needs_waveform() const override { return false; }
    Json run(const Json& request, EngineActionContext& ctx) const override {
        Json args = request.value("args", Json::object());
        std::string from_sig = args.value("from_signal", "");
        std::string to_sig = args.value("to_signal", "");
        if (from_sig.empty() || to_sig.empty())
            return Json({{"error","MISSING_FIELD"},{"message","args.from_signal and args.to_signal"}});
        Json limits = request.value("limits", args.value("limits", Json::object()));

        // BFS from to_signal to find reachable signals
        detail::BfsOptions bopts;
        bopts.root = to_sig; bopts.direction = "driver";
        bopts.max_depth = std::max(1, limits.value("max_depth", 5));
        bopts.max_nodes = std::max(1, limits.value("max_nodes", 200));
        bopts.max_edges = std::max(1, limits.value("max_edges", 500));
        bopts.edge_type_filter = args;

        TraceOptions topts = parse_trace_opts(args);
        auto trace_fn = [&](const std::string& signal) -> nlohmann::json {
            return trace_one_signal(signal, TraceMode::Driver, topts);
        };

        detail::BfsResult bfs = detail::run_trace_bfs(bopts, trace_fn);

        // BFS from from_signal following edges to find paths to to_sig
        // Build adjacency: signal → [edge to next signal]
        std::map<std::string, std::vector<nlohmann::json>> adj;
        for (const auto& e : bfs.all_edges) {
            std::string e_from = e.value("from", "");
            std::string e_to = e.value("to", "");
            adj[e_from].push_back(e);
        }

        bool found = false;
        nlohmann::json paths = nlohmann::json::array();
        int max_paths = std::max(1, limits.value("max_paths", 10));
        // Simple BFS path finding
        std::vector<std::pair<std::string, nlohmann::json>> pqueue;
        pqueue.push_back({from_sig, nlohmann::json::array()});
        std::set<std::string> pvisited;
        for (size_t pi = 0; pi < pqueue.size() && (int)paths.size() < max_paths; ++pi) {
            std::string cur = pqueue[pi].first;
            nlohmann::json cur_path = pqueue[pi].second;
            if (cur == to_sig) {
                found = true;
                paths.push_back(cur_path);
                continue;
            }
            if (pvisited.count(cur)) continue;
            pvisited.insert(cur);
            auto it = adj.find(cur);
            if (it == adj.end()) continue;
            for (auto& e : it->second) {
                std::string next = e.value("to", e.value("from", ""));
                if (next == cur || next.empty()) continue;
                nlohmann::json new_path = cur_path;
                new_path.push_back(e);
                pqueue.push_back({next, new_path});
            }
        }

        Json out;
        out["from_signal"] = from_sig;
        out["to_signal"] = to_sig;
        out["found"] = found;
        out["path_count"] = paths.size();
        out["truncated"] = bfs.truncated;
        out["summary"] = {
            {"from_signal", from_sig},
            {"to_signal", to_sig},
            {"found", found},
            {"path_count", paths.size()},
            {"truncated", bfs.truncated}
        };
        out["paths"] = Json::parse(paths.dump());
        return out;
    }
};

// ── Single-trace design handlers ───────────────────────────────────────

class ControlExplainHandler : public EngineActionHandler {
public:
    const char* action_name() const override { return "control.explain"; }
    bool needs_design() const override { return true; }
    bool needs_waveform() const override { return false; }
    Json run(const Json& request, EngineActionContext& ctx) const override {
        Json args = request.value("args", Json::object());
        std::string signal = args.value("signal", "");
        if (signal.empty()) return Json({{"error","MISSING_FIELD"},{"message","args.signal"}});

        TraceOptions opts = parse_trace_opts(args);
        nlohmann::json trace = trace_one_signal(signal, TraceMode::Driver, opts);
        nlohmann::json deps = trace.value("control_dependencies", nlohmann::json::array());
        for (auto& dep : deps) {
            std::string source = dep.value("source", "");
            std::string cond = source;
            size_t if_pos = cond.find("if");
            size_t lp = cond.find('(', if_pos == std::string::npos ? 0 : if_pos);
            size_t rp = cond.rfind(')');
            if (lp != std::string::npos && rp != std::string::npos && rp > lp)
                cond = cond.substr(lp + 1, rp - lp - 1);
            dep["condition_text"] = trim(cond);
            dep["condition"] = nlohmann::json::parse(parse_expr_ast(cond).dump());
            nlohmann::json sigs = nlohmann::json::array();
            sigs.push_back(dep.value("signal", ""));
            dep["condition_signals"] = sigs;
            dep["confidence"] = dep.value("source", "").empty() ? "low" : "medium";
        }

        Json out;
        out["summary"] = {{"signal",signal},{"control_dependency_count",deps.size()}};
        out["control_dependencies"] = Json::parse(deps.dump());
        return out;
    }
};

class ExprNormalizeHandler : public EngineActionHandler {
public:
    const char* action_name() const override { return "expr.normalize"; }
    bool needs_design() const override { return true; }
    bool needs_waveform() const override { return false; }
    Json run(const Json& request, EngineActionContext& ctx) const override {
        Json args = request.value("args", Json::object());
        std::string signal = args.value("signal", "");

        Json out;
        if (!signal.empty()) {
            TraceOptions opts = parse_trace_opts(args);
            nlohmann::json trace = trace_one_signal(signal, TraceMode::Driver, opts);
            nlohmann::json assignment = trace.value("assignment", nlohmann::json::object());
            out["summary"] = {{"signal",signal},{"source","npi_trace_assignment"},
                {"confidence",trace.value("confidence","unknown")}};
            out["expr"] = Json::parse(
                assignment.value("rhs", nlohmann::json::object()).dump());
            out["assignment"] = Json::parse(assignment.dump());
            out["rhs_signals"] = Json::parse(
                assignment.value("rhs_signals", nlohmann::json::array()).dump());
            out["confidence"] = trace.value("confidence", "unknown");
            return out;
        }
        std::string expr = args.value("expr", "");
        if (expr.empty()) return Json({{"error","MISSING_FIELD"},{"message","args.expr or args.signal"}});
        out["summary"] = {{"expr",expr},{"source","string_fallback"},{"confidence","low"}};
        out["expr"] = Json::parse(parse_expr_ast(expr).dump());
        out["confidence"] = "low";
        out["confidence_reason"] = "parsed from raw string without NPI handle";
        return out;
    }
};

class ProceduralAssignmentHandler : public EngineActionHandler {
public:
    const char* action_name() const override { return "procedural.assignment"; }
    bool needs_design() const override { return true; }
    bool needs_waveform() const override { return false; }
    Json run(const Json& request, EngineActionContext& ctx) const override {
        Json args = request.value("args", Json::object());
        std::string signal = args.value("signal", "");
        if (signal.empty()) return Json({{"error","MISSING_FIELD"},{"message","args.signal"}});

        TraceOptions opts = parse_trace_opts(args);
        nlohmann::json trace = trace_one_signal(signal, TraceMode::Driver, opts);
        nlohmann::json assignments = detail::normalize_assignments_with_conditions(trace);

        nlohmann::json defaults = nlohmann::json::array();
        nlohmann::json branches = nlohmann::json::array();
        for (const auto& a : assignments) {
            if (a.value("assignment_role", "") == "default_or_unconditional") defaults.push_back(a);
            else branches.push_back(a);
        }

        nlohmann::json enclosing;
        if (!assignments.empty())
            enclosing = nlohmann::json{{"type","procedural_or_continuous"},
                {"location",assignments[0].value("location",nlohmann::json::object())}};
        else
            enclosing = nlohmann::json{{"type","unknown"}};

        Json out;
        out["signal"] = signal;
        out["assignment_count"] = assignments.size();
        out["branch_count"] = branches.size();
        out["default_count"] = defaults.size();
        out["confidence"] = trace.value("confidence","unknown");
        nlohmann::json procedural_assignment = {
            {"target",signal},{"enclosing_block",enclosing},
            {"assignments",assignments},
            {"branch_assignments",branches},
            {"control_dependencies",trace.value("control_dependencies",nlohmann::json::array())},
            {"dependency_edges",trace.value("dependency_edges",nlohmann::json::array())},
            {"confidence",trace.value("confidence","unknown")},
            {"confidence_reason",trace.value("confidence_reason","")}
        };
        if (defaults != assignments) procedural_assignment["default_assignments"] = defaults;
        out["procedural_assignment"] = Json::parse(procedural_assignment.dump());
        return with_scalar_summary(out);
    }
};

class SequentialUpdateHandler : public EngineActionHandler {
public:
    const char* action_name() const override { return "sequential.update"; }
    bool needs_design() const override { return true; }
    bool needs_waveform() const override { return false; }
    Json run(const Json& request, EngineActionContext& ctx) const override {
        Json args = request.value("args", Json::object());
        std::string signal = args.value("signal", "");
        if (signal.empty()) return Json({{"error","MISSING_FIELD"},{"message","args.signal"}});

        TraceOptions opts = parse_trace_opts(args);
        nlohmann::json trace = trace_one_signal(signal, TraceMode::Driver, opts);
        nlohmann::json assignments = detail::normalize_assignments_with_conditions(trace);
        nlohmann::json controls = trace.value("control_dependencies", nlohmann::json::array());
        nlohmann::json timing = assignments.empty()
            ? nlohmann::json{{"clock",nullptr},{"reset",nullptr},{"event_controls",nlohmann::json::array()}}
            : detail::infer_clock_reset_from_assignment(assignments[0], controls);

        nlohmann::json rules = nlohmann::json::array();
        for (const auto& assignment : assignments) {
            nlohmann::json conditions = assignment.value("active_conditions", nlohmann::json::array());
            if (conditions.empty()) conditions.push_back({{"text",""},{"ast",nlohmann::json::object()},{"signals",nlohmann::json::array()}});
            for (const auto& cond : conditions) {
                rules.push_back({
                    {"kind", detail::classify_update_rule(assignment, cond, signal)},
                    {"condition", cond},
                    {"next_value", assignment.value("rhs", nlohmann::json::object())},
                    {"next_value_text", assignment.value("rhs", nlohmann::json::object()).value("text", assignment.value("source", ""))},
                    {"rhs_signals", assignment.value("rhs_signals", nlohmann::json::array())},
                    {"source", assignment.value("source", "")},
                    {"location", assignment.value("location", nlohmann::json::object())}
                });
            }
        }

        Json out;
        out["summary"] = {{"signal",signal},{"rule_count",rules.size()},
            {"clock", Json::parse(timing["clock"].dump())},
            {"reset", Json::parse(timing["reset"].dump())},
            {"confidence",trace.value("confidence","unknown")}};
        out["sequential_update"] = Json::parse(nlohmann::json{
            {"target",signal},
            {"clock", timing["clock"]}, {"reset", timing["reset"]},
            {"event_controls", timing["event_controls"]},
            {"rules", rules}, {"confidence", trace.value("confidence","unknown")},
            {"confidence_reason", trace.value("confidence_reason","")}
        }.dump());
        return out;
    }
};

class FsmExplainHandler : public EngineActionHandler {
public:
    const char* action_name() const override { return "fsm.explain"; }
    bool needs_design() const override { return true; }
    bool needs_waveform() const override { return false; }
    Json run(const Json& request, EngineActionContext& ctx) const override {
        // Reuse SequentialUpdateHandler logic
        SequentialUpdateHandler seq_handler;
        Json seq_resp = seq_handler.run(request, ctx);
        if (seq_resp.contains("error")) return seq_resp;

        Json args = request.value("args", Json::object());
        std::string signal = args.value("signal", "");
        nlohmann::json seq = nlohmann::json::parse(
            seq_resp.value("sequential_update", Json::object()).dump());

        nlohmann::json transitions = nlohmann::json::array();
        for (const auto& rule : seq.value("rules", nlohmann::json::array())) {
            std::string kind = rule.value("kind", "");
            if (kind == "reset" || kind == "update") {
                transitions.push_back({
                    {"from","current"}, {"to",rule.value("next_value_text","")},
                    {"condition",rule.value("condition",nlohmann::json::object())},
                    {"kind", kind == "reset" ? "reset_transition" : "transition"},
                    {"source",rule.value("source","")},
                    {"location",rule.value("location",nlohmann::json::object())}
                });
            }
        }

        Json out;
        out["summary"] = {{"signal",signal},{"transition_count",transitions.size()},
            {"confidence",seq.value("confidence","unknown")}};
        out["fsm"] = Json::parse(nlohmann::json{
            {"state_signal",signal},{"clock",seq["clock"]},
            {"reset",seq["reset"]},{"transitions",transitions},
            {"rules",seq["rules"]},{"confidence",seq.value("confidence","unknown")},
            {"confidence_reason",seq.value("confidence_reason","")}
        }.dump());
        return out;
    }
};

class CounterExplainHandler : public EngineActionHandler {
public:
    const char* action_name() const override { return "counter.explain"; }
    bool needs_design() const override { return true; }
    bool needs_waveform() const override { return false; }
    Json run(const Json& request, EngineActionContext& ctx) const override {
        SequentialUpdateHandler seq_handler;
        Json seq_resp = seq_handler.run(request, ctx);
        if (seq_resp.contains("error")) return seq_resp;

        Json args = request.value("args", Json::object());
        std::string signal = args.value("signal", "");
        nlohmann::json seq = nlohmann::json::parse(
            seq_resp.value("sequential_update", Json::object()).dump());

        nlohmann::json counter_rules = nlohmann::json::array();
        bool is_counter_like = false;
        for (const auto& rule : seq.value("rules", nlohmann::json::array())) {
            std::string kind = rule.value("kind", "");
            if (kind == "reset" || kind == "increment" || kind == "decrement" || kind == "hold" || kind == "update")
                counter_rules.push_back(rule);
            if (kind == "increment" || kind == "decrement") is_counter_like = true;
        }

        std::string conf = is_counter_like ? seq.value("confidence","medium") : "medium";
        Json out;
        out["summary"] = {{"signal",signal},{"counter_like",is_counter_like},
            {"rule_count",counter_rules.size()},{"confidence",conf}};
        out["counter"] = Json::parse(nlohmann::json{
            {"signal",signal},{"clock",seq["clock"]},
            {"reset",seq["reset"]},{"rules",counter_rules},
            {"counter_like",is_counter_like},{"confidence",conf},
            {"confidence_reason", is_counter_like
                ? "increment/decrement rule was identified from next-value expression"
                : "sequential rules were found but no increment/decrement pattern was proven"}
        }.dump());
        return out;
    }
};

// ── Zero-dependency design handlers ────────────────────────────────────

class SourceContextHandler : public EngineActionHandler {
public:
    const char* action_name() const override { return "source.context"; }
    bool needs_design() const override { return false; }
    bool needs_waveform() const override { return false; }
    Json run(const Json& request, EngineActionContext& ctx) const override {
        Json args = request.value("args", Json::object());
        std::string file = args.value("file", "");
        int line = args.value("line", 0);
        if (file.empty() || line <= 0)
            return Json({{"error","MISSING_FIELD"},{"message","args.file and args.line"}});

        bool compact = request.value("output", Json::object()).value("verbosity", "") == "compact";
        bool include_src = args.value("include_source", false);
        int ctx_lines = args.value("context_lines", compact && !include_src ? 3 : 8);

        std::ifstream in(file);
        if (!in) return Json({{"error","SOURCE_NOT_FOUND"},{"message",file}});
        std::vector<std::string> lines;
        std::string s;
        while (std::getline(in, s)) lines.push_back(s);
        if (line > (int)lines.size())
            return Json({{"error","INVALID_REQUEST"},{"message","line out of range"}});

        int begin = std::max(1, line - ctx_lines);
        int end = std::min((int)lines.size(), line + ctx_lines);
        nlohmann::json enclosing = detail::infer_enclosing_block(lines, line);

        Json out;
        out["summary"] = {{"file",file},{"line",line}};
        out["file"] = file;
        out["line"] = line;
        out["symbol"] = args.value("symbol", "");
        out["context_kind"] = enclosing.value("type", "unknown");
        out["enclosing"] = Json::parse(enclosing.dump());
        if (!compact || include_src) {
            nlohmann::json ctx = nlohmann::json::array();
            for (int i = begin; i <= end; ++i)
                ctx.push_back({{"line",i},{"text",lines[i-1]},{"hit",i == line}});
            out["context"] = Json::parse(ctx.dump());
        }
        return out;
    }
};

class SignalCanonicalizeHandler : public EngineActionHandler {
public:
    const char* action_name() const override { return "signal.canonicalize"; }
    bool needs_design() const override { return true; }
    bool needs_waveform() const override { return false; }
    Json run(const Json& request, EngineActionContext& ctx) const override {
        Json args = request.value("args", Json::object());
        std::string query = args.value("signal", "");
        if (query.empty()) return Json({{"error","MISSING_FIELD"},{"message","args.signal"}});

        SignalFinder finder;
        SignalResolveResult result = finder.resolve(query);
        nlohmann::json resolved = nlohmann::json::parse(finder.render_json(result));

        // Extract canonical from first match
        nlohmann::json canonical = nullptr, rtl_path = nullptr, leaf = nullptr, scope = nullptr;
        nlohmann::json base_signal = nullptr, select = nullptr;
        nlohmann::json aliases = nlohmann::json::array();
        bool ambiguous = false;
        nlohmann::json fsdb_candidates = nlohmann::json::array();
        nlohmann::json port_mappings = nlohmann::json::array();

        if (resolved.contains("rtl_path")) rtl_path = resolved["rtl_path"];
        if (resolved.contains("canonical_signal")) canonical = resolved["canonical_signal"];
        else if (resolved.contains("canonical")) canonical = resolved["canonical"];
        else if (rtl_path.is_string()) canonical = rtl_path;
        else canonical = query;

        if (resolved.contains("leaf")) leaf = resolved["leaf"];
        if (resolved.contains("scope")) scope = resolved["scope"];
        if (resolved.contains("base_signal")) base_signal = resolved["base_signal"];
        if (resolved.contains("select")) select = resolved["select"];
        if (resolved.contains("aliases")) aliases = resolved["aliases"];
        if (resolved.contains("ambiguous")) ambiguous = resolved["ambiguous"].get<bool>();
        if (resolved.contains("fsdb_candidates")) fsdb_candidates = resolved["fsdb_candidates"];
        if (resolved.contains("port_mappings")) port_mappings = resolved["port_mappings"];

        Json out;
        out["summary"] = {{"query",query},{"ambiguous",ambiguous}};
        out["query"] = query;
        out["canonical"] = Json::parse(canonical.dump());
        out["rtl_path"] = Json::parse(rtl_path.dump());
        out["leaf"] = Json::parse(leaf.dump());
        out["scope"] = Json::parse(scope.dump());
        out["base_signal"] = Json::parse(base_signal.dump());
        out["select"] = Json::parse(select.dump());
        out["ambiguous"] = ambiguous;
        out["aliases"] = Json::parse(aliases.dump());
        out["fsdb_candidates"] = Json::parse(fsdb_candidates.dump());
        out["port_mappings"] = Json::parse(port_mappings.dump());
        return out;
    }
};

// ═══════════════════════════════════════════════════════════════════════
// Not-yet-implemented action handlers (return NOT_IMPLEMENTED)
// ═══════════════════════════════════════════════════════════════════════

}  // namespace

void register_design_handlers(EngineActionRegistry& r) {
    r.add(std::unique_ptr<EngineActionHandler>(new TraceDriverHandler));
    r.add(std::unique_ptr<EngineActionHandler>(new TraceLoadHandler));
    r.add(std::unique_ptr<EngineActionHandler>(new SignalResolveHandler));
    r.add(std::unique_ptr<EngineActionHandler>(new PortTraceHandler));
    r.add(std::unique_ptr<EngineActionHandler>(new InstanceMapHandler));
    r.add(std::unique_ptr<EngineActionHandler>(new InterfaceResolveHandler));
    r.add(std::unique_ptr<EngineActionHandler>(new TraceQueryHandler));
    r.add(std::unique_ptr<EngineActionHandler>(new TraceExpandHandler));
    r.add(std::unique_ptr<EngineActionHandler>(new TraceGraphHandler));
    r.add(std::unique_ptr<EngineActionHandler>(new TracePathHandler));
    r.add(std::unique_ptr<EngineActionHandler>(new TraceExplainHandler));
    r.add(std::unique_ptr<EngineActionHandler>(new SignalCanonicalizeHandler));
    r.add(std::unique_ptr<EngineActionHandler>(new ControlExplainHandler));
    r.add(std::unique_ptr<EngineActionHandler>(new SourceContextHandler));
    r.add(std::unique_ptr<EngineActionHandler>(new ExprNormalizeHandler));
    r.add(std::unique_ptr<EngineActionHandler>(new ProceduralAssignmentHandler));
    r.add(std::unique_ptr<EngineActionHandler>(new SequentialUpdateHandler));
    r.add(std::unique_ptr<EngineActionHandler>(new FsmExplainHandler));
    r.add(std::unique_ptr<EngineActionHandler>(new CounterExplainHandler));
}

}  // namespace xdebug_design
