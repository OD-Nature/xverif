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
Json issue_json(const std::vector<xdebug_waveform::StreamValidationIssue>& issues) {
    Json arr = Json::array();
    for (const auto& issue : issues) {
        arr.push_back({{"severity", issue.severity}, {"code", issue.code}, {"message", issue.message}});
    }
    return arr;
}
void add_issue(std::vector<xdebug_waveform::StreamValidationIssue>& issues,
               const std::string& severity,
               const std::string& code,
               const std::string& message) {
    issues.push_back(xdebug_waveform::StreamValidationIssue{severity, code, message});
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

class StreamValidateHandler : public EngineActionHandler {
public:
    const char* action_name() const override { return "stream.validate"; }
    bool needs_design() const override { return false; }
    bool needs_waveform() const override { return true; }
    Json run(const Json& request, EngineActionContext& ctx) const override {
        Json args = request.value("args", Json::object());
        Json fail;
        StreamConfig config;
        if (!get_config(args, config, fail)) return fail;
        StreamAnalyzer analyzer;
        std::vector<xdebug_waveform::StreamValidationIssue> issues;
        std::string error;
        bool static_ok = analyzer.validate_static(g_fsdb_file, config, issues, error);

        bool dynamic = args.value("dynamic", true);
        Json dyn = Json::object();
        if (static_ok && dynamic) {
            StreamQueryOptions options;
            if (!range_from_args(args, request.value("limits", Json::object()), options, error))
                return err("TIME_SPEC_INVALID", error);
            options.limit = args.value("max_edges", 256);
            StreamAnalysis analysis;
            if (!analyzer.analyze(g_fsdb_file, config, options, analysis, error))
                return err(code_for_stream_error(error, "STREAM_ANALYZE_FAILED"), error);
            if (analysis.vld_cycles == 0) add_issue(issues, "WARNING", "VLD_NEVER_TRUE", "vld was never true in validation window");
            if (analysis.transfer_count == 0) add_issue(issues, "WARNING", "NO_TRANSFER", "no transfer observed in validation window");
            if (analysis.ready_bp_conflict_count > 0) add_issue(issues, "WARNING", "READY_BP_CONFLICT", "observed vld=1,rdy=1,bp=1");
            if (analysis.stable_mismatch_count > 0) add_issue(issues, "WARNING", "STABLE_FIELD_MISMATCH", "observed stable_fields changing within packet");
            dyn = xdebug_waveform::stream_summary_json(config, analysis);
        }
        bool has_error = false;
        for (const auto& issue : issues) if (issue.severity == "ERROR") has_error = true;
        return Json{{"summary", {{"stream", config.name}, {"ok", !has_error}}},
                    {"issues", issue_json(issues)}, {"dynamic", dyn}};
    }
};

}  // namespace

std::unique_ptr<EngineActionHandler> make_stream_validate_handler() {
    return std::unique_ptr<EngineActionHandler>(new StreamValidateHandler);
}

}  // namespace xdebug_design
