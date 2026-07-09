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

Json err(const std::string& code, const std::string& message) {
    return Json{{"error", code}, {"message", message}};
}
std::string code_for_stream_error(const std::string& message, const std::string& fallback) {
    return message.find("0x prefix is not accepted") != std::string::npos ||
           message.find("invalid value literal") != std::string::npos
        ? "VALUE_FORMAT_INVALID"
        : fallback;
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
    std::string start = args.value("start", args.value("begin", tr.value("begin", std::string())));
    std::string end = args.value("end", tr.value("end", std::string("max")));
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
        fail = err("MISSING_FIELD", "args.stream is required");
        return false;
    }
    StreamManager manager;
    if (!manager.get_stream(xdebug_waveform::g_session_id, name, config)) {
        fail = err("STREAM_NOT_FOUND", "stream config not found: " + name);
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
            return err("TIME_SPEC_INVALID", error);
        options.limit = 0;
        StreamAnalyzer analyzer;
        StreamAnalysis analysis;
        if (!analyzer.analyze(g_fsdb_file, config, options, analysis, error))
            return err(code_for_stream_error(error, "STREAM_ANALYZE_FAILED"), error);
        std::string kind = args.value("kind", std::string("transfer"));
        std::string format = args.value("format", std::string("tsv"));
        if (format != "tsv" && format != "csv" && format != "xout") return err("INVALID_REQUEST", "format must be tsv, csv, or xout");
        Json output_arg = args.value("output", Json::object());
        std::string output = output_arg.value("path", std::string());
        if (kind == "packet_beats" && output.empty()) return err("MISSING_FIELD", "packet_beats export requires output.path");
        if (output.empty()) {
            std::ostringstream oss;
            oss << xdebug_waveform::xdebug_waveform_stream_exports_dir(xdebug_waveform::g_session_id)
                << "/" << config.name << "_" << kind << "_" << std::time(nullptr)
                << (format == "csv" ? ".csv" : ".tsv");
            output = oss.str();
        }
        std::string meta;
        StreamExporter exporter;
        bool ok = false;
        if (kind == "packet") ok = exporter.export_packet_file(output, format, config, analysis, meta, error);
        else if (kind == "packet_beats") ok = exporter.export_packet_beats_file(output, format, config, analysis, meta, error);
        else if (kind == "transfer") ok = exporter.export_transfer_file(output, format, config, analysis, meta, error);
        else return err("INVALID_REQUEST", "kind must be transfer, packet, or packet_beats");
        if (!ok) return err("EXPORT_FAILED", error);
        return Json{{"summary", xdebug_waveform::stream_summary_json(config, analysis)},
                    {"output_file", output}, {"meta_file", meta}, {"kind", kind},
                    {"format", format}, {"row_count", kind == "transfer" ? analysis.transfers.size() :
                        kind == "packet" ? analysis.packets.size() : analysis.transfer_count}};
    }
};

}  // namespace

std::unique_ptr<EngineActionHandler> make_stream_export_handler() {
    return std::unique_ptr<EngineActionHandler>(new StreamExportHandler);
}

}  // namespace xdebug_design
