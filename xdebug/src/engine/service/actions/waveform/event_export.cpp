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

static Json value_object(const std::string& raw) {
    return xdebug_waveform::logic_value_json(
        xdebug_waveform::logic_value_from_fsdb_raw(raw, 'h'));
}

class EventHandler : public EngineActionHandler {
    bool export_mode_;
public:
    explicit EventHandler(bool export_mode) : export_mode_(export_mode) {}
    const char* action_name() const override { return export_mode_ ? "event.export" : "event.find"; }
    bool needs_design() const override { return false; }
    bool needs_waveform() const override { return true; }
    Json run(const Json& request, EngineActionContext& ctx) const override {
        using namespace xdebug_waveform;
        Json args = request.value("args", Json::object());
        std::string name = args.value("name", "");
        EventConfig config;

        if (!name.empty()) {
            EventManager em;
            if (!em.get_event(g_session_id, g_fsdb_file_path, name, config))
                return Json({{"error","CONFIG_NOT_FOUND"},{"message",name}});
        } else {
            static const char* legacy[] = {"clk", "sampling", "clock_edge", "posedge", "sample_offset", nullptr};
            for (int i = 0; legacy[i]; ++i) {
                if (args.contains(legacy[i])) {
                    return Json({{"error","INVALID_REQUEST"},
                                 {"invalid_arg", std::string("args.") + legacy[i]},
                                 {"message","legacy clock sampling field is not supported; use args.clock, args.edge, and args.sample_point"}});
                }
            }
            std::string clock = args.value("clock", "");
            if (clock.empty())
                return Json({{"error","MISSING_FIELD"},{"message","args.clock is required for inline event config"}});
            config.clock_sample.clock = clock;
            config.rst_n = args.value("rst_n", "");
            std::string edge_error;
            if (!parse_clock_edge_kind(args.value("edge", std::string("negedge")),
                                       config.clock_sample.edge,
                                       edge_error)) {
                return Json({{"error","INVALID_REQUEST"},{"message",edge_error}});
            }
            if (args.contains("sample_point")) {
                if (!args["sample_point"].is_string())
                    return Json({{"error","INVALID_REQUEST"},{"message","args.sample_point must be before or after"}});
                config.clock_sample.has_sample_point = true;
                if (!parse_clock_sample_point_kind(args["sample_point"].get<std::string>(),
                                                   config.clock_sample.sample_point,
                                                   edge_error))
                    return Json({{"error","INVALID_REQUEST"},{"message",edge_error}});
            }
            if (config.clock_sample.edge == ClockEdgeKind::Negedge &&
                config.clock_sample.has_sample_point)
                return Json({{"error","INVALID_REQUEST"},{"message","args.sample_point is only valid with edge:posedge or edge:dual"}});
            Json sigs = args.value("signals", Json::object());
            for (auto it = sigs.begin(); it != sigs.end(); ++it) {
                if (it->is_string()) config.signals[it.key()] = it->get<std::string>();
            }
            if (config.signals.empty())
                return Json({{"error","MISSING_FIELD"},{"message","args.signals is required for inline event config"}});
        }

        npiFsdbTime tbegin = 0, tend = ~0ULL;
        Json time_range = args.value("time_range", Json::object());
        auto parse_t = [](const std::string& s, bool allow_max, npiFsdbTime& t, std::string& error) -> bool {
            if (s.empty()) return true;
            xdebug_core::TimeParseOptions options;
            options.allow_max = allow_max;
            options.default_unit = "ns";
            return xdebug_core::parse_time(g_fsdb_file, s, options, t, error);
        };
        std::string time_error;
        if (!parse_t(time_range.value("start", time_range.value("begin", "")), false, tbegin, time_error) ||
            !parse_t(time_range.value("end", ""), true, tend, time_error)) {
            return Json({{"error","TIME_SPEC_INVALID"},{"message",time_error}});
        }

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

        if (export_mode_) {
            int limit = args.value("limit", limits.value("max_rows", 1000));
            query.limit = limit > 0 ? limit : 1000;
        } else if (mode == "first") {
            query.limit = 1;
            // The candidate-change fast path can skip a match when a sampled
            // signal changes on the same timestamp as the clock edge. Use the
            // full clock-edge scan here so "first" is semantically exact.
            query.fast_find = false;
        } else if (mode == "last") {
            int limit = args.value("limit", limits.value("max_rows", 10000));
            query.limit = limit > 0 ? limit : 10000;
        } else {
            int limit = args.value("limit", limits.value("max_rows", 1000));
            query.limit = limit > 0 ? limit : 1000;
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
            je["time"] = xdebug_core::format_time(g_fsdb_file, rec.time);
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
        }
        out["summary"] = {
            {"event_count", static_cast<int>(arr.size())},
            {"mode", mode},
            {"inline", name.empty()},
            {"sampling_mode", "clock_edge"},
            {"clock", config.clock_sample.clock},
            {"edge", clock_edge_kind_text(config.clock_sample.edge)},
            {"sample_time_semantics", "time is sample_time"}
        };
        if (config.clock_sample.edge != ClockEdgeKind::Negedge)
            out["summary"]["sample_point"] = clock_sample_point_text(config.clock_sample.sample_point);
        if (!arr.empty()) {
            out["first"] = arr[0]["time"];
            out["last"] = arr[arr.size()-1]["time"];
            out["summary"]["first"] = out["first"];
            out["summary"]["last"] = out["last"];
        }
        auto formatted_range = xdebug_core::format_time_range(g_fsdb_file, tbegin, tend);
        out["begin"] = formatted_range.first;
        out["end"] = formatted_range.second;
        out["sampling_mode"] = "clock_edge";
        out["clock"] = config.clock_sample.clock;
        out["edge"] = clock_edge_kind_text(config.clock_sample.edge);
        if (config.clock_sample.edge != ClockEdgeKind::Negedge)
            out["sample_point"] = clock_sample_point_text(config.clock_sample.sample_point);
        out["sample_time_semantics"] = "time is sample_time";
        return out;
    }
};

}  // namespace

std::unique_ptr<EngineActionHandler> make_event_export_handler() {
    return std::unique_ptr<EngineActionHandler>(new EventHandler(true));
}

}  // namespace xdebug_design
