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

#include <fstream>

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

#include "design_postprocess.h"
#include "trace_bfs_engine.h"

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
        EventConfig config;

        // Two modes: named config (pre-loaded via event.config.load) or
        // inline config (clk + signals passed directly in args).
        if (!name.empty()) {
            EventManager em;
            if (!em.get_event(g_session_id, g_fsdb_file_path, name, config))
                return Json({{"error","CONFIG_NOT_FOUND"},{"message",name}});
        } else {
            // Inline mode: build config from args directly.
            std::string clk = args.value("clk", "");
            if (clk.empty())
                return Json({{"error","MISSING_FIELD"},{"message","args.clk is required for inline event config"}});
            config.clk = clk;
            config.rst_n = args.value("rst_n", "");
            config.posedge = args.value("edge", args.value("posedge", "posedge")) != "negedge";
            Json sigs = args.value("signals", Json::object());
            for (auto it = sigs.begin(); it != sigs.end(); ++it) {
                if (it->is_string()) config.signals[it.key()] = it->get<std::string>();
            }
            if (config.signals.empty())
                return Json({{"error","MISSING_FIELD"},{"message","args.signals is required for inline event config"}});
        }

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

// Forward declarations for helpers defined later in this file.
static bool load_config_from_args(const Json& args, nlohmann::json& cfg_j,
                                   std::string& err);
static bool ensure_apb_analyzed(const std::string& name,
                                 xdebug_waveform::ApbConfig& cfg,
                                 std::string& err);
static bool ensure_axi_analyzed(const std::string& name,
                                 xdebug_waveform::AxiConfig& cfg,
                                 std::string& err);

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

        nlohmann::json cfg_j; std::string err;
        if (!load_config_from_args(args, cfg_j, err))
            return Json({{"error","INVALID_REQUEST"},{"message",err}});

        // Validate required event fields
        if (!cfg_j.contains("clk") || !cfg_j["clk"].is_string() || cfg_j["clk"].get<std::string>().empty())
            return Json({{"error","INVALID_REQUEST"},{"message","missing or empty field: clk"}});
        if (!cfg_j.contains("signals") || !cfg_j["signals"].is_object())
            return Json({{"error","INVALID_REQUEST"},{"message","signals must be an object"}});

        EventConfig cfg;
        cfg.name = name;
        cfg.clk = cfg_j["clk"].get<std::string>();
        cfg.rst_n = cfg_j.value("rst_n", "");
        cfg.posedge = cfg_j.value("posedge", true);
        for (auto it = cfg_j["signals"].begin(); it != cfg_j["signals"].end(); ++it) {
            if (it->is_string()) cfg.signals[it.key()] = it->get<std::string>();
        }
        if (cfg_j.contains("fields") && cfg_j["fields"].is_object()) {
            for (auto it = cfg_j["fields"].begin(); it != cfg_j["fields"].end(); ++it) {
                EventField f;
                f.signal_alias = it->value("signal", "");
                f.left = it->value("left", 0);
                f.right = it->value("right", 0);
                cfg.fields[it.key()] = f;
            }
        }

        EventManager em;
        if (!em.create_event(g_session_id, g_fsdb_file_path, cfg))
            return Json({{"error","CREATE_FAILED"},{"message","failed to save event config"}});

        Json out;
        out["summary"] = {{"name", name}, {"status", "loaded"}};
        out["name"] = name; out["status"] = "loaded";
        Json cinfo; cinfo["name"] = name; cinfo["clk"] = cfg.clk;
        out["config"] = cinfo;
        return out;
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
    Json run(const Json& r) const override {
        Json a = r.value("args", Json::object());
        std::string config_path = a.value("config_path", "");
        std::string rc_path = a.value("rc_path", "");
        bool allow_invalid = a.value("allow_invalid", false);
        if (config_path.empty() || rc_path.empty())
            return Json({{"error","MISSING_FIELD"},{"message","args.config_path and args.rc_path required"}});

        // Read config file
        std::ifstream in(config_path);
        if (!in) return Json({{"error","CONFIG_NOT_FOUND"},{"message",config_path}});
        std::string content((std::istreambuf_iterator<char>(in)), std::istreambuf_iterator<char>());
        nlohmann::json doc;
        try { doc = nlohmann::json::parse(content); }
        catch (...) { return Json({{"error","INVALID_JSON"},{"message","failed to parse config file"}}); }

        xdebug_waveform::RcConfig cfg;
        std::string err;
        if (!xdebug_waveform::parse_rc_config_json(doc, cfg, err))
            return Json({{"error","PARSE_FAILED"},{"message",err}});

        // Validate signals exist in FSDB
        if (!allow_invalid) {
            auto refs = xdebug_waveform::collect_rc_signal_refs(cfg);
            for (auto& ref : refs) {
                if (ref.kind != "signal") continue;
                if (!npi_fsdb_sig_by_name(g_fsdb_file, ref.input_path.c_str(), NULL)) {
                    return Json({{"error","SIGNAL_NOT_FOUND"},
                        {"message","signal not in FSDB: " + ref.input_path}});
                }
            }
        }

        std::string rc_text = xdebug_waveform::render_signal_rc(cfg);
        if (!xdebug_waveform::write_text_file_creating_dirs(rc_path, rc_text, err))
            return Json({{"error","WRITE_FAILED"},{"message",err}});

        Json counts = Json::parse(xdebug_waveform::rc_config_counts(cfg).dump());
        Json out;
        out["summary"] = {{"written", true}, {"config_path", config_path},
            {"rc_path", rc_path}, {"valid", true}};
        if (counts.contains("group_count")) out["summary"]["group_count"] = counts["group_count"];
        if (counts.contains("signal_count")) out["summary"]["signal_count"] = counts["signal_count"];
        out["config_path"] = config_path;
        out["rc_path"] = rc_path;
        out["written"] = true;
        return out;
    }
};

// ── apb.* / axi.* query helpers ──────────────────────────────────────

static bool ensure_apb_analyzed(const std::string& name,
                                 xdebug_waveform::ApbConfig& cfg,
                                 std::string& err) {
    xdebug_waveform::ApbManager am;
    if (!am.get_apb(xdebug_waveform::g_session_id, name, cfg)) {
        err = "APB config not found: " + name;
        return false;
    }
    if (!xdebug_waveform::g_apb_analyzer.analyze(name,
            xdebug_waveform::g_fsdb_file, cfg)) {
        err = "Failed to analyze APB: " + name;
        return false;
    }
    return true;
}

static bool ensure_axi_analyzed(const std::string& name,
                                 xdebug_waveform::AxiConfig& cfg,
                                 std::string& err) {
    xdebug_waveform::AxiManager am;
    if (!am.get_axi(xdebug_waveform::g_session_id, name, cfg)) {
        err = "AXI config not found: " + name;
        return false;
    }
    if (!xdebug_waveform::g_axi_analyzer.analyze(name,
            xdebug_waveform::g_fsdb_file, cfg)) {
        err = "Failed to analyze AXI: " + name;
        return false;
    }
    return true;
}

// ── apb.* / axi.* config handlers ──────────────────────────────────────

// Helper: read config from args.config (inline) or args.config_path (file)
static bool load_config_from_args(const Json& args, nlohmann::json& cfg_j,
                                   std::string& err) {
    if (args.contains("config") && args["config"].is_object()) {
        cfg_j = nlohmann::json::parse(args["config"].dump());
        return true;
    }
    std::string cfg_path = args.value("config_path", "");
    if (!cfg_path.empty()) {
        std::ifstream in(cfg_path);
        if (!in) { err = "config file not found: " + cfg_path; return false; }
        std::string content((std::istreambuf_iterator<char>(in)),
                            std::istreambuf_iterator<char>());
        try { cfg_j = nlohmann::json::parse(content); }
        catch (...) { err = "invalid JSON in config file"; return false; }
        return true;
    }
    err = "args.config or args.config_path required";
    return false;
}

class ApbConfigLoadHandler : public EngineActionHandler {
public:
    const char* action_name() const override { return "apb.config.load"; }
    bool needs_design() const override { return false; }
    bool needs_waveform() const override { return true; }
    Json run(const Json& r) const override {
        using namespace xdebug_waveform;
        Json a = r.value("args", Json::object());
        std::string name = a.value("name", "");
        if (name.empty()) return Json({{"error","MISSING_FIELD"},{"message","args.name"}});

        nlohmann::json cfg_j; std::string err;
        if (!load_config_from_args(a, cfg_j, err))
            return Json({{"error","INVALID_REQUEST"},{"message",err}});

        // Validate required APB fields
        const char* reqs[] = {"clk","rst_n","paddr","psel","penable","pwrite","pwdata","prdata",nullptr};
        for (int i = 0; reqs[i]; ++i) {
            if (!cfg_j.contains(reqs[i]) || !cfg_j[reqs[i]].is_string() ||
                cfg_j[reqs[i]].get<std::string>().empty())
                return Json({{"error","INVALID_REQUEST"},
                    {"message",std::string("missing or empty field: ")+reqs[i]}});
        }

        ApbConfig cfg;
        cfg.name = name;
        cfg.clk = cfg_j["clk"].get<std::string>();
        cfg.rst_n = cfg_j["rst_n"].get<std::string>();
        cfg.paddr = cfg_j["paddr"].get<std::string>();
        cfg.psel = cfg_j["psel"].get<std::string>();
        cfg.penable = cfg_j["penable"].get<std::string>();
        cfg.pwrite = cfg_j["pwrite"].get<std::string>();
        cfg.pwdata = cfg_j["pwdata"].get<std::string>();
        cfg.prdata = cfg_j["prdata"].get<std::string>();
        if (cfg_j.contains("posedge")) cfg.posedge = cfg_j["posedge"].get<bool>();

        ApbManager am;
        if (!am.create_apb(g_session_id, cfg))
            return Json({{"error","CREATE_FAILED"},{"message","failed to save APB config"}});

        Json out;
        out["summary"] = {{"name", name}, {"status", "loaded"}};
        out["name"] = name;
        out["status"] = "loaded";
        Json cinfo; cinfo["name"] = name; cinfo["clk"] = cfg.clk; cinfo["rst_n"] = cfg.rst_n;
        out["config"] = cinfo;
        return out;
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
        using namespace xdebug_waveform;
        Json a = r.value("args", Json::object());
        std::string name = a.value("name", "");
        if (name.empty()) return Json({{"error","MISSING_FIELD"},{"message","args.name"}});

        ApbConfig cfg; std::string err;
        if (!ensure_apb_analyzed(name, cfg, err))
            return Json({{"error","ANALYZE_FAILED"},{"message",err}});

        std::string dir = a.value("direction", "wr");
        bool is_write = (dir != "rd");
        std::string addr_str = a.value("address", a.value("addr", ""));
        int num = a.value("num", -1);
        bool last = a.value("last", false);

        const ApbTransaction* txn = nullptr;
        bool found = false;
        if (!addr_str.empty()) {
            uint64_t addr = std::stoull(addr_str, nullptr, 0);
            if (num >= 0) {
                found = is_write ? g_apb_analyzer.get_write_by_addr_num(name, addr, (size_t)num, txn)
                                 : g_apb_analyzer.get_read_by_addr_num(name, addr, (size_t)num, txn);
            } else if (last) {
                found = is_write ? g_apb_analyzer.get_write_by_addr_last(name, addr, txn)
                                 : g_apb_analyzer.get_read_by_addr_last(name, addr, txn);
            } else {
                found = is_write ? g_apb_analyzer.get_write_by_addr(name, addr, txn)
                                 : g_apb_analyzer.get_read_by_addr(name, addr, txn);
            }
        } else if (num >= 0) {
            found = is_write ? g_apb_analyzer.get_write_by_num(name, (size_t)num, txn)
                             : g_apb_analyzer.get_read_by_num(name, (size_t)num, txn);
        } else if (last) {
            found = is_write ? g_apb_analyzer.get_write_last(name, txn)
                             : g_apb_analyzer.get_read_last(name, txn);
        } else {
            // No filter — return count
            size_t cnt = is_write ? g_apb_analyzer.get_write_count(name)
                                  : g_apb_analyzer.get_read_count(name);
            Json out;
            out["summary"] = {{"name",name},{"direction",dir},{"count",(int)cnt}};
            out["name"] = name; out["direction"] = dir; out["count"] = (int)cnt;
            return out;
        }

        Json out;
        out["summary"] = {{"name",name},{"direction",dir},{"found",found}};
        out["name"] = name; out["direction"] = dir; out["found"] = found;
        if (found && txn) {
            Json tj;
            tj["time"] = txn->time;
            tj["addr"] = txn->addr;
            tj["data"] = txn->data;
            tj["is_write"] = txn->is_write;
            out["transaction"] = tj;
            out["summary"]["addr"] = txn->addr;
        }
        return out;
    }
};

class ApbCursorHandler : public EngineActionHandler {
public:
    const char* action_name() const override { return "apb.cursor"; }
    bool needs_design() const override { return false; }
    bool needs_waveform() const override { return true; }
    Json run(const Json& r) const override {
        using namespace xdebug_waveform;
        Json a = r.value("args", Json::object());
        std::string name = a.value("name", "");
        std::string op = a.value("op", "begin");
        if (name.empty()) return Json({{"error","MISSING_FIELD"},{"message","args.name"}});

        ApbConfig cfg; std::string err;
        if (!ensure_apb_analyzed(name, cfg, err))
            return Json({{"error","ANALYZE_FAILED"},{"message",err}});

        std::string dir = a.value("direction", "all");
        int filter = (dir == "wr") ? 1 : (dir == "rd") ? 2 : 0;

        const ApbTransaction* txn = nullptr;
        bool ok = false;
        if (op == "begin") ok = g_apb_analyzer.cursor_begin(name, filter, txn);
        else if (op == "next") ok = g_apb_analyzer.cursor_next(name, filter, txn);
        else if (op == "prev" || op == "pre") ok = g_apb_analyzer.cursor_prev(name, filter, txn);
        else if (op == "last") ok = g_apb_analyzer.cursor_last(name, filter, txn);
        else return Json({{"error","INVALID_REQUEST"},{"message","op must be begin/next/prev/last"}});

        Json out;
        out["summary"] = {{"name",name},{"op",op},{"direction",dir},{"found",ok}};
        out["name"] = name; out["op"] = op; out["direction"] = dir; out["found"] = ok;
        if (ok && txn) {
            Json tj;
            tj["time"] = txn->time; tj["addr"] = txn->addr;
            tj["data"] = txn->data; tj["is_write"] = txn->is_write;
            out["transaction"] = tj;
            if (txn->is_write) out["summary"]["addr"] = txn->addr;
        }
        return out;
    }
};

class AxiConfigLoadHandler : public EngineActionHandler {
public:
    const char* action_name() const override { return "axi.config.load"; }
    bool needs_design() const override { return false; }
    bool needs_waveform() const override { return true; }
    Json run(const Json& r) const override {
        using namespace xdebug_waveform;
        Json a = r.value("args", Json::object());
        std::string name = a.value("name", "");
        if (name.empty()) return Json({{"error","MISSING_FIELD"},{"message","args.name"}});

        nlohmann::json cfg_j; std::string err;
        if (!load_config_from_args(a, cfg_j, err))
            return Json({{"error","INVALID_REQUEST"},{"message",err}});

        // Validate required AXI fields
        const char* reqs[] = {"clk","rst_n",
            "awvalid","awready","awaddr","awid","awlen","awsize","awburst",
            "wvalid","wready","wdata","wstrb","wlast",
            "bvalid","bready","bid","bresp",
            "arvalid","arready","araddr","arid","arlen","arsize","arburst",
            "rvalid","rready","rdata","rid","rresp","rlast",nullptr};
        for (int i = 0; reqs[i]; ++i) {
            if (!cfg_j.contains(reqs[i]) || !cfg_j[reqs[i]].is_string() ||
                cfg_j[reqs[i]].get<std::string>().empty())
                return Json({{"error","INVALID_REQUEST"},
                    {"message",std::string("missing or empty field: ")+reqs[i]}});
        }

        AxiConfig cfg; cfg.name = name;
        cfg.clk = cfg_j["clk"].get<std::string>();
        cfg.rst_n = cfg_j["rst_n"].get<std::string>();
        cfg.awvalid=cfg_j["awvalid"]; cfg.awready=cfg_j["awready"];
        cfg.awaddr=cfg_j["awaddr"]; cfg.awid=cfg_j["awid"];
        cfg.awlen=cfg_j["awlen"]; cfg.awsize=cfg_j["awsize"]; cfg.awburst=cfg_j["awburst"];
        cfg.wvalid=cfg_j["wvalid"]; cfg.wready=cfg_j["wready"];
        cfg.wdata=cfg_j["wdata"]; cfg.wstrb=cfg_j["wstrb"]; cfg.wlast=cfg_j["wlast"];
        cfg.bvalid=cfg_j["bvalid"]; cfg.bready=cfg_j["bready"];
        cfg.bid=cfg_j["bid"]; cfg.bresp=cfg_j["bresp"];
        cfg.arvalid=cfg_j["arvalid"]; cfg.arready=cfg_j["arready"];
        cfg.araddr=cfg_j["araddr"]; cfg.arid=cfg_j["arid"];
        cfg.arlen=cfg_j["arlen"]; cfg.arsize=cfg_j["arsize"]; cfg.arburst=cfg_j["arburst"];
        cfg.rvalid=cfg_j["rvalid"]; cfg.rready=cfg_j["rready"];
        cfg.rdata=cfg_j["rdata"]; cfg.rid=cfg_j["rid"];
        cfg.rresp=cfg_j["rresp"]; cfg.rlast=cfg_j["rlast"];
        if (cfg_j.contains("posedge")) cfg.posedge = cfg_j["posedge"].get<bool>();

        AxiManager am;
        if (!am.create_axi(g_session_id, cfg))
            return Json({{"error","CREATE_FAILED"},{"message","failed to save AXI config"}});

        Json out;
        out["summary"] = {{"name", name}, {"status", "loaded"}};
        out["name"] = name; out["status"] = "loaded";
        Json cinfo; cinfo["name"] = name; cinfo["clk"] = cfg.clk; cinfo["rst_n"] = cfg.rst_n;
        out["config"] = cinfo;
        return out;
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
        using namespace xdebug_waveform;
        Json a = r.value("args", Json::object());
        std::string name = a.value("name", "");
        if (name.empty()) return Json({{"error","MISSING_FIELD"},{"message","args.name"}});

        AxiConfig cfg; std::string err;
        if (!ensure_axi_analyzed(name, cfg, err))
            return Json({{"error","ANALYZE_FAILED"},{"message",err}});

        std::string dir = a.value("direction", "wr");
        bool is_write = (dir != "rd");
        std::string addr_str = a.value("address", a.value("addr", ""));
        std::string id_str = a.value("id", "");
        int num = a.value("num", -1);
        bool last = a.value("last", false);

        const AxiTransaction* txn = nullptr;
        bool found = false;
        if (!addr_str.empty()) {
            uint64_t addr = std::stoull(addr_str, nullptr, 0);
            if (!id_str.empty()) {
                if (num >= 0)
                    found = is_write ? g_axi_analyzer.get_write_by_addr_num(name, addr, id_str.c_str(), (size_t)num, txn)
                                     : g_axi_analyzer.get_read_by_addr_num(name, addr, id_str.c_str(), (size_t)num, txn);
                else if (last)
                    found = is_write ? g_axi_analyzer.get_write_by_addr_last(name, addr, id_str.c_str(), txn)
                                     : g_axi_analyzer.get_read_by_addr_last(name, addr, id_str.c_str(), txn);
                else
                    found = is_write ? g_axi_analyzer.get_write_by_addr(name, addr, id_str.c_str(), txn)
                                     : g_axi_analyzer.get_read_by_addr(name, addr, id_str.c_str(), txn);
            } else {
                if (num >= 0)
                    found = is_write ? g_axi_analyzer.get_write_by_addr_num(name, addr, (size_t)num, txn)
                                     : g_axi_analyzer.get_read_by_addr_num(name, addr, (size_t)num, txn);
                else if (last)
                    found = is_write ? g_axi_analyzer.get_write_by_addr_last(name, addr, txn)
                                     : g_axi_analyzer.get_read_by_addr_last(name, addr, txn);
                else
                    found = is_write ? g_axi_analyzer.get_write_by_addr(name, addr, txn)
                                     : g_axi_analyzer.get_read_by_addr(name, addr, txn);
            }
        } else if (!id_str.empty()) {
            if (num >= 0)
                found = is_write ? g_axi_analyzer.get_write_by_num(name, id_str.c_str(), (size_t)num, txn)
                                 : g_axi_analyzer.get_read_by_num(name, id_str.c_str(), (size_t)num, txn);
            else if (last)
                found = is_write ? g_axi_analyzer.get_write_last(name, id_str.c_str(), txn)
                                 : g_axi_analyzer.get_read_last(name, id_str.c_str(), txn);
        } else if (num >= 0) {
            found = is_write ? g_axi_analyzer.get_write_by_num(name, (size_t)num, txn)
                             : g_axi_analyzer.get_read_by_num(name, (size_t)num, txn);
        } else if (last) {
            found = is_write ? g_axi_analyzer.get_write_last(name, txn)
                             : g_axi_analyzer.get_read_last(name, txn);
        } else {
            size_t cnt = is_write ? g_axi_analyzer.get_write_count(name)
                                  : g_axi_analyzer.get_read_count(name);
            Json out;
            out["summary"] = {{"name",name},{"direction",dir},{"count",(int)cnt}};
            out["name"] = name; out["direction"] = dir; out["count"] = (int)cnt;
            return out;
        }

        Json out;
        out["summary"] = {{"name",name},{"direction",dir},{"found",found}};
        out["name"] = name; out["direction"] = dir; out["found"] = found;
        if (found && txn) {
            Json tj;
            tj["time"] = txn->addr_time;
            tj["addr"] = txn->addr; tj["id"] = txn->id;
            tj["len"] = txn->len; tj["size"] = txn->size;
            tj["burst"] = txn->burst; tj["is_write"] = txn->is_write;
            if (!txn->data.empty()) { Json da = Json::array(); for (auto& d : txn->data) da.push_back(d); tj["data"] = da; }
            out["transaction"] = tj;
            out["summary"]["addr"] = txn->addr;
        }
        return out;
    }
};

class AxiCursorHandler : public EngineActionHandler {
public:
    const char* action_name() const override { return "axi.cursor"; }
    bool needs_design() const override { return false; }
    bool needs_waveform() const override { return true; }
    Json run(const Json& r) const override {
        using namespace xdebug_waveform;
        Json a = r.value("args", Json::object());
        std::string name = a.value("name", "");
        std::string op = a.value("op", "begin");
        if (name.empty()) return Json({{"error","MISSING_FIELD"},{"message","args.name"}});

        AxiConfig cfg; std::string err;
        if (!ensure_axi_analyzed(name, cfg, err))
            return Json({{"error","ANALYZE_FAILED"},{"message",err}});

        std::string dir = a.value("direction", "all");
        int filter = (dir == "wr") ? 1 : (dir == "rd") ? 2 : 0;

        const AxiTransaction* txn = nullptr;
        bool ok = false;
        if (op == "begin") ok = g_axi_analyzer.cursor_begin(name, filter, txn);
        else if (op == "next") ok = g_axi_analyzer.cursor_next(name, filter, txn);
        else if (op == "prev" || op == "pre") ok = g_axi_analyzer.cursor_prev(name, filter, txn);
        else if (op == "last") ok = g_axi_analyzer.cursor_last(name, filter, txn);
        else return Json({{"error","INVALID_REQUEST"},{"message","op must be begin/next/prev/last"}});

        Json out;
        out["summary"] = {{"name",name},{"op",op},{"direction",dir},{"found",ok}};
        out["name"] = name; out["op"] = op; out["direction"] = dir; out["found"] = ok;
        if (ok && txn) {
            Json tj;
            tj["time"] = txn->addr_time; tj["addr"] = txn->addr; tj["id"] = txn->id;
            tj["len"] = txn->len; tj["is_write"] = txn->is_write;
            out["transaction"] = tj;
            if (txn->is_write) out["summary"]["addr"] = txn->addr;
        }
        return out;
    }
};

class AxiAnalysisHandler : public EngineActionHandler {
public:
    const char* action_name() const override { return "axi.analysis"; }
    bool needs_design() const override { return false; }
    bool needs_waveform() const override { return true; }
    Json run(const Json& r) const override {
        using namespace xdebug_waveform;
        Json a = r.value("args", Json::object());
        std::string name = a.value("name", "");
        if (name.empty()) return Json({{"error","MISSING_FIELD"},{"message","args.name"}});

        AxiConfig cfg; std::string err;
        if (!ensure_axi_analyzed(name, cfg, err))
            return Json({{"error","ANALYZE_FAILED"},{"message",err}});

        std::string analysis = a.value("analysis", "latency");
        std::string dir = a.value("direction", "all");
        int filter = (dir == "wr") ? 1 : (dir == "rd") ? 2 : 0;
        std::string id_str = a.value("id", "");

        Json out;
        if (analysis == "osd" || analysis == "outstanding") {
            AxiStatResult stat;
            if (!g_axi_analyzer.get_outstanding_stats(name, filter,
                    id_str.empty() ? nullptr : id_str.c_str(), stat))
                return Json({{"error","ANALYSIS_FAILED"},{"message","outstanding analysis failed"}});
            out["summary"] = {{"name",name},{"analysis","osd"},{"max",stat.max},
                {"min",stat.min},{"avg",stat.avg},{"samples",(int)stat.samples}};
            out["analysis"] = "osd";
            out["max"] = stat.max; out["min"] = stat.min; out["avg"] = stat.avg;
            out["samples"] = (int)stat.samples;
        } else {
            AxiStatResult stat;
            if (!g_axi_analyzer.get_latency_stats(name, filter,
                    id_str.empty() ? nullptr : id_str.c_str(), stat))
                return Json({{"error","ANALYSIS_FAILED"},{"message","latency analysis failed"}});
            out["summary"] = {{"name",name},{"analysis","latency"},{"max",stat.max},
                {"min",stat.min},{"avg",stat.avg},{"samples",(int)stat.samples}};
            out["analysis"] = "latency";
            out["max"] = stat.max; out["min"] = stat.min; out["avg"] = stat.avg;
            out["samples"] = (int)stat.samples;
        }
        out["name"] = name;
        return out;
    }
};

// ═══════════════════════════════════════════════════════════════════════
// Design action handlers (native TraceEngine, no socket)
// ═══════════════════════════════════════════════════════════════════════

// Helper: run TraceEngine for one signal, return parsed nlohmann::json.
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

class TraceQueryHandler : public EngineActionHandler {
public:
    const char* action_name() const override { return "trace.query"; }
    bool needs_design() const override { return true; }
    bool needs_waveform() const override { return false; }
    Json run(const Json& request) const override {
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
    Json run(const Json& request) const override {
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
        bool compact = request.value("output", Json::object()).value("verbosity", "") == "compact";
        if (compact && !args.value("include_debug", false)) {
            out["summary"] = {{"root_signal",root},{"direction",direction},
                {"node_count",graph["nodes"].size()},{"edge_count",graph["edges"].size()},
                {"truncated",bfs.truncated}};
        } else {
            out["summary"] = {{"root_signal",root},{"direction",direction},
                {"depth",bfs.reached_depth},{"node_count",graph["nodes"].size()},
                {"edge_count",graph["edges"].size()},{"raw_edge_count",bfs.raw_edge_count},
                {"deduped_edge_count",bfs.all_edges.size()},
                {"duplicate_edge_count",bfs.duplicate_edge_count},
                {"relation_group_count",rel_edges.size()},
                {"aggregated_edge_count",agg_count},
                {"failed_query_count",bfs.failed_query_count},
                {"truncated",bfs.truncated}};
        }
        out["truncated"] = bfs.truncated;
        out["data"] = Json::parse(graph.dump());
        return out;
    }
};

class TraceGraphHandler : public EngineActionHandler {
public:
    const char* action_name() const override { return "trace.graph"; }
    bool needs_design() const override { return true; }
    bool needs_waveform() const override { return false; }
    Json run(const Json& request) const override {
        // trace.graph is an alias for trace.expand
        TraceExpandHandler h;
        return h.run(request);
    }
};

class TraceExplainHandler : public EngineActionHandler {
public:
    const char* action_name() const override { return "trace.explain"; }
    bool needs_design() const override { return true; }
    bool needs_waveform() const override { return false; }
    Json run(const Json& request) const override {
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

        Json out;
        out["summary"] = {{"root_signal",root},{"direction",direction},
            {"explanation_count",explanations.size()},
            {"edge_count",rel_edges.size()},{"skipped_empty_dependency_count",skipped},
            {"truncated",bfs.truncated}};
        out["truncated"] = bfs.truncated;
        out["data"] = Json::parse(explanations.dump());
        return out;
    }
};

class TracePathHandler : public EngineActionHandler {
public:
    const char* action_name() const override { return "trace.path"; }
    bool needs_design() const override { return true; }
    bool needs_waveform() const override { return false; }
    Json run(const Json& request) const override {
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
        out["summary"] = {{"from_signal",from_sig},{"to_signal",to_sig},
            {"found",found},{"path_count",paths.size()},{"truncated",bfs.truncated}};
        out["truncated"] = bfs.truncated;
        out["found"] = found;
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
    Json run(const Json& request) const override {
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
        out["data"] = Json::parse(nlohmann::json{{"control_dependencies", deps}}.dump());
        return out;
    }
};

class ExprNormalizeHandler : public EngineActionHandler {
public:
    const char* action_name() const override { return "expr.normalize"; }
    bool needs_design() const override { return true; }
    bool needs_waveform() const override { return false; }
    Json run(const Json& request) const override {
        Json args = request.value("args", Json::object());
        std::string signal = args.value("signal", "");

        Json out;
        if (!signal.empty()) {
            TraceOptions opts = parse_trace_opts(args);
            nlohmann::json trace = trace_one_signal(signal, TraceMode::Driver, opts);
            nlohmann::json assignment = trace.value("assignment", nlohmann::json::object());
            out["summary"] = {{"signal",signal},{"source","npi_trace_assignment"},
                {"confidence",trace.value("confidence","unknown")}};
            out["data"] = Json::parse(nlohmann::json{
                {"expr", assignment.value("rhs", nlohmann::json::object())},
                {"assignment", assignment},
                {"rhs_signals", assignment.value("rhs_signals", nlohmann::json::array())},
                {"confidence", trace.value("confidence", "unknown")}
            }.dump());
            return out;
        }
        std::string expr = args.value("expr", "");
        if (expr.empty()) return Json({{"error","MISSING_FIELD"},{"message","args.expr or args.signal"}});
        out["summary"] = {{"expr",expr},{"source","string_fallback"},{"confidence","low"}};
        out["data"] = Json::parse(nlohmann::json{
            {"expr", nlohmann::json::parse(parse_expr_ast(expr).dump())},
            {"confidence", "low"},
            {"confidence_reason", "parsed from raw string without NPI handle"}
        }.dump());
        return out;
    }
};

class ProceduralAssignmentHandler : public EngineActionHandler {
public:
    const char* action_name() const override { return "procedural.assignment"; }
    bool needs_design() const override { return true; }
    bool needs_waveform() const override { return false; }
    Json run(const Json& request) const override {
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
        out["summary"] = {{"signal",signal},{"assignment_count",assignments.size()},
            {"branch_count",branches.size()},{"default_count",defaults.size()},
            {"confidence",trace.value("confidence","unknown")}};
        out["data"] = Json::parse(nlohmann::json{
            {"procedural_assignment", {{"target",signal},{"enclosing_block",enclosing},
                {"assignments",assignments},{"default_assignments",defaults},
                {"branch_assignments",branches},
                {"control_dependencies",trace.value("control_dependencies",nlohmann::json::array())},
                {"dependency_edges",trace.value("dependency_edges",nlohmann::json::array())},
                {"confidence",trace.value("confidence","unknown")},
                {"confidence_reason",trace.value("confidence_reason","")}}}
        }.dump());
        return out;
    }
};

class SequentialUpdateHandler : public EngineActionHandler {
public:
    const char* action_name() const override { return "sequential.update"; }
    bool needs_design() const override { return true; }
    bool needs_waveform() const override { return false; }
    Json run(const Json& request) const override {
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
        out["data"] = Json::parse(nlohmann::json{
            {"sequential_update", {{"target",signal},
                {"clock", timing["clock"]}, {"reset", timing["reset"]},
                {"event_controls", timing["event_controls"]},
                {"rules", rules}, {"confidence", trace.value("confidence","unknown")},
                {"confidence_reason", trace.value("confidence_reason","")}}}
        }.dump());
        return out;
    }
};

class FsmExplainHandler : public EngineActionHandler {
public:
    const char* action_name() const override { return "fsm.explain"; }
    bool needs_design() const override { return true; }
    bool needs_waveform() const override { return false; }
    Json run(const Json& request) const override {
        // Reuse SequentialUpdateHandler logic
        SequentialUpdateHandler seq_handler;
        Json seq_resp = seq_handler.run(request);
        if (seq_resp.contains("error")) return seq_resp;

        Json args = request.value("args", Json::object());
        std::string signal = args.value("signal", "");
        nlohmann::json seq_data = nlohmann::json::parse(seq_resp["data"].dump());
        nlohmann::json seq = seq_data.value("sequential_update", nlohmann::json::object());

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
        out["data"] = Json::parse(nlohmann::json{
            {"fsm", {{"state_signal",signal},{"clock",seq["clock"]},
                {"reset",seq["reset"]},{"transitions",transitions},
                {"rules",seq["rules"]},{"confidence",seq.value("confidence","unknown")},
                {"confidence_reason",seq.value("confidence_reason","")}}}
        }.dump());
        return out;
    }
};

class CounterExplainHandler : public EngineActionHandler {
public:
    const char* action_name() const override { return "counter.explain"; }
    bool needs_design() const override { return true; }
    bool needs_waveform() const override { return false; }
    Json run(const Json& request) const override {
        SequentialUpdateHandler seq_handler;
        Json seq_resp = seq_handler.run(request);
        if (seq_resp.contains("error")) return seq_resp;

        Json args = request.value("args", Json::object());
        std::string signal = args.value("signal", "");
        nlohmann::json seq_data = nlohmann::json::parse(seq_resp["data"].dump());
        nlohmann::json seq = seq_data.value("sequential_update", nlohmann::json::object());

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
        out["data"] = Json::parse(nlohmann::json{
            {"counter", {{"signal",signal},{"clock",seq["clock"]},
                {"reset",seq["reset"]},{"rules",counter_rules},
                {"counter_like",is_counter_like},{"confidence",conf},
                {"confidence_reason", is_counter_like
                    ? "increment/decrement rule was identified from next-value expression"
                    : "sequential rules were found but no increment/decrement pattern was proven"}}}
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
    Json run(const Json& request) const override {
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
        out["data"] = Json::parse(nlohmann::json{
            {"file",file},{"line",line},
            {"symbol", args.value("symbol", "")},
            {"context_kind", enclosing.value("type", "unknown")},
            {"enclosing", enclosing}
        }.dump());
        if (!compact || include_src) {
            nlohmann::json ctx = nlohmann::json::array();
            for (int i = begin; i <= end; ++i)
                ctx.push_back({{"line",i},{"text",lines[i-1]},{"hit",i == line}});
            out["data"]["context"] = Json::parse(ctx.dump());
        }
        return out;
    }
};

class SignalCanonicalizeHandler : public EngineActionHandler {
public:
    const char* action_name() const override { return "signal.canonicalize"; }
    bool needs_design() const override { return true; }
    bool needs_waveform() const override { return false; }
    Json run(const Json& request) const override {
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
        out["data"] = Json::parse(nlohmann::json{
            {"query",query},{"canonical",canonical},{"rtl_path",rtl_path},
            {"leaf",leaf},{"scope",scope},{"base_signal",base_signal},
            {"select",select},{"ambiguous",ambiguous},{"aliases",aliases},
            {"fsdb_candidates",fsdb_candidates},{"port_mappings",port_mappings}
        }.dump());
        return out;
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

        // Remaining design actions (native, no socket)
        r->add(std::unique_ptr<EngineActionHandler>(new TraceQueryHandler));
        r->add(std::unique_ptr<EngineActionHandler>(new TraceExpandHandler));
        r->add(std::unique_ptr<EngineActionHandler>(new TraceGraphHandler));
        r->add(std::unique_ptr<EngineActionHandler>(new TracePathHandler));
        r->add(std::unique_ptr<EngineActionHandler>(new TraceExplainHandler));
        r->add(std::unique_ptr<EngineActionHandler>(new SignalCanonicalizeHandler));
        r->add(std::unique_ptr<EngineActionHandler>(new ControlExplainHandler));
        r->add(std::unique_ptr<EngineActionHandler>(new SourceContextHandler));
        r->add(std::unique_ptr<EngineActionHandler>(new ExprNormalizeHandler));
        r->add(std::unique_ptr<EngineActionHandler>(new ProceduralAssignmentHandler));
        r->add(std::unique_ptr<EngineActionHandler>(new SequentialUpdateHandler));
        r->add(std::unique_ptr<EngineActionHandler>(new FsmExplainHandler));
        r->add(std::unique_ptr<EngineActionHandler>(new CounterExplainHandler));

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
