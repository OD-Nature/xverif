#include "engine_action_handler.h"
#include "engine_action_registry.h"
#include "engine_globals.h"

#include "../../api/text_response_builder.h"
#include "../../design/protocol/protocol.h"
#include "../../waveform/server/fsdb_value_reader.h"
#include "../../waveform/event/event_manager.h"
#include "../../waveform/event/event_analyzer.h"
#include "../../waveform/list/list_manager.h"
#include "../../waveform/list/signal_list.h"
#include "../../waveform/service/rc_generator.h"

#include "npi.h"
#include "npi_fsdb.h"
#include "npi_L1.h"

#include <fstream>
#include <memory>

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
    std::string render_xout(const Json& r) const override {
        xdebug::TextResponseBuilder out("xdebug");
        out.emit_header(action_name());
        const Json& d = r.value("data", Json::object());
        out.emit_section("target");
        if (d.contains("signal")) out.emit_kv("signal", d["signal"]);
        if (d.contains("time")) out.emit_kv("time", d["time"]);
        out.emit_section("summary");
        if (d.contains("value")) out.emit_kv("value", d["value"]);
        if (d.contains("known")) out.emit_kv("known", d["known"]);
        if (d.contains("width")) out.emit_kv("width", d["width"]);
        return out.str();
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
    std::string render_xout(const Json& r) const override {
        xdebug::TextResponseBuilder out("xdebug");
        out.emit_header(action_name());
        const Json& d = r.value("data", Json::object());
        const Json& s = r.value("summary", Json::object());
        out.emit_section("target");
        if (s.contains("time")) out.emit_kv("time", s["time"]);
        if (s.contains("signal_count")) out.emit_kv("signal_count", s["signal_count"]);
        out.emit_section("values");
        if (d.contains("signals") && d["signals"].is_object()) {
            for (auto it = d["signals"].begin(); it != d["signals"].end(); ++it)
                out.emit_row({it.key(), xdebug::json_to_xout_value(it.value()["value"])});
        }
        return out.str();
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

        if (!name.empty()) {
            EventManager em;
            if (!em.get_event(g_session_id, g_fsdb_file_path, name, config))
                return Json({{"error","CONFIG_NOT_FOUND"},{"message",name}});
        } else {
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
        out["examples"] = arr;
        out["count"] = static_cast<int>(arr.size());
        out["event_count"] = out["count"];
        if (!arr.empty()) {
            out["first"] = arr[0]["time"];
            out["last"] = arr[arr.size()-1]["time"];
        }
        out["begin"] = time_range.value("start", time_range.value("begin", ""));
        out["end"] = time_range.value("end", "");
        out["mode"] = args.value("mode", export_mode_ ? "export" : "first");
        out["sampling_mode"] = "clock_edge";
        out["inline"] = name.empty();
        out["summary"] = {
            {"event_count", out["event_count"]},
            {"first", out.value("first", Json())},
            {"last", out.value("last", Json())},
            {"count", out["count"]}
        };
        return out;
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
        // Fix statistics end time: ai functions may return FSDB max time
        // instead of the requested window end.
        Json args = request.value("args", Json::object());
        if (args.contains("time_range") && args["time_range"].is_object() &&
            args["time_range"].contains("end")) {
            std::string req_end = args["time_range"]["end"].get<std::string>();
            if (!req_end.empty() && result.contains("end") &&
                result["end"].is_string() && result["end"] != req_end) {
                result["end"] = req_end;
            }
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


}  // namespace

void register_waveform_handlers(EngineActionRegistry& r) {
    r.add(std::unique_ptr<EngineActionHandler>(new ValueAtHandler));
    r.add(std::unique_ptr<EngineActionHandler>(new ValueBatchAtHandler));
    r.add(std::unique_ptr<EngineActionHandler>(new ScopeListHandler));
    r.add(std::unique_ptr<EngineActionHandler>(new ListCreateHandler));
    r.add(std::unique_ptr<EngineActionHandler>(new ListAddHandler));
    r.add(std::unique_ptr<EngineActionHandler>(new ListDeleteHandler));
    r.add(std::unique_ptr<EngineActionHandler>(new ListShowHandler));
    r.add(std::unique_ptr<EngineActionHandler>(new ListValueAtHandler));
    r.add(std::unique_ptr<EngineActionHandler>(new ListValidateHandler));
    r.add(std::unique_ptr<EngineActionHandler>(new ListDiffHandler));
    r.add(std::unique_ptr<EngineActionHandler>(new RcGenerateHandler));
    r.add(std::unique_ptr<EngineActionHandler>(new VerifyConditionsHandler));
    // Cursor actions
    r.add(std::unique_ptr<EngineActionHandler>(new CursorActionHandler("cursor.set")));
    r.add(std::unique_ptr<EngineActionHandler>(new CursorActionHandler("cursor.get")));
    r.add(std::unique_ptr<EngineActionHandler>(new CursorActionHandler("cursor.list")));
    r.add(std::unique_ptr<EngineActionHandler>(new CursorActionHandler("cursor.delete")));
    r.add(std::unique_ptr<EngineActionHandler>(new CursorActionHandler("cursor.use")));
    // ai_* actions
    r.add(std::unique_ptr<EngineActionHandler>(new AiActionHandler("signal.changes",        false, true)));
    r.add(std::unique_ptr<EngineActionHandler>(new AiActionHandler("signal.stability",      false, true)));
    r.add(std::unique_ptr<EngineActionHandler>(new AiActionHandler("signal.trend",          false, true)));
    r.add(std::unique_ptr<EngineActionHandler>(new AiActionHandler("signal.statistics",     false, true)));
    r.add(std::unique_ptr<EngineActionHandler>(new AiActionHandler("expr.eval_at",          false, true)));
    r.add(std::unique_ptr<EngineActionHandler>(new AiActionHandler("window.verify",         false, true)));
    r.add(std::unique_ptr<EngineActionHandler>(new AiActionHandler("sampled_pulse.inspect", false, true)));
    r.add(std::unique_ptr<EngineActionHandler>(new AiActionHandler("inspect_signal",        false, true)));
    r.add(std::unique_ptr<EngineActionHandler>(new AiActionHandler("detect_anomaly",        false, true)));
    r.add(std::unique_ptr<EngineActionHandler>(new AiActionHandler("handshake.inspect",     false, true)));
    r.add(std::unique_ptr<EngineActionHandler>(new AiActionHandler("apb.transfer_window",   false, true)));
    r.add(std::unique_ptr<EngineActionHandler>(new AiActionHandler("axi.channel_stall",     false, true)));
    r.add(std::unique_ptr<EngineActionHandler>(new AiActionHandler("axi.outstanding_timeline", false, true)));
    r.add(std::unique_ptr<EngineActionHandler>(new AiActionHandler("axi.request_response_pair", false, true)));
    r.add(std::unique_ptr<EngineActionHandler>(new AiActionHandler("axi.latency_outlier",   false, true)));
    // Event handlers
    r.add(std::unique_ptr<EngineActionHandler>(new EventConfigLoadHandler));
    r.add(std::unique_ptr<EngineActionHandler>(new EventConfigListHandler));
    r.add(std::unique_ptr<EngineActionHandler>(new EventHandler(false)));  // event.find
    r.add(std::unique_ptr<EngineActionHandler>(new EventHandler(true)));   // event.export
}

}  // namespace xdebug_design
