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
#include "../../waveform/export/waveform_exporter.h"
#include "../../waveform/common/xdebug_waveform_paths.h"
#include "../../waveform/service/action_support.h"
#include "../../waveform/service/rc_generator.h"
#include "../../waveform/value/logic_value.h"

#include "npi.h"
#include "npi_fsdb.h"
#include "npi_L1.h"
#include "npi_hdl.h"

#include <fstream>
#include <memory>
#include <algorithm>
#include <map>
#include <sstream>
#include <vector>

namespace xdebug_design {
namespace {

static bool contains_xz(const std::string& v) {
    return xdebug_waveform::logic_value_has_xz(
        xdebug_waveform::logic_value_from_fsdb_raw(v, 'h'));
}

static std::string trim_copy(const std::string& text) {
    size_t begin = 0;
    while (begin < text.size() && std::isspace(static_cast<unsigned char>(text[begin]))) ++begin;
    size_t end = text.size();
    while (end > begin && std::isspace(static_cast<unsigned char>(text[end - 1]))) --end;
    return text.substr(begin, end - begin);
}

static Json value_object(const std::string& raw) {
    return xdebug_waveform::logic_value_json(
        xdebug_waveform::logic_value_from_fsdb_raw(raw, 'h'));
}

static std::string npi_str(NPI_INT32 property, npiHandle hdl) {
    const char* value = hdl ? npi_get_str(property, hdl) : nullptr;
    return value ? std::string(value) : std::string();
}

static std::string fsdb_scope_str(npiFsdbScopePropertyType property,
                                  npiFsdbScopeHandle scope) {
    const char* value = scope ? npi_fsdb_scope_property_str(property, scope) : nullptr;
    return value ? std::string(value) : std::string();
}

static int fsdb_scope_int(npiFsdbScopePropertyType property,
                          npiFsdbScopeHandle scope) {
    int value = 0;
    if (!scope || !npi_fsdb_scope_property(property, scope, &value)) return 0;
    return value;
}

static std::string normalize_root_path(std::string path) {
    path = trim_copy(path);
    while (!path.empty() && path[0] == '/') path.erase(path.begin());
    while (!path.empty() && path.back() == '/') path.pop_back();
    return path;
}

static std::string join_strings(const Json& arr) {
    std::ostringstream os;
    if (!arr.is_array()) return "";
    for (size_t i = 0; i < arr.size(); ++i) {
        if (i) os << ",";
        os << arr[i].get<std::string>();
    }
    return os.str();
}

static std::string object_string_field(const Json& obj, const char* key) {
    if (!obj.is_object()) return "";
    return obj.value(key, std::string());
}

static std::string with_value_prefix(const std::string& raw, char fmt) {
    std::string text = trim_copy(raw);
    if (text.size() >= 2 && text[0] == '\'') return text;
    return std::string("'") + static_cast<char>(std::tolower(static_cast<unsigned char>(fmt))) + text;
}

static Json make_xbit_hints(const Json& args,
                            const std::string& signal,
                            const std::string& raw) {
    if (!args.contains("slice_hint") || !args["slice_hint"].is_object()) return Json();
    Json hint = args["slice_hint"];
    long long width = hint.value("chunk_width", 0LL);
    long long count = hint.value("count", 1LL);
    if (width <= 0) {
        return Json{{"status", "needs_slice_hint"}, {"signal", signal},
                    {"raw_value", trim_copy(raw)}};
    }
    if (count <= 0) count = 1;
    Json slices = Json::array();
    Json commands = Json::array();
    for (long long i = 0; i < count; ++i) {
        long long lo = i * width;
        long long hi = lo + width - 1;
        slices.push_back({{"index", i},
                          {"range", "[" + std::to_string(hi) + ":" + std::to_string(lo) + "]"}});
        commands.push_back("tools/xbit slice \"" + trim_copy(raw) + "\" " +
                           std::to_string(hi) + " " + std::to_string(lo) + " --json");
    }
    return Json{{"status", "ready"}, {"signal", signal}, {"raw_value", trim_copy(raw)},
                {"chunk_width", width}, {"count", count}, {"slices", slices},
                {"commands", commands}};
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
        std::string time_str = args.value("time", args.value("at", std::string()));
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
        raw = with_value_prefix(raw, fmt);

        Json out;
        out["signal"] = signal;
        out["time"] = time_str;
        std::string requested_format = args.value("format", "");
        if (requested_format == "array_indexed" && raw.find('{') == std::string::npos) {
            out["status"] = "unsupported_format";
            out["value"] = value_object(raw);
            out["raw_value"] = trim_copy(raw);
            out["reason"] = "format:array_indexed requires an FSDB aggregate value";
        } else {
            out["status"] = "ok";
            out["value"] = value_object(raw);
        }
        out["known"] = !contains_xz(raw);
        Json hints = make_xbit_hints(args, signal, raw);
        if (!hints.is_null()) out["xbit_hints"] = hints;
        out["summary"] = {{"signal", signal}, {"time", time_str},
                          {"known", !contains_xz(raw)}, {"status", out["status"]}};
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
        if (d.contains("status")) out.emit_kv("status", d["status"]);
        if (d.contains("value")) out.emit_kv("value", d["value"]);
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
        std::string time_str = args.value("time", args.value("at", std::string()));
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
        Json batch = Json::array();
        Json missing_by_reason = Json::object();
        int missing_count = 0;
        int unknown_count = 0;
        for (size_t i = 0; i < names.size(); ++i) {
            Json item;
            item["signal"] = names[i];
            item["time"] = time_str;
            if (found[i]) {
                values[i] = with_value_prefix(values[i], fmt);
                item["status"] = "ok";
                item["value"] = value_object(values[i]);
                if (contains_xz(values[i])) unknown_count++;
            } else {
                item["status"] = "signal_not_found";
                item["value"] = nullptr;
                item["reason"] = "Signal path was not found in the FSDB: " + names[i];
                missing_count++;
                missing_by_reason["signal_not_found"] =
                    missing_by_reason.value("signal_not_found", 0) + 1;
            }
            batch.push_back(item);
        }
        out["values"] = batch;
        out["summary"] = {{"time", time_str}, {"signal_count", batch.size()},
                          {"x_or_z_count", unknown_count}, {"unknown_count", unknown_count},
                          {"missing_count", missing_count},
                          {"missing_by_reason", missing_by_reason}};
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
        if (d.contains("values") && d["values"].is_array()) {
            out.emit_row({"signal", "value", "status"});
            for (const auto& item : d["values"]) {
                if (!item.is_object()) continue;
                out.emit_row({item.value("signal", std::string()),
                              xdebug::json_to_xout_value(item.value("value", Json())),
                              item.value("status", std::string())});
            }
        } else if (d.contains("values") && d["values"].is_object()) {
            for (auto it = d["values"].begin(); it != d["values"].end(); ++it)
                out.emit_row({it.key(), xdebug::json_to_xout_value(it.value())});
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
        Json limits = request.value("limits", Json::object());
        int max_rows = limits.value("max_rows", -1);

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

        const size_t total_signals = signals.size();
        bool truncated = max_rows >= 0 && signals.size() > static_cast<size_t>(max_rows);
        if (truncated) {
            Json limited = Json::array();
            for (int i = 0; i < max_rows; ++i) limited.push_back(signals[i]);
            signals = limited;
        }
        Json out;
        out["path"] = path;
        out["recursive"] = recursive;
        out["scopes"] = scopes;
        out["signals"] = signals;
        out["signals_preview"] = signals;
        out["total_signals"] = static_cast<int>(total_signals);
        out["truncated"] = truncated;
        out["summary"] = {{"path", path}, {"recursive", recursive},
                          {"signal_count", signals.size()}, {"truncated", truncated}};
        return out;
    }

private:
    static Json err(const char* code, const std::string& msg) {
        Json e; e["error"] = code; e["message"] = msg; return e;
    }
};

class ScopeRootsHandler : public EngineActionHandler {
public:
    const char* action_name() const override { return "scope.roots"; }
    bool needs_design() const override { return false; }
    bool needs_waveform() const override { return false; }

    Json run(const Json& request) const override {
        Json args = request.value("args", Json::object());
        std::string source = args.value("source", std::string("auto"));
        if (source.empty()) source = "auto";
        if (source != "auto" && source != "wave" && source != "design")
            return err("INVALID_REQUEST", "args.source must be auto, wave, or design");

        const bool want_wave = source == "auto" || source == "wave";
        const bool want_design = source == "auto" || source == "design";
        Json limitations = Json::array();
        Json wave_roots = Json::array();
        Json wave_root_candidates = Json::array();
        Json design_roots = Json::array();

        if (want_wave) {
            if (g_has_waveform && g_fsdb_file) {
                wave_roots = collect_wave_roots(limitations);
                wave_root_candidates = wave_roots;
            } else {
                limitations.push_back("wave roots unavailable: waveform not loaded");
            }
        }
        if (want_design) {
            if (g_has_design) {
                if (wave_root_candidates.empty() && g_has_waveform && g_fsdb_file) {
                    Json candidate_limitations = Json::array();
                    wave_root_candidates = collect_wave_roots(candidate_limitations);
                }
                design_roots = collect_design_roots(limitations, wave_root_candidates);
            } else {
                limitations.push_back("design roots unavailable: design not loaded");
            }
        }

        Json roots = merge_roots(wave_roots, design_roots);
        int matched_count = 0;
        for (const auto& root : roots) {
            if (root.value("status", "") == "matched") ++matched_count;
        }

        Json recommended = nullptr;
        std::string reason = "none";
        if (roots.size() == 1) {
            recommended = roots[0].value("path", "");
            reason = "unique root";
        } else if (matched_count == 1) {
            for (const auto& root : roots) {
                if (root.value("status", "") == "matched") {
                    recommended = root.value("path", "");
                    reason = "unique matched root";
                    break;
                }
            }
        } else if (roots.empty()) {
            reason = "no roots discovered";
        } else if (matched_count > 1) {
            reason = "multiple matched roots";
        } else {
            reason = "multiple roots or design/wave mismatch";
        }

        Json out;
        out["source"] = source;
        out["roots"] = roots;
        out["wave_roots"] = wave_roots;
        out["design_roots"] = design_roots;
        out["summary"] = {
            {"source", source},
            {"root_count", static_cast<int>(roots.size())},
            {"wave_count", static_cast<int>(wave_roots.size())},
            {"design_count", static_cast<int>(design_roots.size())},
            {"matched_count", matched_count},
            {"recommended_root", recommended},
            {"recommended_reason", reason}
        };
        if (!limitations.empty()) out["limitations"] = limitations;
        return out;
    }

    std::string render_xout(const Json& r) const override {
        xdebug::TextResponseBuilder out("xdebug");
        out.emit_header("scope.roots");
        Json summary = r.value("summary", Json::object());
        out.emit_section("summary");
        out.emit_kv("recommended",
                    summary.value("recommended_root", Json(nullptr)).is_null()
                        ? "none (" + summary.value("recommended_reason", std::string("unknown")) + ")"
                        : summary.value("recommended_root", std::string()));
        out.emit_kv("source", summary.value("source", std::string("auto")));
        out.emit_kv("roots", summary.value("root_count", 0));
        out.emit_kv("matched", summary.value("matched_count", 0));
        out.emit_kv("wave", summary.value("wave_count", 0));
        out.emit_kv("design", summary.value("design_count", 0));

        Json data = r.value("data", Json::object());
        Json roots = data.value("roots", Json::array());
        out.emit_section("roots");
        out.emit_row({"path", "status", "sources", "wave", "design"});
        for (const auto& root : roots) {
            out.emit_row({
                root.value("path", std::string()),
                root.value("status", std::string()),
                join_strings(root.value("sources", Json::array())),
                object_string_field(root.value("wave", Json()), "full_name"),
                object_string_field(root.value("design", Json()), "full_name")
            });
        }
        if (roots.empty()) out.emit_row({"[empty]", "", "", "", ""});

        Json limitations = data.value("limitations", Json::array());
        if (!limitations.empty()) {
            out.emit_section("limitations");
            for (const auto& item : limitations) {
                out.emit_row({xdebug::json_to_xout_value(item)});
            }
        }
        return out.str();
    }

private:
    static Json collect_wave_roots(Json& limitations) {
        Json roots = Json::array();
        npiFsdbScopeIter iter = npi_fsdb_iter_top_scope(g_fsdb_file);
        if (!iter) {
            limitations.push_back("wave root iterator returned no scopes");
            return roots;
        }
        while (npiFsdbScopeHandle scope = npi_fsdb_iter_scope_next(iter)) {
            Json root;
            std::string full_name = fsdb_scope_str(npiFsdbScopeFullName, scope);
            std::string name = fsdb_scope_str(npiFsdbScopeName, scope);
            if (full_name.empty()) full_name = name;
            root["path"] = normalize_root_path(full_name);
            root["name"] = name;
            root["full_name"] = full_name;
            root["def_name"] = fsdb_scope_str(npiFsdbScopeDefName, scope);
            root["type"] = fsdb_scope_int(npiFsdbScopeType, scope);
            root["queryable"] = true;
            roots.push_back(root);
        }
        npi_fsdb_iter_scope_stop(iter);
        return roots;
    }

    static Json collect_design_roots(Json& limitations, const Json& wave_candidates) {
        Json roots = Json::array();
        npiHandle iter = npi_iterate(npiTop, nullptr);
        if (iter) {
            while (npiHandle hdl = npi_scan(iter)) {
                Json root = design_root_from_handle(hdl, "npi_top");
                if (!root.value("path", std::string()).empty()) roots.push_back(root);
            }
        }
        if (!roots.empty()) return roots;

        for (const auto& candidate : wave_candidates) {
            std::string path = candidate.value("path", std::string());
            if (path.empty()) continue;
            npiHandle hdl = npi_handle_by_name(path.c_str(), nullptr);
            if (!hdl) continue;
            int type = npi_get(npiType, hdl);
            if (type != npiModule && type != npiInterface && type != npiProgram) continue;
            Json root = design_root_from_handle(hdl, "verified_wave_root");
            if (!root.value("path", std::string()).empty()) roots.push_back(root);
        }
        if (roots.empty()) limitations.push_back("design root discovery returned no top handles");
        return roots;
    }

    static Json design_root_from_handle(npiHandle hdl, const std::string& discovery) {
        Json root;
        std::string full_name = npi_str(npiFullName, hdl);
        std::string name = npi_str(npiName, hdl);
        if (full_name.empty()) full_name = name;
        root["path"] = normalize_root_path(full_name);
        root["name"] = name;
        root["full_name"] = full_name;
        root["def_name"] = npi_str(npiDefName, hdl);
        int type = npi_get(npiType, hdl);
        if (type == npiModule) root["kind"] = "module";
        else if (type == npiInterface) root["kind"] = "interface";
        else if (type == npiProgram) root["kind"] = "program";
        else root["kind"] = "scope";
        root["discovery"] = discovery;
        root["traceable"] = true;
        return root;
    }

    static Json merge_roots(const Json& wave_roots, const Json& design_roots) {
        struct Entry {
            Json wave = nullptr;
            Json design = nullptr;
        };
        std::map<std::string, Entry> by_path;
        for (const auto& root : wave_roots) {
            std::string path = normalize_root_path(root.value("path", std::string()));
            if (!path.empty()) by_path[path].wave = root;
        }
        for (const auto& root : design_roots) {
            std::string path = normalize_root_path(root.value("path", std::string()));
            if (!path.empty()) by_path[path].design = root;
        }

        Json roots = Json::array();
        for (auto& kv : by_path) {
            Json item;
            item["path"] = kv.first;
            item["sources"] = Json::array();
            item["wave"] = kv.second.wave;
            item["design"] = kv.second.design;
            const bool has_wave = !kv.second.wave.is_null();
            const bool has_design = !kv.second.design.is_null();
            if (has_design) item["sources"].push_back("design");
            if (has_wave) item["sources"].push_back("wave");
            if (has_design && has_wave) item["status"] = "matched";
            else if (has_design) item["status"] = "design_only";
            else item["status"] = "wave_only";
            roots.push_back(item);
        }
        return roots;
    }

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
            while (*e && std::isspace(*e)) ++e;
            u = e;
            npi_fsdb_convert_time_in(g_fsdb_file, v, u.c_str(), t);
        };
        parse_t(time_range.value("start", time_range.value("begin", "")), tbegin);
        parse_t(time_range.value("end", ""), tend);

        EventQuery query;
        query.expr = args.value("expr", "");
        query.begin = tbegin;
        query.end = tend;
        Json limits = request.value("limits", Json::object());
        std::string mode = args.value("mode", export_mode_ ? "export" : "first");
        if (mode == "head") mode = "first";
        if (mode == "tail") mode = "last";
        if (!export_mode_ && mode != "first" && mode != "last" && mode != "all") {
            return Json({{"error","INVALID_REQUEST"},
                         {"message","args.mode must be first, last, or all"}});
        }

        int scan_limit = 0;
        if (export_mode_) {
            int max_examples = args.value(
                "max_examples",
                args.value("max_events",
                           args.value("limit", limits.value("max_rows", 1000))));
            query.limit = max_examples > 0 ? max_examples : 1000;
        } else if (mode == "first") {
            query.limit = 1;
            // The candidate-change fast path can skip a match when a sampled
            // signal changes on the same timestamp as the clock edge. Use the
            // full clock-edge scan here so "first" is semantically exact.
            query.fast_find = false;
        } else if (mode == "last") {
            scan_limit = args.value("scan_limit", limits.value("max_rows", 10000));
            query.limit = scan_limit > 0 ? scan_limit : 10000;
        } else {
            int max_events = args.value(
                "limit",
                args.value("max_events", limits.value("max_rows", 1000)));
            query.limit = max_events > 0 ? max_events : 1000;
        }

        std::vector<EventRecord> records;
        std::string error;
        if (!g_event_analyzer.analyze(g_fsdb_file, config, query, records, error))
            return Json({{"error","EVENT_FAILED"},{"message",error}});
        if (!export_mode_ && mode == "last" && records.size() > 1) {
            EventRecord last = records.back();
            records.assign(1, last);
        }

        Json arr = Json::array();
        for (auto& rec : records) {
            Json je;
            je["time"] = format_time(rec.time);
            je["time_ps"] = rec.time;
            Json signal_values = Json::object();
            for (const auto& value : rec.signals)
                signal_values[value.first] = value_object(value.second);
            Json field_values = Json::object();
            for (const auto& value : rec.fields)
                field_values[value.first] = value_object(value.second);
            je["signals"] = signal_values;
            je["fields"] = field_values;
            arr.push_back(je);
        }
        Json out;
        bool include_events = true;
        if (export_mode_ && args.contains("aggregate") && args["aggregate"].is_object()) {
            Json aggregate_args = args["aggregate"];
            Json aggregate;
            aggregate["count"] = arr.size();
            Json groups = Json::object();
            Json group_by = aggregate_args.value("group_by", Json::array());
            if (group_by.is_array() && !group_by.empty()) {
                for (const auto& event : arr) {
                    std::string key;
                    for (const auto& field : group_by) {
                        if (!field.is_string()) continue;
                        std::string name = field.get<std::string>();
                        Json value;
                        if (event["fields"].contains(name)) value = event["fields"][name]["value"];
                        else if (event["signals"].contains(name)) value = event["signals"][name]["value"];
                        if (!key.empty()) key += "|";
                        key += name + "=" + (value.is_string() ? value.get<std::string>() : "null");
                    }
                    groups[key] = groups.value(key, 0) + 1;
                }
            }
            aggregate["groups"] = groups;
            aggregate["group_count"] = groups.size();
            out["aggregate"] = aggregate;
            include_events = aggregate_args.value("events", true);
        }
        if (include_events) {
            out["events"] = arr;
            out["examples"] = arr;
        }
        out["count"] = static_cast<int>(arr.size());
        out["event_count"] = out["count"];
        if (!arr.empty()) {
            out["first"] = arr[0]["time"];
            out["last"] = arr[arr.size()-1]["time"];
        }
        out["begin"] = time_range.value("start", time_range.value("begin", ""));
        out["end"] = time_range.value("end", "");
        out["mode"] = mode;
        if (scan_limit > 0) out["scan_limit"] = scan_limit;
        out["sampling_mode"] = "clock_edge";
        out["inline"] = name.empty();
        out["summary"] = {
            {"event_count", out["event_count"]},
            {"first", out.value("first", Json())},
            {"last", out.value("last", Json())},
            {"count", out["count"]},
            {"mode", mode},
            {"inline", name.empty()}
        };
        if (scan_limit > 0) out["summary"]["scan_limit"] = scan_limit;
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
        Json effective_request = request;
        if (name_ == "inspect_signal") {
            effective_request["args"]["include_rows"] = true;
        }
        Json result = xdebug_waveform::ai_dispatch_query(effective_request, error);
        if (!error.empty()) {
            Json e; e["error"] = "ACTION_FAILED"; e["message"] = error; return e;
        }
        // Fix statistics end time: ai functions may return FSDB max time
        // instead of the requested window end.
        Json args = request.value("args", Json::object());
        if (name_ == "signal.changes") {
            int limit = args.value("limit", args.value("max_events", 1000));
            size_t matched = result.value("returned_change_rows", static_cast<size_t>(0));
            if (limit >= 0 && matched > static_cast<size_t>(limit))
                result["truncated"] = true;
        }
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
        int passed = 0;
        int failed = 0;
        int unknown = 0;
        for (auto& cond : conditions) {
            Json r;
            r["signal"] = cond.value("signal", "");
            r["time"] = time_str;
            r["op"] = cond.value("op", "==");
            r["expected"] = cond.value("value", "");
            xdebug_waveform::LogicValue expected_value =
                xdebug_waveform::parse_user_logic_literal(r["expected"].get<std::string>());
            if (!expected_value.valid)
                return err("VALUE_FORMAT_INVALID", expected_value.error);
            std::string signal = cond.value("signal", "");
            if (!signal.empty()) {
                std::string raw;
                if (npi_fsdb_sig_value_at(g_fsdb_file, signal.c_str(), fsdb_time, raw, npiFsdbHexStrVal)) {
                    raw = with_value_prefix(raw, 'h');
                    xdebug_waveform::LogicValue observed =
                        xdebug_waveform::logic_value_from_fsdb_raw(raw, 'h');
                    bool known = !xdebug_waveform::logic_value_has_xz(observed) &&
                                 !xdebug_waveform::logic_value_has_xz(expected_value);
                    r["observed"] = value_object(raw);
                    r["known"] = known;
                    std::string op = cond.value("op", "==");
                    if (known) {
                        bool equal = xdebug_waveform::logic_value_compare_key(observed) ==
                                     xdebug_waveform::logic_value_compare_key(expected_value);
                        bool pass = op == "!=" ? !equal : equal;
                        r["status"] = pass ? "pass" : "fail";
                        r["pass"] = pass;
                        if (pass) passed++; else failed++;
                    } else {
                        r["status"] = "unknown";
                        r["pass"] = nullptr;
                        unknown++;
                    }
                } else {
                    r["known"] = false;
                    r["status"] = "unknown";
                    r["pass"] = nullptr;
                    r["error"] = "signal not found";
                    unknown++;
                }
            } else {
                r["known"] = false;
                r["status"] = "unknown";
                r["pass"] = nullptr;
                unknown++;
            }
            results.push_back(r);
        }
        Json out;
        out["time"] = time_str;
        out["all_pass"] = failed == 0 && unknown == 0;
        out["checks"] = results;
        out["results"] = results;
        out["summary"] = {{"verdict", out["all_pass"].get<bool>() ? "pass" : "fail"},
                          {"condition_count", results.size()},
                          {"all_passed", out["all_pass"]},
                          {"passed", passed}, {"failed", failed}, {"unknown", unknown}};
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

        EventConfig cfg;
        if (!parse_event_config(cfg_j, cfg, err))
            return Json({{"error","INVALID_REQUEST"},{"message",err}});
        cfg.name = name;

        EventManager em;
        if (!em.create_event(g_session_id, g_fsdb_file_path, cfg))
            return Json({{"error","CREATE_FAILED"},{"message","failed to save event config"}});

        Json out;
        out["summary"] = {{"name", name}, {"status", "loaded"}};
        out["name"] = name; out["status"] = "loaded";
        out["config"] = event_config_json(cfg);
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
        out["summary"] = {{"name", n}, {"status", "created"}};
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
        if (!npi_fsdb_sig_by_name(xdebug_waveform::g_fsdb_file, sig.c_str(), NULL))
            return Json({{"error","SIGNAL_NOT_FOUND"},{"message",sig}});
        xdebug_waveform::ListManager lm;
        if (!lm.add_signal(xdebug_waveform::g_session_id, n, sig))
            return Json({{"error","ADD_FAILED"},{"message",sig}});
        Json out; out["name"] = n; out["signal"] = sig; out["added"] = true;
        out["summary"] = {{"name", n}, {"signal", sig}, {"status", "added"}};
        return out;
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
        std::string signal = a.value("signal", a.value("index", ""));
        if (signal.empty())
            return Json({{"error","MISSING_FIELD"},{"message","args.signal or args.index"}});
        if (!lm.del_signal(xdebug_waveform::g_session_id, n, signal))
            return Json({{"error","DEL_FAILED"}});
        Json out; out["name"] = n; out["deleted"] = true; out["removed"] = signal;
        out["summary"] = {{"name", n}, {"removed", signal}};
        return out;
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
        Json arr = Json::array();
        for (size_t i = 0; i < lst.signals.size(); ++i)
            arr.push_back({{"index", static_cast<int>(i) + 1}, {"signal", lst.signals[i]}});
        out["signals"] = arr; out["count"] = static_cast<int>(lst.signals.size());
        out["summary"] = {{"name", n}, {"signal_count", arr.size()}};
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
        while (e && *e && std::isspace(*e)) ++e;
        unit = e;
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
        out["summary"] = {{"name", n}, {"time", ts}};
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
        Json out; out["name"] = n; out["signals"] = arr;
        bool all_found = true;
        for (const auto& item : arr) {
            if (item.value("status", "") != "ok") all_found = false;
        }
        out["summary"] = {{"name", n}, {"all_found", all_found}};
        return out;
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
            while (e && *e && std::isspace(*e)) ++e;
            u = e;
            return !u.empty() && npi_fsdb_convert_time_in(xdebug_waveform::g_fsdb_file, v, u.c_str(), t);
        };
        npiFsdbTime bt = 0, et = 0;
        if (!ptime(bs, bt) || !ptime(es, et))
            return Json({{"error","TIME_SPEC_INVALID"}});
        npiFsdbTime dt = 0;
        bool found = xdebug_waveform::find_list_diff(
            xdebug_waveform::g_fsdb_file, lst.signals, bt, et, dt);
        Json out; out["name"] = n; out["diff_found"] = found;
        if (found) {
            std::string formatted = xdebug_waveform::format_time(dt);
            out["diff_time"] = formatted;
            out["time"] = formatted;
            out["summary"] = {{"name", n}, {"diff_time", formatted}};
        } else {
            out["summary"] = {{"name", n}, {"diff_time", ""}};
        }
        return out;
    }
};

class ListExportHandler : public EngineActionHandler {
public:
    const char* action_name() const override { return "list.export"; }
    bool needs_design() const override { return false; }
    bool needs_waveform() const override { return true; }
    Json run(const Json& r) const override {
        Json a = r.value("args", Json::object());
        std::string n = a.value("name", a.value("list", ""));
        if (n.empty()) return Json({{"error","MISSING_FIELD"},{"message","args.name"}});
        xdebug_waveform::SignalList lst;
        if (!read_list_storage(n, lst))
            return Json({{"error","LIST_NOT_FOUND"},{"message",n}});

        Json tr = a.value("time_range", Json::object());
        std::string bs = tr.value("begin", tr.value("from", std::string()));
        std::string es = tr.value("end", tr.value("to", std::string()));
        if (bs.empty()) bs = a.value("start", a.value("begin", a.value("from", std::string())));
        if (es.empty()) es = a.value("end", a.value("to", std::string()));
        if (bs.empty() || es.empty())
            return Json({{"error","MISSING_FIELD"},{"message","list.export requires begin/end"}});

        auto ptime = [](const std::string& s, bool allow_max, npiFsdbTime& t) -> bool {
            if (allow_max && (s == "max" || s == "inf")) {
                t = 0xffffffffffffffffULL;
                return true;
            }
            double v; std::string u; char* e = nullptr;
            v = std::strtod(s.c_str(), &e);
            while (e && *e && std::isspace(*e)) ++e;
            u = e;
            return !u.empty() && npi_fsdb_convert_time_in(xdebug_waveform::g_fsdb_file, v, u.c_str(), t);
        };
        npiFsdbTime begin = 0, end = 0;
        if (!ptime(bs, false, begin) || !ptime(es, true, end))
            return Json({{"error","TIME_SPEC_INVALID"},{"message","failed to parse list.export time range"}});
        if (end < begin)
            return Json({{"error","TIME_SPEC_INVALID"},{"message","end time is before begin time"}});
        if (end - begin < 256000ULL)
            return Json({{"error","TIME_RANGE_TOO_SMALL"},{"message","list.export requires at least 256ns; use list.value_at or value.batch_at for point reads"}});

        std::string format = a.value("format", std::string("u64bin"));
        std::string output_dir = a.value("output_dir", std::string());
        if (output_dir.empty()) {
            output_dir = xdebug_waveform::xdebug_waveform_list_exports_dir(xdebug_waveform::g_session_id)
                + "/" + n + "_" + std::to_string(begin) + "_" + std::to_string(end)
                + "_" + std::to_string(static_cast<long long>(time(nullptr)));
        }
        xdebug_waveform::ListExportOptions options;
        options.session_id = xdebug_waveform::g_session_id;
        options.list_name = n;
        options.output_dir = output_dir;
        options.format = format;
        options.begin = begin;
        options.end = end;
        xdebug_waveform::ListExportResult result;
        std::string error;
        if (!xdebug_waveform::export_signal_list(xdebug_waveform::g_fsdb_file, lst, options, result, error))
            return Json({{"error","EXPORT_FAILED"},{"message",error}});

        Json out;
        out["summary"] = {{"name", n}, {"signal_count", result.signal_count},
                          {"row_count", result.row_count}, {"format", result.format}};
        out["output_dir"] = result.output_dir;
        out["manifest_file"] = result.manifest_file;
        out["format"] = result.format;
        out["signal_count"] = result.signal_count;
        out["row_count"] = result.row_count;
        out["signals"] = result.signals;
        out["begin"] = xdebug_waveform::format_time(begin);
        out["end"] = xdebug_waveform::format_time(end);
        out["begin_ps"] = begin;
        out["end_ps"] = end;
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
    r.add(std::unique_ptr<EngineActionHandler>(new ScopeRootsHandler));
    r.add(std::unique_ptr<EngineActionHandler>(new ListCreateHandler));
    r.add(std::unique_ptr<EngineActionHandler>(new ListAddHandler));
    r.add(std::unique_ptr<EngineActionHandler>(new ListDeleteHandler));
    r.add(std::unique_ptr<EngineActionHandler>(new ListShowHandler));
    r.add(std::unique_ptr<EngineActionHandler>(new ListValueAtHandler));
    r.add(std::unique_ptr<EngineActionHandler>(new ListValidateHandler));
    r.add(std::unique_ptr<EngineActionHandler>(new ListDiffHandler));
    r.add(std::unique_ptr<EngineActionHandler>(new ListExportHandler));
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
    r.add(std::unique_ptr<EngineActionHandler>(new AiActionHandler("counter.statistics",    false, true)));
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
