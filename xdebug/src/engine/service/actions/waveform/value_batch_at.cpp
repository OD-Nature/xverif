#include "service/engine_action_handler.h"
#include "service/engine_action_registry.h"
#include "service/engine_globals.h"

#include "api/text_response_builder.h"
#include "design/protocol/protocol.h"
#include "waveform/server/fsdb_value_reader.h"
#include "waveform/event/event_manager.h"
#include "waveform/event/event_analyzer.h"
#include "waveform/list/list_manager.h"
#include "waveform/list/signal_list.h"
#include "waveform/export/waveform_exporter.h"
#include "waveform/common/xdebug_waveform_paths.h"
#include "waveform/service/action_support.h"
#include "waveform/service/rc_generator.h"
#include "waveform/value/logic_value.h"
#include "core/npi/time_contract.h"

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
static std::string with_value_prefix(const std::string& raw, char fmt) {
    std::string text = trim_copy(raw);
    if (text.size() >= 2 && text[0] == '\'') return text;
    return std::string("'") + static_cast<char>(std::tolower(static_cast<unsigned char>(fmt))) + text;
}

class ValueBatchAtHandler : public EngineActionHandler {
public:
    const char* action_name() const override { return "value.batch_at"; }
    bool needs_design() const override { return false; }
    bool needs_waveform() const override { return true; }

    Json run(const Json& request, EngineActionContext& ctx) const override {
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
        std::string time_error;
        if (!xdebug_waveform::parse_user_time(time_str.c_str(), false, fsdb_time, time_error))
            return err("TIME_SPEC_INVALID", time_error.empty() ? "failed to parse time: " + time_str : time_error);

        std::vector<std::string> names;
        for (const auto& s : signals_j)
            if (s.is_string()) names.push_back(s.get<std::string>());

        std::vector<std::string> values;
        std::vector<bool> found;
        xdebug_waveform::read_sig_vec_value_at_with_status(
            g_fsdb_file, names, fsdb_time, fmt, values, found);

        Json out;
        std::string formatted_time = xdebug_core::format_time(g_fsdb_file, fsdb_time);
        out["time"] = formatted_time;
        Json batch = Json::array();
        Json missing_by_reason = Json::object();
        int missing_count = 0;
        int unknown_count = 0;
        for (size_t i = 0; i < names.size(); ++i) {
            Json item;
            item["signal"] = names[i];
            item["time"] = formatted_time;
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
        out["summary"] = {{"time", formatted_time}, {"signal_count", batch.size()},
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
            std::vector<std::vector<std::string>> rows;
            for (const auto& item : d["values"]) {
                if (!item.is_object()) continue;
                rows.push_back({item.value("signal", std::string()),
                                xdebug::json_to_xout_value(item.value("value", Json())),
                                item.value("status", std::string())});
            }
            out.emit_table({"signal", "value", "status"}, rows);
        } else if (d.contains("values") && d["values"].is_object()) {
            std::vector<std::vector<std::string>> rows;
            for (auto it = d["values"].begin(); it != d["values"].end(); ++it)
                rows.push_back({it.key(), xdebug::json_to_xout_value(it.value())});
            out.emit_table({"signal", "value"}, rows);
        }
        return out.str();
    }
};

}  // namespace

std::unique_ptr<EngineActionHandler> make_value_batch_at_handler() {
    return std::unique_ptr<EngineActionHandler>(new ValueBatchAtHandler);
}

}  // namespace xdebug_design
