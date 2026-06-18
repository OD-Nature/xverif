#include "action_support.h"

#include <cctype>
#include <set>
#include <utility>

namespace xdebug_design {

namespace {

int find_top_level_op(const std::string& s, const std::string& op) {
    int depth = 0;
    for (int i = static_cast<int>(s.size()) - static_cast<int>(op.size()); i >= 0; --i) {
        char c = s[i];
        if (c == ')') depth++;
        else if (c == '(') depth--;
        if (depth == 0 && s.compare(i, op.size(), op) == 0) return i;
    }
    return -1;
}

json parse_atom(const std::string& text) {
    std::string s = trim(text);
    if (s.empty()) return {{"type", "unknown"}, {"text", ""}};
    if (s.size() >= 2 && s.front() == '(' && s.back() == ')') {
        return parse_expr_ast(s.substr(1, s.size() - 2));
    }
    if (s[0] == '!') {
        return {{"op", "not"}, {"args", json::array({parse_expr_ast(s.substr(1))})}};
    }
    bool numeric_or_const = false;
    for (char c : s) {
        if (std::isdigit(static_cast<unsigned char>(c)) || c == '\'' || c == 'h' || c == 'b' || c == 'd' ||
            c == 'x' || c == 'z' || c == '_' || c == '-') {
            numeric_or_const = true;
        } else {
            numeric_or_const = false;
            break;
        }
    }
    if (numeric_or_const || s == "RUN" || s == "IDLE" || s == "BUSY") {
        return {{"type", "const"}, {"value", s}};
    }
    return {{"type", "signal"}, {"name", s}};
}

void collect_ast_signals(const json& node, std::set<std::string>& signals) {
    if (!node.is_object()) return;
    std::string kind = node.value("kind", node.value("type", ""));
    if (kind == "signal") {
        std::string name = node.value("name", "");
        if (!name.empty()) signals.insert(name);
    }
    if (node.contains("base_signal") && node["base_signal"].is_string()) {
        std::string name = node["base_signal"].get<std::string>();
        if (!name.empty()) signals.insert(name);
    }
    for (const auto& item : node.items()) {
        if (item.value().is_object()) collect_ast_signals(item.value(), signals);
        if (item.value().is_array()) {
            for (const auto& elem : item.value()) collect_ast_signals(elem, signals);
        }
    }
}

std::string rhs_from_source(const std::string& source) {
    std::string s = trim(source);
    size_t eq = std::string::npos;
    size_t le = s.find("<=");
    if (le != std::string::npos) eq = le + 1;
    else eq = s.find('=');
    if (eq == std::string::npos) return "";
    std::string rhs = s.substr(eq + 1);
    size_t semi = rhs.rfind(';');
    if (semi != std::string::npos) rhs = rhs.substr(0, semi);
    return trim(rhs);
}

std::string assignment_kind_from_source(const std::string& source) {
    std::string s = trim(source);
    if (starts_with(s, "assign ")) return "continuous_assign";
    if (s.find("<=") != std::string::npos) return "clocked_update";
    if (s.find("=") != std::string::npos) return "procedural_assignment";
    return "statement_only";
}

std::string confidence_for_trace(const json& trace) {
    if (!trace.value("ok", true)) return "unknown";
    if (trace.value("has_statement_only", false)) return "low";
    int count = trace.value("result_count", 0);
    if (count <= 0 && trace.value("control_dependency_count", 0) <= 0) return "unknown";
    for (const auto& r : trace.value("results", json::array())) {
        if (!r.value("source", "").empty()) return "high";
    }
    return "medium";
}

json compact_trace_payload(const json& request, const json& trace, const std::string& mode) {
    json args = request.value("args", json::object());
    std::string query = trace.value("query", args.value("signal", args.value("root_signal", "")));
    json items = json::array();
    json control_signals = json::array();
    for (const auto& edge : trace.value("dependency_edges", json::array())) {
        std::string type = edge.value("type", "");
        std::string related = mode == "load" ? edge.value("to", "") : edge.value("from", "");
        if (related.empty() && type != "statement_only") continue;
        json item = {
            {"signal", related.empty() ? query : related},
            {"kind", type.empty() ? edge.value("resolution", "") : type},
            {"rhs_signals", json::array()},
            {"condition_signals", json::array()},
            {"file", edge.value("file", "")},
            {"line", edge.value("line", 0)},
            {"confidence", edge.value("confidence", trace.value("confidence", "unknown"))}
        };
        if (type == "control_dependency") {
            item["condition_signals"].push_back(related);
            control_signals.push_back(related);
        } else if (!related.empty() && mode != "load") {
            item["rhs_signals"].push_back(related);
        }
        items.push_back(item);
    }
    if (items.empty()) {
        for (const auto& r : trace.value("results", json::array())) {
            items.push_back({
                {"signal", r.value("signal", "")},
                {"kind", r.value("resolution", r.value("role", ""))},
                {"rhs_signals", json::array()},
                {"condition_signals", json::array()},
                {"file", r.value("file", "")},
                {"line", r.value("line", 0)},
                {"confidence", trace.value("confidence", "unknown")}
            });
        }
    }
    json out = json::object();
    out[mode == "load" ? "loads" : "drivers"] = items;
    out["signal"] = query;
    out["mode"] = mode;
    out["confidence"] = trace.value("confidence", "unknown");
    return out;
}

} // namespace

json parse_expr_ast(const std::string& expr) {
    std::string s = trim(expr);
    if (s.empty()) return {{"type", "unknown"}, {"text", ""}};
    int qpos = find_top_level_op(s, "?");
    if (qpos >= 0) {
        int depth = 0;
        for (size_t i = qpos + 1; i < s.size(); ++i) {
            if (s[i] == '(') depth++;
            else if (s[i] == ')') depth--;
            else if (s[i] == ':' && depth == 0) {
                return {{"op", "ternary"},
                        {"args", json::array({parse_expr_ast(s.substr(0, qpos)),
                                               parse_expr_ast(s.substr(qpos + 1, i - qpos - 1)),
                                               parse_expr_ast(s.substr(i + 1))})}};
            }
        }
    }
    const std::vector<std::pair<std::string, std::string>> ops = {
        {"||", "or"}, {"&&", "and"}, {"!=", "neq"}, {"==", "eq"},
        {">=", "ge"}, {"<=", "le"}, {">", "gt"}, {"<", "lt"},
        {"+", "add"}, {"-", "sub"}, {"*", "mul"}
    };
    for (const auto& item : ops) {
        int pos = find_top_level_op(s, item.first);
        if (pos > 0) {
            return {{"op", item.second},
                    {"args", json::array({parse_expr_ast(s.substr(0, pos)),
                                           parse_expr_ast(s.substr(pos + item.first.size()))})}};
        }
    }
    return parse_atom(s);
}

std::string expr_op(const json& expr) {
    return expr.is_object() ? expr.value("op", "") : "";
}

bool expr_mentions_signal(const json& expr, const std::string& signal) {
    std::set<std::string> signals;
    collect_ast_signals(expr, signals);
    std::string target_leaf = leaf_name(signal);
    for (const auto& name : signals) {
        if (name == signal || leaf_name(name) == target_leaf) return true;
    }
    return false;
}

json signal_array_from_ast(const json& expr) {
    std::set<std::string> signals;
    collect_ast_signals(expr, signals);
    json out = json::array();
    for (const auto& name : signals) out.push_back(name);
    return out;
}

json enrich_trace_payload(const json& request, const json& trace) {
    json out = trace;
    std::string query = trace.value("query", request.value("args", json::object()).value("signal", ""));
    std::string mode = trace.value("mode", "driver");
    json rhs_signals = json::array();
    json edges = json::array();
    json records = trace.value("results", json::array());
    for (const auto& r : records) {
        std::string signal = r.value("signal", "");
        std::string role = r.value("role", "");
        std::string resolution = r.value("resolution", "");
        if (!signal.empty() && resolution != "statement_only") rhs_signals.push_back(signal);
        std::string edge_type = resolution == "statement_only" ? "statement_only" : "data_dependency";
        if (role == "lhs_target") edge_type = "load_dependency";
        edges.push_back({
            {"from", mode == "driver" ? signal : query}, {"to", mode == "driver" ? query : signal},
            {"type", edge_type}, {"role", role}, {"file", r.value("file", "")},
            {"line", r.value("line", 0)}, {"source", r.value("source", "")},
            {"resolution", resolution}, {"confidence", edge_type == "statement_only" ? "low" : "high"}
        });
    }
    for (const auto& r : trace.value("control_dependencies", json::array())) {
        edges.push_back({
            {"from", r.value("signal", "")}, {"to", query}, {"type", "control_dependency"},
            {"relation", "controls_assignment"}, {"file", r.value("file", "")},
            {"line", r.value("line", 0)}, {"source", r.value("source", "")},
            {"resolution", r.value("resolution", "")}, {"confidence", "medium"}
        });
    }
    std::string confidence = confidence_for_trace(trace);
    out["rhs_signals"] = rhs_signals;
    out["dependency_edges"] = edges;
    out["confidence"] = confidence;
    out["confidence_reason"] =
        confidence == "high" ? "exact signal references with source locations were resolved" :
        confidence == "medium" ? "trace records were resolved but structured expression is incomplete" :
        confidence == "low" ? "trace contains statement_only or fallback records" :
        "no reliable trace result was resolved";
    if (!records.empty()) {
        std::string source = records[0].value("source", "");
        std::string rhs = rhs_from_source(source);
        if (!rhs.empty()) {
            out["assignment"] = {{"kind", assignment_kind_from_source(source)},
                {"lhs", {{"type", "signal"}, {"name", query}}},
                {"rhs", parse_expr_ast(rhs)}, {"source", source},
                {"ast_confidence", "heuristic"}};
        }
    }
    return out;
}

json make_trace_summary(const json& trace) {
    return {{"query", trace.value("query", "")}, {"mode", trace.value("mode", "")},
        {"result_count", trace.value("result_count", 0)},
        {"control_dependency_count", trace.value("control_dependency_count", 0)},
        {"truncated", trace.value("truncated", false)},
        {"confidence", trace.value("confidence", "unknown")}};
}

json run_trace_action(const json& request, const std::string& mode) {
    json response = base_response(request, request.value("action", ""));
    std::string session_id;
    SessionInfo session;
    if (!ensure_target_session(request, response, session_id, session)) return response;
    json args = request.value("args", json::object());
    std::string signal = args.value("signal", args.value("root_signal", ""));
    if (signal.empty()) return error_response(request, request.value("action", ""), "MISSING_FIELD", "args.signal is required");
    json rpc_args = args;
    const json limits = request.value("limits", json::object());
    if (limits.contains("max_results")) rpc_args["limit"] = limits["max_results"];
    if (limits.contains("max_rows") && !rpc_args.contains("limit")) rpc_args["limit"] = limits["max_rows"];
    json trace;
    std::string status, message;
    json engine_error;
    if (!send_json_command(session_id, mode == "load" ? "trace.load" : "trace.driver",
                           rpc_args, trace, status, message, engine_error)) {
        if (!engine_error.is_null()) {
            json resp = base_response(request, request.value("action", ""));
            resp["ok"] = false;
            resp["error"] = engine_error;
            return resp;
        }
        return error_response(request, request.value("action", ""), "SESSION_UNHEALTHY", message.empty() ? status : message);
    }
    json enriched = trace.contains("dependency_edges") ? trace : enrich_trace_payload(request, trace);
    response["ok"] = enriched.value("ok", true);
    response["summary"] = make_trace_summary(enriched);
    if (compact_mode(request) && !include_arg(request, "include_trace") &&
        !include_arg(request, "include_ast") && !include_arg(request, "include_source") &&
        !include_arg(request, "include_candidates")) {
        response["data"] = compact_trace_payload(request, enriched, mode);
    } else {
        response["data"] = enriched;
    }
    response["meta"]["truncated"] = enriched.value("truncated", false);
    if (!response["ok"].get<bool>()) {
        response["error"] = {{"code", "SIGNAL_NOT_FOUND"}, {"message", enriched.value("error", "trace failed")},
            {"recoverable", true}, {"candidates", json::array()}, {"suggested_actions", json::array({{
                {"tool", "shell"}, {"action", "rg"},
                {"reason", "xdebug_design requires an exact signal path; use source grep to discover candidate names"},
                {"args", {{"query", leaf_name(signal)}}}}})}};
    }
    return response;
}

json run_signal_resolve_action(const json& request) {
    json response = base_response(request, request.value("action", ""));
    std::string session_id;
    SessionInfo session;
    if (!ensure_target_session(request, response, session_id, session)) return response;
    json args = request.value("args", json::object());
    std::string query = args.value("signal", args.value("query", ""));
    if (query.empty()) return error_response(request, request.value("action", ""), "MISSING_FIELD", "args.signal or args.query is required");
    json payload;
    std::string status, message;
    json engine_error;
    if (!send_json_command(session_id, "signal.resolve", {{"signal", query}}, payload, status, message, engine_error)) {
        return error_response(request, request.value("action", ""), "SESSION_UNHEALTHY", message.empty() ? status : message);
    }
    response["ok"] = payload.value("ok", true);
    response["summary"] = {{"query", payload.value("query", query)}, {"count", payload.value("count", 0)},
                            {"truncated", payload.value("truncated", false)}};
    response["data"] = payload;
    response["meta"]["truncated"] = payload.value("truncated", false);
    if (!response["ok"].get<bool>()) {
        response["error"] = {{"code", "SIGNAL_NOT_FOUND"}, {"message", payload.value("message", "signal not found")},
            {"recoverable", true}, {"candidates", payload.value("matches", json::array())},
            {"suggested_actions", json::array({{{"tool", "shell"}, {"action", "rg"},
                {"reason", "xdebug_design signal.resolve only accepts exact paths; use source grep to discover candidate names"},
                {"args", {{"query", leaf_name(query)}}}}})}};
    }
    return response;
}

json canonicalize_signal(const json& request) {
    json resolved = run_signal_resolve_action(request);
    if (!resolved.value("ok", false)) return resolved;
    json data = resolved.value("data", json::object());
    std::string query = data.value("query", request.value("args", json::object()).value("signal", ""));
    std::string canonical = query;
    json matches = data.value("matches", json::array());
    if (!matches.empty()) canonical = matches[0].value("signal", query);
    bool ambiguous = matches.size() > 1;
    std::string base = canonical;
    std::string select;
    size_t bracket = canonical.find('[');
    if (bracket != std::string::npos) {
        base = canonical.substr(0, bracket);
        select = canonical.substr(bracket);
    }
    size_t dot = base.rfind('.');
    resolved["summary"]["canonical"] = canonical;
    resolved["summary"]["ambiguous"] = ambiguous;
    resolved["data"]["canonical"] = canonical;
    resolved["data"]["rtl_path"] = canonical;
    resolved["data"]["query"] = query;
    resolved["data"]["leaf"] = leaf_name(canonical);
    resolved["data"]["scope"] = dot == std::string::npos ? "" : base.substr(0, dot);
    resolved["data"]["base_signal"] = base;
    resolved["data"]["select"] = select;
    resolved["data"]["ambiguous"] = ambiguous;
    resolved["data"]["aliases"] = query == canonical ? json::array({canonical}) : json::array({query, canonical});
    resolved["data"]["fsdb_candidates"] = json::array({canonical});
    resolved["data"]["port_mappings"] = json::array();
    return resolved;
}

} // namespace xdebug_design
