#include "service/engine_action_handler.h"
#include "service/engine_action_registry.h"
#include "service/engine_globals.h"

#include "waveform/common/xdebug_waveform_paths.h"
#include "waveform/stream/legacy_stream_analyzer_adapter.h"
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
using xdebug_waveform::analyze_stream_cached_with_legacy_differential;
using xdebug_waveform::AnalysisCacheScope;
using xdebug_waveform::StreamAnalysis;
using xdebug_waveform::StreamAnalyzer;
using xdebug_waveform::StreamConfig;
using xdebug_waveform::StreamExporter;
using xdebug_waveform::StreamManager;
using xdebug_waveform::StreamQueryOptions;

Json err(const std::string& code, const std::string& message, const Json& details) {
    return make_handler_error(code, message, details);
}
Json stream_validate_example(const std::string& stream = "req_stream") {
    return Json{{"api_version", "xdebug.v1"},
                {"action", "stream.validate"},
                {"target", {{"session_id", "case_a"}}},
                {"args", {{"stream", stream}, {"dynamic", true}}}};
}
Json stream_name_error(const std::string& name) {
    Json details = {{"invalid_arg", "args.stream"},
                    {"expected", "name of a previously loaded stream config"},
                    {"correct_example", stream_validate_example()},
                    {"example_note", "Example only; replace target.session_id and args.stream with active case values."},
                    {"next_actions", Json::array({"Call stream.config.list to inspect loaded stream names.",
                                                   "Call stream.config.load before validating a stream."})}};
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
                {"correct_example", stream_validate_example()},
                {"example_note", "Example only; omit time_range for full waveform or use begin/end strings with units."},
                {"next_actions", Json::array({"Fix args.time_range.begin/end to include a valid unit.",
                                               "Omit args.time_range to validate the whole waveform window."})}});
}
Json stream_analyze_error(const std::string& message) {
    return err(code_for_stream_error(message, "ACTION_FAILED"), message,
               {{"cause_code", "STREAM_ANALYZE_FAILED"},
                {"expected", "loaded stream config whose aliased signal paths exist in the active FSDB"},
                {"correct_example", stream_validate_example()},
                {"next_actions", Json::array({"Call stream.show to inspect config signal aliases.",
                                               "Call stream.config.load again after fixing signal paths."})}});
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
        const bool dynamic = args.value("dynamic", true);
        if (!dynamic && args.contains("cache_scope")) {
            Json example = stream_validate_example(config.name);
            example["args"].erase("cache_scope");
            return err(
                "INVALID_ARGUMENT",
                "cache_scope is only valid when stream.validate dynamic=true",
                {{"invalid_arg", "args.cache_scope"},
                 {"expected", "omit cache_scope for static validation"},
                 {"correct_example", example}});
        }
        const std::string cache_scope =
            args.value("cache_scope", std::string("full"));
        if (cache_scope != "full" && cache_scope != "range")
            return err("INVALID_ENUM", "cache_scope must be full or range",
                       {{"invalid_arg", "args.cache_scope"},
                        {"expected", "one of full, range"},
                        {"allowed_values", Json::array({"full", "range"})},
                        {"correct_example", stream_validate_example(config.name)}});
        StreamAnalyzer analyzer;
        std::vector<xdebug_waveform::StreamValidationIssue> issues;
        std::string error;
        bool static_ok = analyzer.validate_static(g_fsdb_file, config, issues, error);

        Json dyn = Json::object();
        bool dynamic_complete = !dynamic;
        if (static_ok && dynamic) {
            StreamQueryOptions options;
            if (!range_from_args(args, request.value("limits", Json::object()), options, error))
                return stream_time_error(error);
            options.limit = args.value("line_limit", 256);
            options.query_kind = "validate";
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
            if (analysis.vld_cycles == 0) add_issue(issues, "WARNING", "VLD_NEVER_TRUE", "vld was never true in validation window");
            if (analysis.transfer_count == 0) add_issue(issues, "WARNING", "NO_TRANSFER", "no transfer observed in validation window");
            if (analysis.ready_bp_conflict_count > 0) add_issue(issues, "WARNING", "READY_BP_CONFLICT", "observed vld=1,rdy=1,bp=1");
            if (analysis.packet_stable_mismatch_count > 0) add_issue(issues, "WARNING", "PACKET_STABLE_FIELD_MISMATCH", "observed packet_stable_fields changing within packet");
            dyn = xdebug_waveform::stream_summary_json(config, analysis);
            dynamic_complete = analysis.analysis_complete;
        }
        bool has_error = false;
        for (const auto& issue : issues) if (issue.severity == "ERROR") has_error = true;
        return Json{{"summary", {{"stream", config.name}, {"ok", !has_error},
                                  {"static_validation_complete", true},
                                  {"dynamic_requested", dynamic},
                                  {"validation_complete", static_ok && dynamic_complete}}},
                    {"issues", issue_json(issues)}, {"dynamic", dyn}};
    }
};

}  // namespace

std::unique_ptr<EngineActionHandler> make_stream_validate_handler() {
    return std::unique_ptr<EngineActionHandler>(new StreamValidateHandler);
}

}  // namespace xdebug_design
