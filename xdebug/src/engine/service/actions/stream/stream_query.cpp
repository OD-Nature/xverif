#include "service/engine_action_handler.h"
#include "service/engine_action_registry.h"
#include "service/engine_globals.h"

#include "waveform/common/xdebug_waveform_paths.h"
#include "waveform/stream/legacy_stream_analyzer_adapter.h"
#include "waveform/stream/stream_exporter.h"
#include "waveform/stream/stream_manager.h"
#include "waveform/filter/value_filter.h"
#include "core/npi/time_contract.h"

#include "npi_fsdb.h"
#include "npi_L1.h"

#include <ctime>
#include <memory>
#include <set>
#include <sstream>
#include <sys/stat.h>

namespace xdebug_design {
namespace {

using xdebug_waveform::Json;
using xdebug_waveform::StreamAnalysis;
using xdebug_waveform::analyze_stream_cached_with_legacy_differential;
using xdebug_waveform::AnalysisCacheScope;
using xdebug_waveform::StreamConfig;
using xdebug_waveform::StreamExporter;
using xdebug_waveform::StreamManager;
using xdebug_waveform::StreamQueryOptions;
using xdebug_waveform::ValueFilter;
using xdebug_waveform::ValueFilterError;
using xdebug_waveform::ValueFilterParseOptions;

Json err(const std::string& code, const std::string& message, const Json& details) {
    return make_handler_error(code, message, details);
}
Json stream_query_example(const std::string& stream = "req_stream",
                          const std::string& query = "summary") {
    return Json{{"api_version", "xdebug.v1"},
                {"action", "stream.query"},
                {"target", {{"session_id", "case_a"}}},
                {"args", {{"stream", stream}, {"query", query}}}};
}
Json stream_name_error(const std::string& action, const std::string& name) {
    Json example = stream_query_example();
    example["action"] = action;
    Json details = {{"invalid_arg", "args.stream"},
                    {"expected", "name of a previously loaded stream config"},
                    {"correct_example", example},
                    {"example_note", "Example only; replace target.session_id and args.stream with the active session and loaded stream name."},
                    {"next_actions", Json::array({"Call stream.config.list to inspect loaded stream names.",
                                                   "Call stream.config.load before querying a stream."})}};
    if (!name.empty()) {
        details["missing_name"] = name;
        details["missing_resource"] = "stream config";
    }
    return err(name.empty() ? "MISSING_FIELD" : "CONFIG_NOT_FOUND",
               name.empty() ? "args.stream is required" : "stream config not found: " + name,
               details);
}
std::string code_for_stream_error(const std::string& message, const std::string& fallback) {
    return message.find("0x prefix is not accepted") != std::string::npos ||
           message.find("invalid value literal") != std::string::npos
        ? "VALUE_FORMAT_INVALID"
        : fallback;
}
Json stream_time_error(const std::string& message) {
    return err("INVALID_TIME", message,
               {{"invalid_arg", "args.time_range"},
                {"expected", "args.time_range.begin/end time strings such as 0ns and 100ns"},
                {"correct_example", stream_query_example()},
                {"example_note", "Example only; omit time_range for full waveform or use begin/end strings with units."},
                {"next_actions", Json::array({"Fix args.time_range.begin/end to include a valid unit.",
                                               "Omit args.time_range to query the whole waveform."})}});
}
Json stream_analyze_error(const std::string& message) {
    return err(code_for_stream_error(message, "ACTION_FAILED"), message,
               {{"cause_code", "STREAM_ANALYZE_FAILED"},
                {"expected", "loaded stream config whose aliased signal paths exist in the active FSDB"},
                {"correct_example", stream_query_example()},
                {"next_actions", Json::array({"Call stream.show to inspect config signal aliases.",
                                               "Call stream.validate to check static and dynamic stream issues."})}});
}
Json stream_filter_error(const std::string& stream,
                         const std::string& message,
                         const std::string& invalid_arg) {
    Json example = stream_query_example(stream, "transfer_window");
    example["args"]["filter"] = {
        {"fields", {{"opcode", {{"mode", "exact"},
                                  {"values", Json::array({"8'h5a"})}}}}}};
    return err(code_for_stream_error(message, "INVALID_ARGUMENT"), message,
               {{"invalid_arg", invalid_arg},
                {"expected", "non-empty filter.fields using exactly one of exact, range, or mask per configured stream field"},
                {"correct_example", example},
                {"example_note", "Example only; choose fields from stream.show. Packet streams also require filter.position=sop or eop."}});
}

bool parse_stream_filter(const Json& filter_json,
                         const StreamConfig& config,
                         StreamQueryOptions& options,
                         std::string& error,
                         std::string& invalid_arg) {
    options.filter.enabled = true;
    options.filter.position = filter_json.value("position", std::string());
    const bool packet_enabled = xdebug_waveform::stream_packet_enabled(config);
    if (packet_enabled) {
        if (options.filter.position != "sop" && options.filter.position != "eop") {
            error = "packet stream filter requires position=sop or position=eop";
            invalid_arg = "args.filter.position";
            return false;
        }
    } else if (!options.filter.position.empty()) {
        error = "filter.position is only valid for streams configured with sop/eop";
        invalid_arg = "args.filter.position";
        return false;
    }

    std::set<std::string> available;
    if (!config.data.empty()) available.insert("data");
    for (const auto& item : config.beat_fields) available.insert(item.first);
    for (const auto& item : config.packet_stable_fields) available.insert(item.first);

    const Json fields = filter_json.value("fields", Json::object());
    if (!fields.is_object() || fields.empty()) {
        error = "filter.fields must be a non-empty object";
        invalid_arg = "args.filter.fields";
        return false;
    }
    for (auto it = fields.begin(); it != fields.end(); ++it) {
        const std::string field = it.key();
        const std::string base = "args.filter.fields." + field;
        if (available.find(field) == available.end()) {
            error = "stream filter field is not configured: " + field;
            invalid_arg = base;
            return false;
        }
        const Json& spec = it.value();
        ValueFilter parsed;
        ValueFilterError parse_error;
        ValueFilterParseOptions parse_options;
        if (!xdebug_waveform::parse_value_filter(spec, base, parse_options,
                                                 parsed, parse_error)) {
            error = parse_error.message;
            invalid_arg = parse_error.invalid_arg;
            return false;
        }
        options.filter.fields[field] = std::move(parsed);
    }
    return true;
}
bool parse_time_arg(const std::string& text, bool allow_max, npiFsdbTime& out, std::string& error) {
    if (text.empty()) {
        out = 0;
        return true;
    }
    xdebug_core::TimeParseOptions options;
    options.allow_max = allow_max;
    options.use_fsdb_max = true;
    options.default_unit = "ns";
    return xdebug_core::parse_time(g_fsdb_file, text, options, out, error);
}
bool range_from_args(const Json& args, const Json& limits, StreamQueryOptions& options, std::string& error) {
    npiFsdbTime min_t = 0, max_t = 0;
    npi_fsdb_min_time(g_fsdb_file, &min_t);
    npi_fsdb_max_time(g_fsdb_file, &max_t);
    Json tr = args.value("time_range", Json::object());
    std::string start = tr.value("begin", std::string());
    std::string end = tr.value("end", std::string("max"));
    if (start.empty()) options.begin = min_t;
    else if (!parse_time_arg(start, false, options.begin, error)) return false;
    if (end.empty() || end == "max") options.end = max_t;
    else if (!parse_time_arg(end, true, options.end, error)) return false;
    options.limit = args.value("line_limit", 32);
    if (options.limit <= 0) options.limit = 32;
    options.channel_filter = args.value("channel", std::string());
    return true;
}
Json rows_limited(const std::vector<xdebug_waveform::StreamRow>& rows, int limit) {
    Json arr = Json::array();
    for (size_t i = 0; i < rows.size() && static_cast<int>(i) < limit; ++i) {
        arr.push_back(xdebug_waveform::stream_row_json(rows[i]));
    }
    return arr;
}
Json stalls_limited(const std::vector<xdebug_waveform::StreamStallWindow>& stalls, int limit) {
    Json arr = Json::array();
    for (size_t i = 0; i < stalls.size() && static_cast<int>(i) < limit; ++i) {
        arr.push_back(xdebug_waveform::stream_stall_json(stalls[i]));
    }
    return arr;
}
Json packets_limited(const std::vector<xdebug_waveform::StreamPacket>& packets, int limit) {
    Json arr = Json::array();
    for (size_t i = 0; i < packets.size() && static_cast<int>(i) < limit; ++i) {
        arr.push_back(xdebug_waveform::stream_packet_json(packets[i]));
    }
    return arr;
}
bool get_config(const Json& args, StreamConfig& config, Json& fail) {
    std::string name = args.value("stream", args.value("name", std::string()));
    if (name.empty()) {
        fail = stream_name_error("stream.query", name);
        return false;
    }
    StreamManager manager;
    if (!manager.get_stream(xdebug_waveform::g_session_id, name, config)) {
        fail = stream_name_error("stream.query", name);
        return false;
    }
    return true;
}

class StreamQueryHandler : public EngineActionHandler {
public:
    const char* action_name() const override { return "stream.query"; }
    bool needs_design() const override { return false; }
    bool needs_waveform() const override { return true; }
    Json run(const Json& request, EngineActionContext& ctx) const override {
        Json args = request.value("args", Json::object());
        Json fail;
        StreamConfig config;
        if (!get_config(args, config, fail)) return fail;
        StreamQueryOptions options;
        std::string error;
        const std::string cache_scope =
            args.value("cache_scope", std::string("full"));
        if (cache_scope != "full" && cache_scope != "range")
            return err("INVALID_ENUM", "cache_scope must be full or range",
                       {{"invalid_arg", "args.cache_scope"},
                        {"expected", "one of full, range"},
                        {"allowed_values", Json::array({"full", "range"})},
                        {"correct_example", stream_query_example(config.name)}});
        if (!range_from_args(args, request.value("limits", Json::object()), options, error))
            return stream_time_error(error);
        std::string query = args.value("query", std::string("summary"));
        options.query_kind = query;
        options.packet_index = args.value("packet_index", -1);
        if (args.contains("filter")) {
            std::string invalid_arg;
            if (!parse_stream_filter(args["filter"], config, options, error, invalid_arg))
                return stream_filter_error(config.name, error, invalid_arg);
            const bool packet_enabled = xdebug_waveform::stream_packet_enabled(config);
            const std::set<std::string> allowed = packet_enabled
                ? std::set<std::string>{"summary", "first_packet", "last_packet", "packet_window"}
                : std::set<std::string>{"summary", "first_transfer", "last_transfer", "transfer_window"};
            if (allowed.find(query) == allowed.end()) {
                return stream_filter_error(
                    config.name,
                    packet_enabled
                        ? "packet stream filters support summary, first_packet, last_packet, or packet_window"
                        : "beat stream filters support summary, first_transfer, last_transfer, or transfer_window",
                    "args.query");
            }
        }
        StreamAnalysis analysis;
        if (!analyze_stream_cached_with_legacy_differential(
                xdebug_waveform::g_stream_analyzer, g_fsdb_file, config,
                options,
                cache_scope == "range" ? AnalysisCacheScope::Range
                                       : AnalysisCacheScope::Full,
                analysis, error)) {
            if (!xdebug_waveform::g_stream_analyzer.last_cache_error().empty())
                return make_analysis_cache_error(
                    xdebug_waveform::g_stream_analyzer.last_cache_error());
            return stream_analyze_error(error);
        }

        Json out;
        out["summary"] = xdebug_waveform::stream_summary_json(config, analysis);
        out["summary"]["query"] = query;
        if (options.filter.enabled) {
            out["summary"]["filter_applied"] = true;
            out["summary"]["unresolved_filter_count"] = analysis.unresolved_filter_count;
            if (xdebug_waveform::stream_packet_enabled(config))
                out["summary"]["matched_packet_count"] = analysis.matched_packet_count;
            else
                out["summary"]["matched_transfer_count"] = analysis.matched_transfer_count;
            if (xdebug_waveform::stream_packet_enabled(config)) {
                out["summary"]["retained_packet_count"] = analysis.packets.size();
                if (analysis.truncated)
                    out["summary"]["truncation_scope"] = "response_packets";
            }
            out["filter"] = args["filter"];
            out["notes"] = {{"unresolved_filter_count",
                "因所选 SOP/EOP 边界未出现在查询窗口内，或被引用字段的有效比较位含 X/Z，导致无法判断是否匹配的 transfer/packet 数；mask 为 0 的位不影响判断。"}};
        } else {
            out["summary"]["filter_applied"] = false;
        }
        out["hint"] = analysis.truncated
            ? (options.filter.enabled
                ? "narrow filter/time_range or increase line_limit"
                : "use stream.export for large result")
            : "";
        if (query == "summary") return out;
        if (query == "first_transfer" || query == "last_transfer") {
            out["summary"].erase(query == "first_transfer" ? "first_transfer_time" : "last_transfer_time");
            if (analysis.has_transfer_evidence) {
                out["row"] = xdebug_waveform::stream_row_json(
                    query == "first_transfer" ? analysis.first_transfer : analysis.last_transfer);
            }
            return out;
        }
        if (query == "transfer_window") {
            out["rows"] = rows_limited(analysis.transfers, options.limit);
            return out;
        }
        if (query == "first_stall" || query == "last_stall") {
            out["summary"].erase(query == "first_stall" ? "first_stall_time" : "last_stall_time");
            if (!analysis.stalls.empty()) {
                out["stall"] = xdebug_waveform::stream_stall_json(
                    query == "first_stall" ? analysis.stalls.front() : analysis.stalls.back());
            }
            return out;
        }
        if (query == "stall_window") {
            out["stalls"] = stalls_limited(analysis.stalls, options.limit);
            return out;
        }
        if (query == "first_packet" || query == "last_packet") {
            const bool found = options.filter.enabled
                ? analysis.has_matched_packet_evidence : !analysis.packets.empty();
            out["found"] = found;
            if (found) {
                out["packet"] = xdebug_waveform::stream_packet_json(
                    options.filter.enabled
                        ? (query == "first_packet" ? analysis.first_matched_packet
                                                    : analysis.last_matched_packet)
                        : (query == "first_packet" ? analysis.packets.front()
                                                    : analysis.packets.back()));
            } else {
                out["packet"] = nullptr;
            }
            return out;
        }
        if (query == "packet_at") {
            int packet_index = args.value("packet_index", -1);
            out["found"] = false;
            out["packet"] = nullptr;
            if (packet_index < 0) {
                Json example = stream_query_example(config.name, "packet_at");
                example["args"]["packet_index"] = 0;
                return err("INVALID_ARGUMENT", "packet_index must be >= 0",
                           {{"invalid_arg", "args.packet_index"},
                            {"expected", "integer >= 0"},
                            {"received", packet_index},
                            {"correct_example", example},
                            {"example_note", "Example only; replace stream name and packet_index with the target packet."}});
            }
            for (const auto& packet : analysis.packets) {
                if (packet.packet_index == packet_index) {
                    out["found"] = true;
                    out["packet"] = xdebug_waveform::stream_packet_json(packet);
                    break;
                }
            }
            return out;
        }
        if (query == "packet_window") {
            out["packets"] = packets_limited(analysis.packets, options.limit);
            const int available_count = options.filter.enabled
                ? analysis.matched_packet_count
                : analysis.complete_packet_count + analysis.partial_packet_count;
            if (available_count > options.limit) {
                out["summary"]["truncated"] = true;
                out["summary"]["truncation_scope"] = "response_packets";
            }
            return out;
        }
        return err("INVALID_ENUM", "unsupported stream.query type: " + query,
                   {{"invalid_arg", "args.query"},
                    {"expected", "one of summary, first_transfer, last_transfer, transfer_window, first_stall, last_stall, stall_window, first_packet, last_packet, packet_at, packet_window"},
                    {"allowed_values", Json::array({"summary", "first_transfer", "last_transfer", "transfer_window",
                                                     "first_stall", "last_stall", "stall_window", "first_packet",
                                                     "last_packet", "packet_at", "packet_window"})},
                    {"correct_example", stream_query_example(config.name, "summary")},
                    {"example_note", "Example only; choose one query kind from allowed_values."}});
    }
};

}  // namespace

std::unique_ptr<EngineActionHandler> make_stream_query_handler() {
    return std::unique_ptr<EngineActionHandler>(new StreamQueryHandler);
}

}  // namespace xdebug_design
