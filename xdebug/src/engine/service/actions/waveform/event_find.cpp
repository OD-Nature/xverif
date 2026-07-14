#include "service/engine_action_handler.h"
#include "service/engine_action_registry.h"
#include "service/engine_globals.h"
#include "event_action_helpers.h"

#include "api/text_response_builder.h"
#include "design/protocol/protocol.h"
#include "waveform/server/fsdb_value_reader.h"
#include "waveform/event/event_manager.h"
#include "waveform/event/event_analyzer.h"
#include "waveform/list/list_manager.h"
#include "waveform/list/signal_list.h"
#include "waveform/export/waveform_exporter.h"
#include "waveform/common/expression.h"
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

static Json expression_alias_error(const char* action, const std::string& message) {
    return event_expression_alias_error(action, message);
}

static Json validate_expr_aliases(const std::string& action, const std::string& expr) {
    xdebug_waveform::Expression parsed;
    std::string error;
    if (!parsed.parse(expr, error)) {
        return expression_alias_error(action.c_str(), error);
    }
    std::vector<std::string> bad_aliases =
        xdebug_waveform::expression_aliases_that_look_like_paths(parsed.aliases());
    if (!bad_aliases.empty()) {
        return expression_alias_error(
            action.c_str(),
            "expression operands must be aliases, not direct signal paths: " +
            bad_aliases.front() + "; put real signal paths in args.signals");
    }
    return Json();
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
                return event_config_not_found_error(action_name(), name);
        } else {
            static const char* legacy[] = {"clk", "sampling", "clock_edge", "posedge", "sample_offset", nullptr};
            for (int i = 0; legacy[i]; ++i) {
                if (args.contains(legacy[i])) {
                    return event_invalid_arg_error(
                        action_name(),
                        std::string("args.") + legacy[i],
                        "legacy clock sampling field is not supported; use args.clock, args.edge, and args.sample_point",
                        "args.clock, args.edge, and args.sample_point");
                }
            }
            std::string clock = args.value("clock", "");
            if (clock.empty())
                return event_missing_field_error(action_name(), "args.clock", "clock alias or signal path for inline event config");
            config.clock_sample.clock = clock;
            config.rst_n = args.value("rst_n", "");
            std::string edge_error;
            if (!parse_clock_edge_kind(args.value("edge", std::string("negedge")),
                                       config.clock_sample.edge,
                                       edge_error)) {
                return event_invalid_enum_error(action_name(), "args.edge", edge_error,
                                                Json::array({"posedge", "negedge", "dual"}));
            }
            if (args.contains("sample_point")) {
                if (!args["sample_point"].is_string())
                    return event_invalid_arg_error(action_name(), "args.sample_point",
                                                   "args.sample_point must be before or after",
                                                   "before or after",
                                                   Json::array({"before", "after"}));
                config.clock_sample.has_sample_point = true;
                if (!parse_clock_sample_point_kind(args["sample_point"].get<std::string>(),
                                                   config.clock_sample.sample_point,
                                                   edge_error))
                    return event_invalid_enum_error(action_name(), "args.sample_point", edge_error,
                                                    Json::array({"before", "after"}));
            }
            if (config.clock_sample.edge == ClockEdgeKind::Negedge &&
                config.clock_sample.has_sample_point)
                return event_invalid_arg_error(action_name(), "args.sample_point",
                                               "args.sample_point is only valid with edge:posedge or edge:dual",
                                               "omit sample_point for negedge, or use edge posedge/dual");
            Json sigs = args.value("signals", Json::object());
            for (auto it = sigs.begin(); it != sigs.end(); ++it) {
                if (it->is_string()) config.signals[it.key()] = it->get<std::string>();
            }
            if (config.signals.empty())
                return event_missing_field_error(action_name(), "args.signals", "alias to real signal path map");
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
        if (!parse_t(time_range.value("begin", ""), false, tbegin, time_error) ||
            !parse_t(time_range.value("end", ""), true, tend, time_error)) {
            return event_time_error(action_name(), time_error);
        }

        EventQuery query;
        query.expr = args.value("expr", "");
        Json expr_error = validate_expr_aliases(action_name(), query.expr);
        if (!expr_error.is_null()) return expr_error;
        query.begin = tbegin;
        query.end = tend;
        query.max_samples = args.value("max_samples", -1);
        EventScanStats scan_stats;
        query.stats = &scan_stats;
        std::string mode = args.value("mode", export_mode_ ? "export" : "first");
        if (mode == "head") mode = "first";
        if (mode == "tail") mode = "last";
        if (!export_mode_ && mode != "first" && mode != "last" && mode != "all") {
            return event_invalid_enum_error(action_name(), "args.mode",
                                            "args.mode must be first, last, or all",
                                            Json::array({"first", "last", "all"}));
        }

        if (export_mode_) {
            int limit = args.value("line_limit", 1000);
            query.limit = limit > 0 ? limit : 1000;
        } else if (mode == "first") {
            if (args.contains("line_limit"))
                return event_invalid_enum_error(action_name(), "args.line_limit",
                                                "line_limit is only valid with mode=all",
                                                Json::array({"omit line_limit"}));
            query.limit = 1;
            // The candidate-change fast path can skip a match when a sampled
            // signal changes on the same timestamp as the clock edge. Use the
            // full clock-edge scan here so "first" is semantically exact.
            query.fast_find = false;
        } else if (mode == "last") {
            if (args.contains("line_limit"))
                return event_invalid_enum_error(action_name(), "args.line_limit",
                                                "line_limit is only valid with mode=all",
                                                Json::array({"omit line_limit"}));
            query.limit = -1;
            query.retain_last_only = true;
        } else {
            query.limit = -1;
        }

        std::vector<EventRecord> records;
        std::string error;
        if (!g_event_analyzer.analyze(g_fsdb_file, config, query, records, error))
            return make_handler_error("ACTION_FAILED", error, {{"cause_code", "EVENT_FAILED"}});
        if (!export_mode_ && mode == "last" && records.size() > 1) {
            EventRecord last = records.back();
            records.assign(1, last);
        }

        const size_t matched_count = static_cast<size_t>(scan_stats.matched_count);
        const int response_limit = args.value("line_limit", 1000);
        Json arr = Json::array();
        size_t response_count = 0;
        for (auto& rec : records) {
            if (!export_mode_ && mode == "all" && response_limit >= 0 &&
                static_cast<int>(response_count) >= response_limit) break;
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
            ++response_count;
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
            {"event_count", static_cast<int>(matched_count)},
            {"returned_event_count", static_cast<int>(arr.size())},
            {"response_truncated", mode == "all" && arr.size() < matched_count},
            {"scan_complete", !scan_stats.sample_budget_exhausted},
            {"sample_count", scan_stats.sample_count},
            {"mode", mode},
            {"inline", name.empty()},
            {"sampling_mode", "clock_edge"},
            {"clock", config.clock_sample.clock},
            {"edge", clock_edge_kind_text(config.clock_sample.edge)},
            {"sample_time_semantics", "time is sample_time"}
        };
        out["summary"]["analysis_complete"] = !scan_stats.sample_budget_exhausted;
        const bool response_truncated = mode == "all" && arr.size() < matched_count;
        out["summary"]["truncated"] = scan_stats.sample_budget_exhausted || response_truncated;
        out["summary"]["truncation_scopes"] = Json::array();
        if (scan_stats.sample_budget_exhausted)
            out["summary"]["truncation_scopes"].push_back("analysis_samples");
        if (response_truncated)
            out["summary"]["truncation_scopes"].push_back("response_events");
        if (config.clock_sample.edge != ClockEdgeKind::Negedge)
            out["summary"]["sample_point"] = clock_sample_point_text(config.clock_sample.sample_point);
        if (scan_stats.matched_count > 0) {
            out["summary"]["first"] = xdebug_core::format_time(g_fsdb_file, scan_stats.first_match_time);
            out["summary"]["last"] = xdebug_core::format_time(g_fsdb_file, scan_stats.last_match_time);
        }
        auto formatted_range = xdebug_core::format_time_range(g_fsdb_file, tbegin, tend);
        out["summary"]["begin"] = formatted_range.first;
        out["summary"]["end"] = formatted_range.second;
        return out;
    }
};

}  // namespace

std::unique_ptr<EngineActionHandler> make_event_find_handler() {
    return std::unique_ptr<EngineActionHandler>(new EventHandler(false));
}

}  // namespace xdebug_design
