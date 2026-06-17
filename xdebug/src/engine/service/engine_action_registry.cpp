#include "engine_action_registry.h"

#include "../../design/trace/trace_engine.h"
#include "../../design/signal/signal_finder.h"
#include "../../design/port/port_analyzer.h"
#include "../../design/protocol/protocol.h"

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

#include "../../waveform/event/event_manager.h"
#include "../../waveform/event/event_analyzer.h"
#include "../../waveform/apb/apb_manager.h"
#include "../../waveform/apb/apb_analyzer.h"
#include "../../waveform/axi/axi_manager.h"
#include "../../waveform/axi/axi_analyzer.h"
#include "../../waveform/list/list_manager.h"
#include "../../waveform/list/signal_list.h"
#include "../../waveform/service/rc_generator.h"

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

} // namespace xdebug_design

// Waveform globals — at global scope to avoid nested-namespace issues.
namespace xdebug_waveform {
extern std::string g_session_id;
extern std::string g_fsdb_file_path;
extern npiFsdbFileHandle g_fsdb_file;
extern EventAnalyzer g_event_analyzer;
extern ApbAnalyzer g_apb_analyzer;
extern AxiAnalyzer g_axi_analyzer;
std::string format_time(npiFsdbTime t);
bool read_list_from_storage(const std::string& session_id,
                            const char* list_name, SignalList& out_list);
bool find_list_diff(npiFsdbFileHandle file,
                    const std::vector<std::string>& signals,
                    npiFsdbTime begin_time, npiFsdbTime end_time,
                    npiFsdbTime& diff_time);
bool read_sig_vec_value_at_with_status(npiFsdbFileHandle file,
    const std::vector<std::string>& signals, npiFsdbTime time, char fmt,
    std::vector<std::string>& out_values, std::vector<bool>& out_found);
}

namespace xdebug_design {
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

// verify.conditions — read signals at a time point, evaluate boolean conditions.
class VerifyConditionsHandler : public EngineActionHandler {
public:
    const char* action_name() const override { return "verify.conditions"; }
    bool needs_design() const override { return false; }
    bool needs_waveform() const override { return true; }
    Json run(const Json& request) const override {
        Json args = request.value("args", Json::object());
        Json conditions = args.value("conditions", Json::array());
        std::string time_str = args.value("time", args.value("at", ""));
        if (time_str.empty() || !conditions.is_array())
            return err("MISSING_FIELD", "args.conditions[] and args.time are required");

        npiFsdbTime fsdb_time = 0;
        double tv; std::string unit;
        char* end = nullptr;
        tv = std::strtod(time_str.c_str(), &end);
        if (!end || end == time_str.c_str()) return err("TIME_SPEC_INVALID", time_str);
        while (*end && std::isspace(*end)) ++end;
        unit = end;
        if (!npi_fsdb_convert_time_in(g_fsdb_file, tv, unit.c_str(), fsdb_time))
            return err("TIME_SPEC_INVALID", "failed to convert: " + time_str);

        Json results = Json::array();
        bool all_pass = true;
        for (auto& cond : conditions) {
            Json r;
            r["expr"] = cond.value("expr", "");
            r["op"] = cond.value("op", "");
            r["expected"] = cond.value("value", "");
            bool pass = false;
            std::string signal = cond.value("signal", "");
            if (!signal.empty()) {
                std::string raw;
                if (npi_fsdb_sig_value_at(g_fsdb_file, signal.c_str(), fsdb_time, raw, npiFsdbBinStrVal)) {
                    bool known = raw.find_first_of("xXzZ") == std::string::npos;
                    r["actual"] = raw;
                    r["known"] = known;
                    std::string exp_val = cond.value("value", "");
                    std::string op = cond.value("op", "==");
                    if (known) {
                        if (op == "==") pass = (raw == exp_val);
                        else if (op == "!=") pass = (raw != exp_val);
                    }
                } else {
                    r["actual"] = "NOT_FOUND"; r["known"] = false;
                }
            }
            r["pass"] = pass;
            if (!pass) all_pass = false;
            results.push_back(r);
        }
        Json out;
        out["time"] = time_str;
        out["all_pass"] = all_pass;
        out["results"] = results;
        return out;
    }
private:
    static Json err(const char* c, const std::string& m) {
        Json e; e["error"] = c; e["message"] = m; return e;
    }
};

// event.find / event.export — call EventManager + EventAnalyzer directly.
class EventHandler : public EngineActionHandler {
    bool export_mode_;
public:
    explicit EventHandler(bool export_mode) : export_mode_(export_mode) {}
    const char* action_name() const override { return export_mode_ ? "event.export" : "event.find"; }
    bool needs_design() const override { return false; }
    bool needs_waveform() const override { return true; }
    Json run(const Json& request) const override {
        using namespace xdebug_waveform;
        Json args = request.value("args", Json::object());
        std::string name = args.value("name", "");
        EventManager em;
        EventConfig config;
        if (!em.get_event(g_session_id, g_fsdb_file_path, name, config))
            return Json({{"error","CONFIG_NOT_FOUND"},{"message",name}});

        // Parse time range from standard TimeSpec fields
        npiFsdbTime tbegin = 0, tend = ~0ULL;
        Json time_range = args.value("time_range", Json::object());
        auto parse_t = [](const std::string& s, npiFsdbTime& t) {
            if (s.empty()) return;
            double v; std::string u; char* e = nullptr;
            v = std::strtod(s.c_str(), &e);
            if (!e || e == s.c_str()) return;
            while (*e && std::isspace(*e)) ++e; u = e;
            npi_fsdb_convert_time_in(g_fsdb_file, v, u.c_str(), t);
        };
        parse_t(time_range.value("start", time_range.value("begin", "")), tbegin);
        parse_t(time_range.value("end", ""), tend);

        EventQuery query;
        query.expr = args.value("expr", "");
        query.begin = tbegin;
        query.end = tend;
        int max_examples = export_mode_ ? args.value("max_examples", args.value("max_events", 1000)) : 1;
        query.limit = max_examples > 0 ? max_examples : 1000;

        std::vector<EventRecord> records;
        std::string error;
        if (!g_event_analyzer.analyze(g_fsdb_file, config, query, records, error))
            return Json({{"error","EVENT_FAILED"},{"message",error}});

        Json arr = Json::array();
        for (auto& rec : records) {
            Json je;
            je["time"] = format_time(rec.time);
            je["time_ps"] = rec.time;
            je["signals"] = rec.signals;
            je["fields"] = rec.fields;
            arr.push_back(je);
        }
        Json out;
        out["events"] = arr;
        out["count"] = static_cast<int>(arr.size());
        return out;
    }
};

// event.config.load / event.config.list — EventManager CRUD.
class EventConfigLoadHandler : public EngineActionHandler {
public:
    const char* action_name() const override { return "event.config.load"; }
    bool needs_design() const override { return false; }
    bool needs_waveform() const override { return true; }
    Json run(const Json& request) const override {
        using namespace xdebug_waveform;
        Json args = request.value("args", Json::object());
        std::string name = args.value("name", "");
        if (name.empty()) return Json({{"error","MISSING_FIELD"},{"message","args.name"}});
        // Config parsing requires the existing waveform helpers
        return Json({{"error","NOT_IMPLEMENTED"},{"message","event.config.load requires config parsing from waveform lib"}});
    }
};

class EventConfigListHandler : public EngineActionHandler {
public:
    const char* action_name() const override { return "event.config.list"; }
    bool needs_design() const override { return false; }
    bool needs_waveform() const override { return true; }
    Json run(const Json& request) const override {
        using namespace xdebug_waveform;
        Json args = request.value("args", Json::object());
        std::string name = args.value("name", "");
        EventManager em;
        if (name.empty()) {
            auto names = em.list_events(g_session_id, g_fsdb_file_path);
            Json arr = Json::array();
            for (size_t i = 0; i < names.size(); i++) arr.push_back(names[i]);
            return Json({{"count",static_cast<int>(arr.size())},{"events",arr}});
        }
        EventConfig cfg;
        if (!em.get_event(g_session_id, g_fsdb_file_path, name, cfg))
            return Json({{"error","CONFIG_NOT_FOUND"},{"message",name}});
        Json out; out["name"] = name;
        out["clk"] = cfg.clk; out["posedge"] = cfg.posedge;
        out["signals"] = cfg.signals;
        return out;
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

// ── list.* handlers ────────────────────────────────────────────────────

static bool read_list_storage(const std::string& name,
                               xdebug_waveform::SignalList& lst) {
    return xdebug_waveform::read_list_from_storage(
        xdebug_waveform::g_session_id, name.c_str(), lst);
}

class ListCreateHandler : public EngineActionHandler {
public:
    const char* action_name() const override { return "list.create"; }
    bool needs_design() const override { return false; }
    bool needs_waveform() const override { return true; }
    Json run(const Json& r) const override {
        Json a = r.value("args", Json::object());
        std::string n = a.value("name", "");
        if (n.empty()) return Json({{"error","MISSING_FIELD"},{"message","args.name"}});
        xdebug_waveform::ListManager lm;
        if (!lm.create_list(xdebug_waveform::g_session_id, n))
            return Json({{"error","CREATE_FAILED"},{"message",n}});
        Json out; out["name"] = n; out["created"] = true;
        // Optionally add initial signals
        Json sigs = a.value("signals", Json::array());
        for (auto& s : sigs) if (s.is_string())
            lm.add_signal(xdebug_waveform::g_session_id, n, s.get<std::string>());
        return out;
    }
};

class ListAddHandler : public EngineActionHandler {
public:
    const char* action_name() const override { return "list.add"; }
    bool needs_design() const override { return false; }
    bool needs_waveform() const override { return true; }
    Json run(const Json& r) const override {
        Json a = r.value("args", Json::object());
        std::string n = a.value("name", ""), sig = a.value("signal", "");
        if (n.empty() || sig.empty())
            return Json({{"error","MISSING_FIELD"},{"message","args.name+signal"}});
        xdebug_waveform::ListManager lm;
        if (!lm.add_signal(xdebug_waveform::g_session_id, n, sig))
            return Json({{"error","ADD_FAILED"},{"message",sig}});
        Json out; out["name"] = n; out["signal"] = sig; out["added"] = true; return out;
    }
};

class ListDeleteHandler : public EngineActionHandler {
public:
    const char* action_name() const override { return "list.delete"; }
    bool needs_design() const override { return false; }
    bool needs_waveform() const override { return true; }
    Json run(const Json& r) const override {
        Json a = r.value("args", Json::object());
        std::string n = a.value("name", "");
        if (n.empty()) return Json({{"error","MISSING_FIELD"},{"message","args.name"}});
        xdebug_waveform::ListManager lm;
        if (a.contains("signal")) {
            if (!lm.del_signal(xdebug_waveform::g_session_id, n, a["signal"].get<std::string>()))
                return Json({{"error","DEL_FAILED"}});
        } else {
            if (!lm.delete_list(xdebug_waveform::g_session_id, n))
                return Json({{"error","DEL_FAILED"}});
        }
        Json out; out["name"] = n; out["deleted"] = true; return out;
    }
};

class ListShowHandler : public EngineActionHandler {
public:
    const char* action_name() const override { return "list.show"; }
    bool needs_design() const override { return false; }
    bool needs_waveform() const override { return true; }
    Json run(const Json& r) const override {
        Json a = r.value("args", Json::object());
        std::string n = a.value("name", "");
        if (n.empty()) return Json({{"error","MISSING_FIELD"},{"message","args.name"}});
        xdebug_waveform::SignalList lst;
        if (!read_list_storage(n, lst))
            return Json({{"error","LIST_NOT_FOUND"},{"message",n}});
        Json out; out["name"] = n;
        Json arr = Json::array(); for (auto& s : lst.signals) arr.push_back(s);
        out["signals"] = arr; out["count"] = static_cast<int>(lst.signals.size());
        return out;
    }
};

class ListValueAtHandler : public EngineActionHandler {
public:
    const char* action_name() const override { return "list.value_at"; }
    bool needs_design() const override { return false; }
    bool needs_waveform() const override { return true; }
    Json run(const Json& r) const override {
        Json a = r.value("args", Json::object());
        std::string n = a.value("name", ""), ts = a.value("time", "");
        if (n.empty() || ts.empty())
            return Json({{"error","MISSING_FIELD"},{"message","args.name+time"}});
        xdebug_waveform::SignalList lst;
        if (!read_list_storage(n, lst))
            return Json({{"error","LIST_NOT_FOUND"},{"message",n}});
        double tv; std::string unit; char* e = nullptr;
        tv = std::strtod(ts.c_str(), &e);
        while (e && *e && std::isspace(*e)) ++e; unit = e;
        npiFsdbTime ft = 0;
        if (!unit.empty() && !npi_fsdb_convert_time_in(xdebug_waveform::g_fsdb_file, tv, unit.c_str(), ft))
            return Json({{"error","TIME_SPEC_INVALID"}});
        std::vector<std::string> vals; std::vector<bool> found;
        xdebug_waveform::read_sig_vec_value_at_with_status(
            xdebug_waveform::g_fsdb_file, lst.signals, ft, 'h', vals, found);
        Json out; out["name"] = n; out["time"] = ts;
        Json sv = Json::object();
        for (size_t i = 0; i < lst.signals.size(); i++)
            sv[lst.signals[i]] = found[i] ? vals[i] : "NOT_FOUND";
        out["values"] = sv;
        return out;
    }
};

class ListValidateHandler : public EngineActionHandler {
public:
    const char* action_name() const override { return "list.validate"; }
    bool needs_design() const override { return false; }
    bool needs_waveform() const override { return true; }
    Json run(const Json& r) const override {
        Json a = r.value("args", Json::object());
        std::string n = a.value("name", "");
        if (n.empty()) return Json({{"error","MISSING_FIELD"},{"message","args.name"}});
        xdebug_waveform::SignalList lst;
        if (!read_list_storage(n, lst))
            return Json({{"error","LIST_NOT_FOUND"},{"message",n}});
        Json arr = Json::array();
        for (auto& sig : lst.signals) {
            Json item; item["signal"] = sig;
            item["status"] = npi_fsdb_sig_by_name(xdebug_waveform::g_fsdb_file, sig.c_str(), NULL)
                ? "ok" : "not_found";
            arr.push_back(item);
        }
        Json out; out["name"] = n; out["signals"] = arr; return out;
    }
};

class ListDiffHandler : public EngineActionHandler {
public:
    const char* action_name() const override { return "list.diff"; }
    bool needs_design() const override { return false; }
    bool needs_waveform() const override { return true; }
    Json run(const Json& r) const override {
        Json a = r.value("args", Json::object());
        std::string n = a.value("name", ""), bs = a.value("begin", ""), es = a.value("end", "");
        if (n.empty() || bs.empty() || es.empty())
            return Json({{"error","MISSING_FIELD"},{"message","args.name+begin+end"}});
        xdebug_waveform::SignalList lst;
        if (!read_list_storage(n, lst))
            return Json({{"error","LIST_NOT_FOUND"},{"message",n}});
        auto ptime = [](const std::string& s, npiFsdbTime& t) -> bool {
            double v; std::string u; char* e = nullptr;
            v = std::strtod(s.c_str(), &e);
            while (e && *e && std::isspace(*e)) ++e; u = e;
            return !u.empty() && npi_fsdb_convert_time_in(xdebug_waveform::g_fsdb_file, v, u.c_str(), t);
        };
        npiFsdbTime bt = 0, et = 0;
        if (!ptime(bs, bt) || !ptime(es, et))
            return Json({{"error","TIME_SPEC_INVALID"}});
        npiFsdbTime dt = 0;
        bool found = xdebug_waveform::find_list_diff(
            xdebug_waveform::g_fsdb_file, lst.signals, bt, et, dt);
        Json out; out["name"] = n; out["diff_found"] = found;
        if (found) out["diff_time"] = dt;
        return out;
    }
};

// ── rc.generate ────────────────────────────────────────────────────────

class RcGenerateHandler : public EngineActionHandler {
public:
    const char* action_name() const override { return "rc.generate"; }
    bool needs_design() const override { return false; }
    bool needs_waveform() const override { return true; }
    Json run(const Json&) const override {
        return Json({{"error","NOT_IMPLEMENTED"},{"message","rc.generate pending"}});
    }
};

// ── apb.* / axi.* config handlers ──────────────────────────────────────

class ApbConfigLoadHandler : public EngineActionHandler {
public:
    const char* action_name() const override { return "apb.config.load"; }
    bool needs_design() const override { return false; }
    bool needs_waveform() const override { return true; }
    Json run(const Json&) const override {
        return Json({{"error","NOT_IMPLEMENTED"},{"message","apb.config.load pending config parsing"}});
    }
};

class ApbConfigListHandler : public EngineActionHandler {
public:
    const char* action_name() const override { return "apb.config.list"; }
    bool needs_design() const override { return false; }
    bool needs_waveform() const override { return true; }
    Json run(const Json& r) const override {
        Json a = r.value("args", Json::object());
        std::string name = a.value("name", "");
        xdebug_waveform::ApbManager am;
        if (name.empty()) { am.get_latest_apb(xdebug_waveform::g_session_id, name); }
        xdebug_waveform::ApbConfig cfg;
        if (name.empty() || !am.get_apb(xdebug_waveform::g_session_id, name, cfg))
            return Json({{"error","CONFIG_NOT_FOUND"}});
        Json out; out["name"] = name;
        out["clk"] = cfg.clk; out["rst_n"] = cfg.rst_n;
        return out;
    }
};

class ApbQueryHandler : public EngineActionHandler {
public:
    const char* action_name() const override { return "apb.query"; }
    bool needs_design() const override { return false; }
    bool needs_waveform() const override { return true; }
    Json run(const Json& r) const override {
        return Json({{"error","NOT_IMPLEMENTED"},{"message","apb.query pending"}});
    }
};

class ApbCursorHandler : public EngineActionHandler {
public:
    const char* action_name() const override { return "apb.cursor"; }
    bool needs_design() const override { return false; }
    bool needs_waveform() const override { return true; }
    Json run(const Json& r) const override {
        return Json({{"error","NOT_IMPLEMENTED"},{"message","apb.cursor pending"}});
    }
};

class AxiConfigLoadHandler : public EngineActionHandler {
public:
    const char* action_name() const override { return "axi.config.load"; }
    bool needs_design() const override { return false; }
    bool needs_waveform() const override { return true; }
    Json run(const Json&) const override {
        return Json({{"error","NOT_IMPLEMENTED"},{"message","axi.config.load pending config parsing"}});
    }
};

class AxiConfigListHandler : public EngineActionHandler {
public:
    const char* action_name() const override { return "axi.config.list"; }
    bool needs_design() const override { return false; }
    bool needs_waveform() const override { return true; }
    Json run(const Json& r) const override {
        Json a = r.value("args", Json::object());
        std::string name = a.value("name", "");
        xdebug_waveform::AxiManager am;
        if (name.empty()) { am.get_latest_axi(xdebug_waveform::g_session_id, name); }
        xdebug_waveform::AxiConfig cfg;
        if (name.empty() || !am.get_axi(xdebug_waveform::g_session_id, name, cfg))
            return Json({{"error","CONFIG_NOT_FOUND"}});
        Json out; out["name"] = name;
        out["clk"] = cfg.clk; out["rst_n"] = cfg.rst_n;
        return out;
    }
};

class AxiQueryHandler : public EngineActionHandler {
public:
    const char* action_name() const override { return "axi.query"; }
    bool needs_design() const override { return false; }
    bool needs_waveform() const override { return true; }
    Json run(const Json& r) const override {
        return Json({{"error","NOT_IMPLEMENTED"},{"message","axi.query pending"}});
    }
};

class AxiCursorHandler : public EngineActionHandler {
public:
    const char* action_name() const override { return "axi.cursor"; }
    bool needs_design() const override { return false; }
    bool needs_waveform() const override { return true; }
    Json run(const Json& r) const override {
        return Json({{"error","NOT_IMPLEMENTED"},{"message","axi.cursor pending"}});
    }
};

class AxiAnalysisHandler : public EngineActionHandler {
public:
    const char* action_name() const override { return "axi.analysis"; }
    bool needs_design() const override { return false; }
    bool needs_waveform() const override { return true; }
    Json run(const Json& r) const override {
        return Json({{"error","NOT_IMPLEMENTED"},{"message","axi.analysis pending"}});
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

        r->add(std::unique_ptr<EngineActionHandler>(new ListCreateHandler));
        r->add(std::unique_ptr<EngineActionHandler>(new ListAddHandler));
        r->add(std::unique_ptr<EngineActionHandler>(new ListDeleteHandler));
        r->add(std::unique_ptr<EngineActionHandler>(new ListShowHandler));
        r->add(std::unique_ptr<EngineActionHandler>(new ListValueAtHandler));
        r->add(std::unique_ptr<EngineActionHandler>(new ListValidateHandler));
        r->add(std::unique_ptr<EngineActionHandler>(new ListDiffHandler));
        r->add(std::unique_ptr<EngineActionHandler>(new RcGenerateHandler));
        r->add(std::unique_ptr<EngineActionHandler>(new VerifyConditionsHandler));

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

        r->add(std::unique_ptr<EngineActionHandler>(new ApbConfigLoadHandler));
        r->add(std::unique_ptr<EngineActionHandler>(new ApbConfigListHandler));
        r->add(std::unique_ptr<EngineActionHandler>(new ApbQueryHandler));
        r->add(std::unique_ptr<EngineActionHandler>(new ApbCursorHandler));
        r->add(std::unique_ptr<EngineActionHandler>(new AxiConfigLoadHandler));
        r->add(std::unique_ptr<EngineActionHandler>(new AxiConfigListHandler));
        r->add(std::unique_ptr<EngineActionHandler>(new AxiQueryHandler));
        r->add(std::unique_ptr<EngineActionHandler>(new AxiCursorHandler));
        r->add(std::unique_ptr<EngineActionHandler>(new AxiAnalysisHandler));
        // (axi.* analysis and apb.transfer_window handled by AiActionHandler above)

        r->add(std::unique_ptr<EngineActionHandler>(new EventConfigLoadHandler));
        r->add(std::unique_ptr<EngineActionHandler>(new EventConfigListHandler));
        r->add(std::unique_ptr<EngineActionHandler>(new EventHandler(false)));  // event.find
        r->add(std::unique_ptr<EngineActionHandler>(new EventHandler(true)));   // event.export

        // ── combined actions ──
        r->add(std::unique_ptr<EngineActionHandler>(new ActiveDriverHandler));
        r->add(std::unique_ptr<EngineActionHandler>(new ActiveDriverChainHandler));

        return r;
    }();
    return *reg;
}

} // namespace xdebug_design
