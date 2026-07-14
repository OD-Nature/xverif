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
Json stream_export_example(const std::string& stream = "req_stream",
                           const std::string& kind = "transfer") {
    return Json{{"api_version", "xdebug.v1"},
                {"action", "stream.export"},
                {"target", {{"session_id", "case_a"}}},
                {"args", {{"stream", stream},
                          {"kind", kind},
                          {"output", {{"path", "/tmp/stream.tsv"}, {"file_format", "tsv"}}}}}};
}
Json stream_name_error(const std::string& name) {
    Json details = {{"invalid_arg", "args.stream"},
                    {"expected", "name of a previously loaded stream config"},
                    {"correct_example", stream_export_example()},
                    {"example_note", "Example only; replace target.session_id, args.stream, and output.path with the active case values."},
                    {"next_actions", Json::array({"Call stream.config.list to inspect loaded stream names.",
                                                   "Call stream.config.load before exporting a stream."})}};
    if (!name.empty()) {
        details["missing_name"] = name;
        details["missing_resource"] = "stream config";
    }
    return err(name.empty() ? "MISSING_FIELD" : "CONFIG_NOT_FOUND",
               name.empty() ? "args.stream is required" : "stream config not found: " + name,
               details);
}
size_t row_count_for_kind(const StreamAnalysis& analysis, const std::string& kind) {
    if (kind == "packet") return analysis.packets.size();
    if (kind == "packet_beats") return analysis.transfer_count;
    return analysis.transfers.size();
}
Json preview_for_kind(const StreamAnalysis& analysis, const std::string& kind, int line_limit) {
    Json rows = Json::array();
    int limit = line_limit > 0 ? line_limit : 16;
    if (kind == "packet") {
        for (size_t i = 0; i < analysis.packets.size() && static_cast<int>(i) < limit; ++i)
            rows.push_back(xdebug_waveform::stream_packet_json(analysis.packets[i]));
    } else {
        for (size_t i = 0; i < analysis.transfers.size() && static_cast<int>(i) < limit; ++i)
            rows.push_back(xdebug_waveform::stream_row_json(analysis.transfers[i]));
    }
    return rows;
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
                {"correct_example", stream_export_example()},
                {"example_note", "Example only; omit time_range for full waveform or use begin/end strings with units."},
                {"next_actions", Json::array({"Fix args.time_range.begin/end to include a valid unit.",
                                               "Omit args.time_range to export the whole waveform window."})}});
}
Json stream_analyze_error(const std::string& message) {
    return err(code_for_stream_error(message, "ACTION_FAILED"), message,
               {{"cause_code", "STREAM_ANALYZE_FAILED"},
                {"expected", "loaded stream config whose aliased signal paths exist in the active FSDB"},
                {"correct_example", stream_export_example()},
                {"next_actions", Json::array({"Call stream.show to inspect config signal aliases.",
                                               "Call stream.validate before exporting large stream results."})}});
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
bool get_config(const Json& args, StreamConfig& config, Json& fail) {
    std::string name = args.value("stream", args.value("name", std::string()));
    if (name.empty()) {
        fail = stream_name_error(name);
        return false;
    }
    StreamManager manager;
    if (!manager.get_stream(xdebug_waveform::g_session_id, name, config)) {
        fail = stream_name_error(name);
        return false;
    }
    return true;
}

class StreamExportHandler : public EngineActionHandler {
public:
    const char* action_name() const override { return "stream.export"; }
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
        options.limit = 0;
        StreamAnalyzer analyzer;
        StreamAnalysis analysis;
        if (!analyzer.analyze(g_fsdb_file, config, options, analysis, error))
            return stream_analyze_error(error);
        std::string kind = args.value("kind", std::string("transfer"));
        Json output_arg = args.value("output", Json::object());
        std::string format = output_arg.value("file_format", std::string("tsv"));
        if (format != "tsv" && format != "csv" && format != "xout")
            return err("INVALID_ENUM", "output.file_format must be tsv, csv, or xout",
                       {{"invalid_arg", "args.output.file_format"},
                        {"expected", "one of tsv, csv, xout"},
                        {"allowed_values", Json::array({"tsv", "csv", "xout"})},
                        {"correct_example", stream_export_example(config.name)},
                        {"example_note", "Example only; output.file_format controls exported file content, not MCP output_format."}});
        std::string output = output_arg.value("path", std::string());
        if (!output.empty() && args.contains("line_limit"))
            return err("INVALID_REQUEST",
                       "stream.export args.line_limit only controls preview rows and is not valid for file export",
                       {{"invalid_arg", "args.line_limit"},
                        {"expected", "omit line_limit when args.output.path is present"}});
        size_t row_count = row_count_for_kind(analysis, kind);
        Json summary = xdebug_waveform::stream_summary_json(config, analysis);
        summary["status"] = output.empty() ? "preview" : "written";
        summary["output_written"] = !output.empty();
        summary["row_count"] = row_count;
        summary["line_limit"] = args.value("line_limit", 16);
        summary["truncated"] = analysis.truncated ||
            (output.empty() && static_cast<int>(row_count) > summary["line_limit"].get<int>());
        summary["kind"] = kind;
        if (output.empty()) {
            return Json{{"summary", summary},
                        {"preview", preview_for_kind(analysis, kind, summary["line_limit"].get<int>())}};
        }
        std::string meta;
        StreamExporter exporter;
        bool ok = false;
        if (kind == "packet") ok = exporter.export_packet_file(output, format, config, analysis, meta, error);
        else if (kind == "packet_beats") ok = exporter.export_packet_beats_file(output, format, config, analysis, meta, error);
        else if (kind == "transfer") ok = exporter.export_transfer_file(output, format, config, analysis, meta, error);
        else return err("INVALID_ENUM", "kind must be transfer, packet, or packet_beats",
                        {{"invalid_arg", "args.kind"},
                         {"expected", "one of transfer, packet, packet_beats"},
                         {"allowed_values", Json::array({"transfer", "packet", "packet_beats"})},
                         {"correct_example", stream_export_example(config.name, "transfer")},
                         {"example_note", "Example only; choose kind from allowed_values."}});
        if (!ok) return err("ACTION_FAILED", error,
                            {{"cause_code", "EXPORT_FAILED"},
                             {"invalid_arg", "args.output.path"},
                             {"expected", "writable output path"},
                             {"correct_example", stream_export_example(config.name, kind)}});
        Json output_info = {{"path", output}, {"meta_path", meta}, {"file_format", format}};
        summary["output"] = output_info;
        return Json{{"summary", summary}};
    }
};

}  // namespace

std::unique_ptr<EngineActionHandler> make_stream_export_handler() {
    return std::unique_ptr<EngineActionHandler>(new StreamExportHandler);
}

}  // namespace xdebug_design
