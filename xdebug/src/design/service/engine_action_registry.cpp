#include "engine_action_registry.h"

#include "../trace/trace_engine.h"
#include "../signal/signal_finder.h"
#include "../port/port_analyzer.h"
#include "../protocol/protocol.h"

// Waveform value-reader (lightweight header, no text-protocol deps).
#include "../../waveform/server/fsdb_value_reader.h"

// Forward-declare waveform helpers we call directly.
namespace xdebug_waveform {
bool parse_user_time(const char* text, bool allow_max,
                     npiFsdbTime& out_time, std::string& error);
// ai_* functions from waveform/server/service/query_actions.cpp
nlohmann::ordered_json ai_dispatch_query(const nlohmann::ordered_json& req,
                                          std::string& error);
nlohmann::ordered_json ai_cursor_action(const std::string& action,
                                         const nlohmann::ordered_json& args,
                                         std::string& error);
}  // namespace xdebug_waveform

#include "npi.h"
#include "npi_fsdb.h"
#include "npi_L1.h"

#include "../../combined/active_trace_service.h"
#include "../../combined/active_trace_chain.h"

namespace xdebug_design {

// ═══════════════════════════════════════════════════════════════════════
// Design action handlers
// ═══════════════════════════════════════════════════════════════════════

namespace {

// Helper: parse trace options from args (same as server.cpp)
static TraceOptions parse_trace_opts(const Json& args) {
    TraceOptions opts;
    opts.limit = args.value("limit", 0);
    opts.role = args.value("role", std::string());
    opts.no_statement_only = args.value("no_statement_only", false);
    if (args.contains("include_statement_only") && args["include_statement_only"].is_boolean())
        opts.no_statement_only = !args["include_statement_only"].get<bool>();
    return opts;
}

class TraceDriverHandler : public EngineActionHandler {
public:
    const char* action_name() const override { return "trace.driver"; }
    bool needs_design() const override { return true; }
    bool needs_waveform() const override { return false; }

    Json run(const Json& request) const override {
        Json args = request.value("args", Json::object());
        std::string signal = args.value("signal", std::string());
        if (signal.empty()) return err("MISSING_FIELD", "args.signal is required");
        TraceEngine engine;
        TraceResult result = engine.trace(signal, TraceMode::Driver, parse_trace_opts(args));
        return Json::parse(engine.render_ai_json(result));
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

    Json run(const Json& request) const override {
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

    Json run(const Json& request) const override {
        Json args = request.value("args", Json::object());
        std::string signal = args.value("signal", std::string());
        if (signal.empty()) return err("MISSING_FIELD", "args.signal is required");
        SignalFinder finder;
        SignalResolveResult result = finder.resolve(signal);
        return Json::parse(finder.render_json(result));
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

    Json run(const Json& request) const override {
        Json args = request.value("args", Json::object());
        std::string path = args.value("path", std::string());
        if (path.empty()) return err("MISSING_FIELD", "args.path is required");
        int limit = args.value("limit", 0);
        PortAnalyzer analyzer;
        return Json::parse(analyzer.render_port_trace(path, limit));
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

    Json run(const Json& request) const override {
        Json args = request.value("args", Json::object());
        std::string path = args.value("path", std::string());
        if (path.empty()) return err("MISSING_FIELD", "args.path is required");
        PortAnalyzer analyzer;
        return Json::parse(analyzer.render_instance_map(path));
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

    Json run(const Json& request) const override {
        Json args = request.value("args", Json::object());
        std::string path = args.value("path", std::string());
        if (path.empty()) return err("MISSING_FIELD", "args.path is required");
        PortAnalyzer analyzer;
        return Json::parse(analyzer.render_interface_resolve(path));
    }

private:
    static Json err(const char* code, const std::string& msg) {
        Json e; e["error"] = code; e["message"] = msg; return e;
    }
};

// ═══════════════════════════════════════════════════════════════════════
// Waveform action handlers
// ═══════════════════════════════════════════════════════════════════════

} // anonymous namespace

// References to unified-engine globals defined in server.cpp.
extern bool g_has_design;
extern bool g_has_waveform;
extern npiFsdbFileHandle g_fsdb_file;
extern std::string g_fsdb_path;
extern std::string g_daidir_path;
extern std::string g_session_id;

namespace {

static bool contains_xz(const std::string& v) {
    return v.find_first_of("xXzZ") != std::string::npos;
}

// Parse TimeSpec string (e.g. "100ns") via waveform's parse_user_time with
// fallback to simple <value><unit> conversion.
static bool engine_parse_time(const std::string& text, npiFsdbTime& out) {
    std::string error;
    if (xdebug_waveform::parse_user_time(text.c_str(), false, out, error))
        return true;
    double val = 0;
    std::string unit;
    char* end = nullptr;
    val = std::strtod(text.c_str(), &end);
    if (!end || end == text.c_str()) return false;
    while (*end && std::isspace(static_cast<unsigned char>(*end))) ++end;
    unit = end;
    if (unit.empty()) return false;
    return npi_fsdb_convert_time_in(g_fsdb_file, val, unit.c_str(), out) != 0;
}

class ValueAtHandler : public EngineActionHandler {
public:
    const char* action_name() const override { return "value.at"; }
    bool needs_design() const override { return false; }
    bool needs_waveform() const override { return true; }

    Json run(const Json& request) const override {
        Json args = request.value("args", Json::object());
        std::string signal = args.value("signal", std::string());
        std::string time_str = args.value("time", std::string());
        std::string fmt_str = args.value("format", std::string("h"));
        if (signal.empty() || time_str.empty())
            return err("MISSING_FIELD", "args.signal and args.time are required");

        char fmt = static_cast<char>(std::tolower(
            static_cast<unsigned char>(fmt_str.empty() ? 'h' : fmt_str[0])));
        if (fmt != 'h' && fmt != 'b' && fmt != 'd') fmt = 'h';

        npiFsdbTime fsdb_time = 0;
        if (!engine_parse_time(time_str, fsdb_time))
            return err("TIME_SPEC_INVALID", "failed to parse time: " + time_str);

        npiFsdbValType vtype = xdebug_waveform::parse_format(fmt);
        std::string raw;
        if (!npi_fsdb_sig_value_at(g_fsdb_file, signal.c_str(), fsdb_time, raw, vtype))
            return err("SIGNAL_NOT_FOUND", "failed to read value: " + signal);

        Json out;
        out["signal"] = signal;
        out["time"] = time_str;
        out["value"] = raw;
        out["known"] = !contains_xz(raw);
        return out;
    }

private:
    static Json err(const char* code, const std::string& msg) {
        Json e; e["error"] = code; e["message"] = msg; return e;
    }
};

class ValueBatchAtHandler : public EngineActionHandler {
public:
    const char* action_name() const override { return "value.batch_at"; }
    bool needs_design() const override { return false; }
    bool needs_waveform() const override { return true; }

    Json run(const Json& request) const override {
        Json args = request.value("args", Json::object());
        Json signals_j = args.value("signals", Json::array());
        std::string time_str = args.value("time", std::string());
        std::string fmt_str = args.value("format", std::string("h"));
        if (!signals_j.is_array() || signals_j.empty() || time_str.empty())
            return err("MISSING_FIELD", "args.signals[] and args.time are required");

        char fmt = static_cast<char>(std::tolower(
            static_cast<unsigned char>(fmt_str.empty() ? 'h' : fmt_str[0])));
        if (fmt != 'h' && fmt != 'b' && fmt != 'd') fmt = 'h';

        npiFsdbTime fsdb_time = 0;
        if (!engine_parse_time(time_str, fsdb_time))
            return err("TIME_SPEC_INVALID", "failed to parse time: " + time_str);

        std::vector<std::string> names;
        for (const auto& s : signals_j)
            if (s.is_string()) names.push_back(s.get<std::string>());

        std::vector<std::string> values;
        std::vector<bool> found;
        xdebug_waveform::read_sig_vec_value_at_with_status(
            g_fsdb_file, names, fsdb_time, fmt, values, found);

        Json out;
        out["time"] = time_str;
        Json batch = Json::object();
        for (size_t i = 0; i < names.size(); ++i) {
            Json item;
            item["signal"] = names[i];
            item["value"] = found[i] ? values[i] : "";
            item["known"] = found[i] && !contains_xz(values[i]);
            if (!found[i]) item["status"] = "signal_not_found";
            batch[names[i]] = item;
        }
        out["signals"] = batch;
        return out;
    }

private:
    static Json err(const char* code, const std::string& msg) {
        Json e; e["error"] = code; e["message"] = msg; return e;
    }
};

class ScopeListHandler : public EngineActionHandler {
public:
    const char* action_name() const override { return "scope.list"; }
    bool needs_design() const override { return false; }
    bool needs_waveform() const override { return true; }

    Json run(const Json& request) const override {
        Json args = request.value("args", Json::object());
        std::string path = args.value("path", std::string(""));
        bool recursive = args.value("recursive", true);
        int max_depth = args.value("max_depth", 3);

        FILE* fp = tmpfile();
        if (!fp) return err("INTERNAL_ERROR", "tmpfile failed");
        npi_fsdb_hier_tree_dump_sig(g_fsdb_file, fp, path.c_str(),
                                     recursive ? max_depth : 1);
        fflush(fp); rewind(fp);

        Json scopes = Json::array();
        Json signals = Json::array();
        char line[4096];
        while (fgets(line, sizeof(line), fp)) {
            size_t len = strlen(line);
            while (len > 0 && (line[len-1]=='\n' || line[len-1]=='\r')) line[--len]='\0';
            if (len == 0) continue;
            std::string s(line, len);
            bool is_scope = s.find("(scope)") != std::string::npos;
            size_t pos = s.find("  (");
            std::string name = (pos != std::string::npos) ? s.substr(0, pos) : s;
            if (is_scope) scopes.push_back(name);
            else signals.push_back(name);
        }
        fclose(fp);

        Json out;
        out["path"] = path;
        out["recursive"] = recursive;
        out["scopes"] = scopes;
        out["signals"] = signals;
        out["signals_preview"] = signals;
        out["total_signals"] = static_cast<int>(signals.size());
        return out;
    }

private:
    static Json err(const char* code, const std::string& msg) {
        Json e; e["error"] = code; e["message"] = msg; return e;
    }
};

// ═══════════════════════════════════════════════════════════════════════
// Combined action handlers
// ═══════════════════════════════════════════════════════════════════════

class ActiveDriverHandler : public EngineActionHandler {
public:
    const char* action_name() const override { return "trace.active_driver"; }
    bool needs_design() const override { return true; }
    bool needs_waveform() const override { return true; }

    Json run(const Json& request) const override {
        xdebug::ActiveTraceService svc;
        return svc.run_engine(request, g_daidir_path, g_fsdb_path, g_fsdb_file);
    }
};

class ActiveDriverChainHandler : public EngineActionHandler {
public:
    const char* action_name() const override { return "trace.active_driver_chain"; }
    bool needs_design() const override { return true; }
    bool needs_waveform() const override { return true; }

    Json run(const Json& request) const override {
        xdebug::ActiveTraceChainService svc;
        return svc.run_engine(request, g_daidir_path, g_fsdb_path, g_fsdb_file);
    }
};

// ═══════════════════════════════════════════════════════════════════════
// Generic handler that wraps an ai_* function (Json→Json, no text protocol)
// ═══════════════════════════════════════════════════════════════════════

class AiActionHandler : public EngineActionHandler {
    std::string name_;
    bool nd_, nw_;
public:
    AiActionHandler(const char* name, bool needs_design, bool needs_waveform)
        : name_(name), nd_(needs_design), nw_(needs_waveform) {}
    const char* action_name() const override { return name_.c_str(); }
    bool needs_design() const override { return nd_; }
    bool needs_waveform() const override { return nw_; }
    Json run(const Json& request) const override {
        std::string error;
        Json result = xdebug_waveform::ai_dispatch_query(request, error);
        if (!error.empty()) {
            Json e; e["error"] = "ACTION_FAILED"; e["message"] = error; return e;
        }
        return result;
    }
};

class CursorActionHandler : public EngineActionHandler {
    std::string name_;
public:
    explicit CursorActionHandler(const char* name) : name_(name) {}
    const char* action_name() const override { return name_.c_str(); }
    bool needs_design() const override { return false; }
    bool needs_waveform() const override { return true; }
    Json run(const Json& request) const override {
        std::string action = request.value("action", std::string());
        Json args = request.value("args", Json::object());
        std::string error;
        Json result = xdebug_waveform::ai_cursor_action(action, args, error);
        if (!error.empty()) {
            Json e; e["error"] = "ACTION_FAILED"; e["message"] = error; return e;
        }
        return result;
    }
};

// ═══════════════════════════════════════════════════════════════════════
// Not-yet-implemented action handlers (return NOT_IMPLEMENTED)
// ═══════════════════════════════════════════════════════════════════════

class NotImplementedHandler : public EngineActionHandler {
    std::string name_;
    bool nd_, nw_;
public:
    NotImplementedHandler(const char* name, bool needs_design, bool needs_waveform)
        : name_(name), nd_(needs_design), nw_(needs_waveform) {}
    const char* action_name() const override { return name_.c_str(); }
    bool needs_design() const override { return nd_; }
    bool needs_waveform() const override { return nw_; }
    Json run(const Json&) const override {
        Json e; e["error"] = "NOT_IMPLEMENTED";
        e["message"] = "action not yet implemented in unified engine: " + name_;
        return e;
    }
};

// Helper for registering NOT_IMPLEMENTED entries.
static void add_ni(EngineActionRegistry& r, const char* name,
                   bool nd, bool nw) {
    r.add(std::unique_ptr<EngineActionHandler>(
        new NotImplementedHandler(name, nd, nw)));
}

} // namespace

// ═══════════════════════════════════════════════════════════════════════
// Registry implementation
// ═══════════════════════════════════════════════════════════════════════

void EngineActionRegistry::add(std::unique_ptr<EngineActionHandler> handler) {
    if (!handler) return;
    handlers_[handler->action_name()] = std::move(handler);
}

const EngineActionHandler* EngineActionRegistry::find(const std::string& action) const {
    auto it = handlers_.find(action);
    return it != handlers_.end() ? it->second.get() : nullptr;
}

const EngineActionRegistry& engine_action_registry() {
    static EngineActionRegistry* reg = []() {
        auto* r = new EngineActionRegistry();

        // ── design actions ──
        r->add(std::unique_ptr<EngineActionHandler>(new TraceDriverHandler));
        r->add(std::unique_ptr<EngineActionHandler>(new TraceLoadHandler));
        r->add(std::unique_ptr<EngineActionHandler>(new SignalResolveHandler));
        r->add(std::unique_ptr<EngineActionHandler>(new PortTraceHandler));
        r->add(std::unique_ptr<EngineActionHandler>(new InstanceMapHandler));
        r->add(std::unique_ptr<EngineActionHandler>(new InterfaceResolveHandler));

        // Remaining design actions (not yet implemented natively)
        add_ni(*r, "trace.query",            true, false);
        add_ni(*r, "trace.expand",           true, false);
        add_ni(*r, "trace.graph",            true, false);
        add_ni(*r, "trace.path",             true, false);
        add_ni(*r, "trace.explain",          true, false);
        add_ni(*r, "signal.canonicalize",    true, false);
        add_ni(*r, "control.explain",        true, false);
        add_ni(*r, "source.context",         true, false);
        add_ni(*r, "expr.normalize",          true, false);
        add_ni(*r, "procedural.assignment",  true, false);
        add_ni(*r, "sequential.update",      true, false);
        add_ni(*r, "fsm.explain",            true, false);
        add_ni(*r, "counter.explain",        true, false);

        // ── waveform actions ──
        r->add(std::unique_ptr<EngineActionHandler>(new ValueAtHandler));
        r->add(std::unique_ptr<EngineActionHandler>(new ValueBatchAtHandler));
        r->add(std::unique_ptr<EngineActionHandler>(new ScopeListHandler));

        add_ni(*r, "list.create",            false, true);
        add_ni(*r, "list.add",               false, true);
        add_ni(*r, "list.delete",            false, true);
        add_ni(*r, "list.show",              false, true);
        add_ni(*r, "list.value_at",          false, true);
        add_ni(*r, "list.validate",          false, true);
        add_ni(*r, "list.diff",              false, true);
        add_ni(*r, "rc.generate",            false, true);
        add_ni(*r, "verify.conditions",      false, true);

        // Cursor actions
        r->add(std::unique_ptr<EngineActionHandler>(new CursorActionHandler("cursor.set")));
        r->add(std::unique_ptr<EngineActionHandler>(new CursorActionHandler("cursor.get")));
        r->add(std::unique_ptr<EngineActionHandler>(new CursorActionHandler("cursor.list")));
        r->add(std::unique_ptr<EngineActionHandler>(new CursorActionHandler("cursor.delete")));
        r->add(std::unique_ptr<EngineActionHandler>(new CursorActionHandler("cursor.use")));

        // ai_* actions (Json→Json, no text protocol)
        r->add(std::unique_ptr<EngineActionHandler>(new AiActionHandler("signal.changes",        false, true)));
        r->add(std::unique_ptr<EngineActionHandler>(new AiActionHandler("signal.stability",      false, true)));
        r->add(std::unique_ptr<EngineActionHandler>(new AiActionHandler("signal.trend",          false, true)));
        r->add(std::unique_ptr<EngineActionHandler>(new AiActionHandler("signal.statistics",     false, true)));
        r->add(std::unique_ptr<EngineActionHandler>(new AiActionHandler("expr.eval_at",          false, true)));
        r->add(std::unique_ptr<EngineActionHandler>(new AiActionHandler("window.verify",         false, true)));
        r->add(std::unique_ptr<EngineActionHandler>(new AiActionHandler("sampled_pulse.inspect", false, true)));
        r->add(std::unique_ptr<EngineActionHandler>(new AiActionHandler("inspect_signal",        false, true)));
        r->add(std::unique_ptr<EngineActionHandler>(new AiActionHandler("detect_anomaly",        false, true)));
        r->add(std::unique_ptr<EngineActionHandler>(new AiActionHandler("handshake.inspect",     false, true)));
        r->add(std::unique_ptr<EngineActionHandler>(new AiActionHandler("apb.transfer_window",   false, true)));
        r->add(std::unique_ptr<EngineActionHandler>(new AiActionHandler("axi.channel_stall",     false, true)));
        r->add(std::unique_ptr<EngineActionHandler>(new AiActionHandler("axi.outstanding_timeline", false, true)));
        r->add(std::unique_ptr<EngineActionHandler>(new AiActionHandler("axi.request_response_pair", false, true)));
        r->add(std::unique_ptr<EngineActionHandler>(new AiActionHandler("axi.latency_outlier",   false, true)));

        add_ni(*r, "apb.config.load",        false, true);
        add_ni(*r, "apb.config.list",        false, true);
        add_ni(*r, "apb.query",              false, true);
        add_ni(*r, "apb.cursor",             false, true);
        add_ni(*r, "axi.config.load",        false, true);
        add_ni(*r, "axi.config.list",        false, true);
        add_ni(*r, "axi.query",              false, true);
        add_ni(*r, "axi.cursor",             false, true);
        add_ni(*r, "axi.analysis",           false, true);
        // (axi.* analysis and apb.transfer_window handled by AiActionHandler above)

        add_ni(*r, "event.config.load",      false, true);
        add_ni(*r, "event.config.list",      false, true);
        add_ni(*r, "event.find",             false, true);
        add_ni(*r, "event.export",           false, true);

        // ── combined actions ──
        r->add(std::unique_ptr<EngineActionHandler>(new ActiveDriverHandler));
        r->add(std::unique_ptr<EngineActionHandler>(new ActiveDriverChainHandler));

        return r;
    }();
    return *reg;
}

} // namespace xdebug_design
