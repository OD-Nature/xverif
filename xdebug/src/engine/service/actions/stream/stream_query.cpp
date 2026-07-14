#include "service/engine_action_handler.h"
#include "service/engine_action_registry.h"
#include "service/engine_globals.h"

#include "waveform/common/xdebug_waveform_paths.h"
#include "waveform/stream/stream_analyzer.h"
#include "waveform/stream/stream_exporter.h"
#include "waveform/stream/stream_manager.h"
#include "core/npi/time_contract.h"

#include "npi_fsdb.h"
#include "npi_L1.h"

#include <ctime>
#include <memory>
#include <sstream>
#include <sys/stat.h>

namespace xdebug_design {
namespace {

using xdebug_waveform::Json;
using xdebug_waveform::StreamAnalysis;
using xdebug_waveform::StreamAnalyzer;
using xdebug_waveform::StreamConfig;
using xdebug_waveform::StreamExporter;
using xdebug_waveform::StreamManager;
using xdebug_waveform::StreamMatch;
using xdebug_waveform::StreamQueryOptions;

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
Json stream_match_error(const std::string& stream,
                        const std::string& query,
                        const std::string& message) {
    Json example = stream_query_example(stream, query);
    example["args"]["match"] = {{"field", "opcode"}, {"op", "=="}, {"value", "8'h5a"}};
    return err(code_for_stream_error(message, "INVALID_ARGUMENT"), message,
               {{"invalid_arg", "args.match.value"},
                {"expected", "match literal compatible with the selected stream field"},
                {"correct_example", example},
                {"example_note", "Example only; choose a field from stream.show and use a SystemVerilog-style value literal."}});
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
        if (!range_from_args(args, request.value("limits", Json::object()), options, error))
            return stream_time_error(error);
        std::string query = args.value("query", std::string("summary"));
        // Exact field matching still retains all transfer rows. Other query
        // modes retain bounded response evidence while aggregates and
        // first/last evidence continue across the full scan.
        if (query == "match_field") options.retain_limit = -1;
        StreamAnalyzer analyzer;
        StreamAnalysis analysis;
        if (!analyzer.analyze(g_fsdb_file, config, options, analysis, error))
            return stream_analyze_error(error);

        Json out;
        out["summary"] = xdebug_waveform::stream_summary_json(config, analysis);
        out["summary"]["query"] = query;
        out["hint"] = analysis.truncated ? "use stream.export for large result" : "";
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
            out["found"] = !analysis.packets.empty();
            if (!analysis.packets.empty()) {
                out["packet"] = xdebug_waveform::stream_packet_json(
                    query == "first_packet" ? analysis.packets.front() : analysis.packets.back());
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
            if (static_cast<int>(analysis.packets.size()) > options.limit) {
                out["summary"]["truncated"] = true;
                out["summary"]["truncation_scope"] = "response_packets";
            }
            return out;
        }
        if (query == "match_field") {
            Json m = args.value("match", Json::object());
            StreamMatch match;
            match.field = m.value("field", std::string());
            match.op = m.value("op", std::string("=="));
            match.value = m.value("value", std::string());
            match.lo = m.value("lo", std::string());
            match.hi = m.value("hi", std::string());
            match.mask = m.value("mask", std::string());
            match.field_scope = m.value("field_scope", args.value("field_scope", std::string("any")));
            if (match.field_scope.empty()) match.field_scope = "any";
            if (match.field_scope != "beat" && match.field_scope != "stable" && match.field_scope != "any")
                return err("INVALID_ENUM", "field_scope must be beat, stable, or any",
                           {{"invalid_arg", m.contains("field_scope") ? "args.match.field_scope" : "args.field_scope"},
                            {"expected", "one of beat, stable, any"},
                            {"allowed_values", Json::array({"beat", "stable", "any"})},
                            {"correct_example", stream_query_example(config.name, "match_field")},
                            {"example_note", "Example only; put field_scope under args.match for match_field queries."}});
            if (match.field.empty()) {
                Json example = stream_query_example(config.name, "match_field");
                example["args"]["match"] = {{"field", "opcode"}, {"op", "=="}, {"value", "8'h5a"}};
                return err("MISSING_FIELD", "match.field is required",
                           {{"invalid_arg", "args.match.field"},
                            {"expected", "field name defined by the loaded stream config"},
                            {"correct_example", example},
                            {"example_note", "Example only; replace opcode/value with a field from stream.show."},
                            {"next_actions", Json::array({"Call stream.show to inspect available fields."})}});
            }
            if (match.field_scope == "stable") {
                Json packets = Json::array();
                for (const auto& packet : analysis.packets) {
                    xdebug_waveform::StreamRow pseudo;
                    pseudo.stable_fields = packet.stable_fields;
                    std::string match_error;
                    if (analyzer.match_row(pseudo, match, match_error)) packets.push_back(xdebug_waveform::stream_packet_json(packet));
                    else if (!match_error.empty())
                        return stream_match_error(config.name, "match_field", match_error);
                    if (static_cast<int>(packets.size()) >= options.limit) break;
                }
                out["packets"] = packets;
                out["summary"]["match_count"] = packets.size();
                out["summary"]["field_scope"] = match.field_scope;
                return out;
            }
            Json rows = Json::array();
            for (const auto& row : analysis.transfers) {
                std::string match_error;
                if (analyzer.match_row(row, match, match_error)) rows.push_back(xdebug_waveform::stream_row_json(row));
                else if (!match_error.empty())
                    return stream_match_error(config.name, "match_field", match_error);
                if (static_cast<int>(rows.size()) >= options.limit) break;
            }
            out["rows"] = rows;
            out["summary"]["match_count"] = rows.size();
            out["summary"]["field_scope"] = match.field_scope;
            return out;
        }
        return err("INVALID_ENUM", "unsupported stream.query type: " + query,
                   {{"invalid_arg", "args.query"},
                    {"expected", "one of summary, first_transfer, last_transfer, transfer_window, first_stall, last_stall, stall_window, first_packet, last_packet, packet_at, packet_window, match_field"},
                    {"allowed_values", Json::array({"summary", "first_transfer", "last_transfer", "transfer_window",
                                                     "first_stall", "last_stall", "stall_window", "first_packet",
                                                     "last_packet", "packet_at", "packet_window", "match_field"})},
                    {"correct_example", stream_query_example(config.name, "summary")},
                    {"example_note", "Example only; choose one query kind from allowed_values."}});
    }
};

}  // namespace

std::unique_ptr<EngineActionHandler> make_stream_query_handler() {
    return std::unique_ptr<EngineActionHandler>(new StreamQueryHandler);
}

}  // namespace xdebug_design
