#include "engine_action_handler.h"
#include "engine_action_registry.h"
#include "engine_globals.h"

#include "../../waveform/common/xdebug_waveform_paths.h"
#include "../../waveform/stream/stream_analyzer.h"
#include "../../waveform/stream/stream_exporter.h"
#include "../../waveform/stream/stream_manager.h"

#include "npi_fsdb.h"
#include "npi_L1.h"

#include <ctime>
#include <cctype>
#include <cstdlib>
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
    if (allow_max && text == "max") {
        return npi_fsdb_max_time(g_fsdb_file, &out) != 0;
    }
    double value = 0;
    char* end = nullptr;
    value = std::strtod(text.c_str(), &end);
    if (!end || end == text.c_str()) {
        error = "invalid time: " + text;
        return false;
    }
    while (*end && std::isspace(static_cast<unsigned char>(*end))) ++end;
    std::string unit = *end ? std::string(end) : "ns";
    if (!npi_fsdb_convert_time_in(g_fsdb_file, value, unit.c_str(), out)) {
        error = "failed to convert time: " + text;
        return false;
    }
    return true;
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
    options.limit = args.value("limit", limits.value("max_rows", limits.value("max_items", 32)));
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

class StreamConfigLoadHandler : public EngineActionHandler {
public:
    const char* action_name() const override { return "stream.config.load"; }
    bool needs_design() const override { return false; }
    bool needs_waveform() const override { return true; }
    Json run(const Json& request) const override {
        Json args = request.value("args", Json::object());
        Json root;
        std::string error;
        if (!xdebug_waveform::load_stream_config_arg(args, root, error)) return err("INVALID_REQUEST", error);
        std::vector<StreamConfig> streams;
        if (!xdebug_waveform::parse_stream_config_list(root, streams, error)) return err("INVALID_REQUEST", error);

        StreamAnalyzer analyzer;
        Json validation = Json::array();
        for (const auto& stream : streams) {
            std::vector<xdebug_waveform::StreamValidationIssue> issues;
            std::string validate_error;
            analyzer.validate_static(g_fsdb_file, stream, issues, validate_error);
            for (const auto& issue : issues) validation.push_back(
                {{"stream", stream.name}, {"severity", issue.severity},
                 {"code", issue.code}, {"message", issue.message}});
            for (const auto& issue : issues) {
                if (issue.severity == "ERROR") return err("INVALID_REQUEST", issue.message);
            }
        }

        std::string mode = args.value("mode", std::string("replace"));
        StreamManager manager;
        if (!manager.load_configs(xdebug_waveform::g_session_id, streams, mode, error))
            return err("INVALID_REQUEST", error);
        Json out;
        out["summary"] = {{"loaded", streams.size()}, {"mode", mode}};
        out["streams"] = Json::array();
        for (const auto& stream : streams) out["streams"].push_back(stream.name);
        out["issues"] = validation;
        return out;
    }
};

class StreamConfigListHandler : public EngineActionHandler {
public:
    const char* action_name() const override { return "stream.config.list"; }
    bool needs_design() const override { return false; }
    bool needs_waveform() const override { return true; }
    Json run(const Json& request) const override {
        bool verbose = request.value("args", Json::object()).value("verbose", false);
        StreamManager manager;
        auto streams = manager.list_streams(xdebug_waveform::g_session_id);
        Json arr = Json::array();
        for (const auto& stream : streams) {
            if (verbose) arr.push_back(xdebug_waveform::stream_config_json(stream));
            else arr.push_back({{"name", stream.name}, {"clock", stream.clock},
                                {"clock_edge", stream.posedge ? "posedge" : "negedge"},
                                {"handshake", xdebug_waveform::stream_handshake_text(stream)},
                                {"packet", xdebug_waveform::stream_packet_enabled(stream) ? "sop/eop" : "none"},
                                {"field_count", stream.data_fields.size() + stream.beat_fields.size() +
                                    stream.stable_fields.size() + (stream.data.empty() ? 0 : 1)},
                                {"channel_id_valid", stream.channel_id_valid},
                                {"allow_interleaving", stream.allow_interleaving}});
        }
        return Json{{"summary", {{"count", streams.size()}}}, {"streams", arr}};
    }
};

class StreamShowHandler : public EngineActionHandler {
public:
    const char* action_name() const override { return "stream.show"; }
    bool needs_design() const override { return false; }
    bool needs_waveform() const override { return true; }
    Json run(const Json& request) const override {
        Json fail;
        StreamConfig config;
        if (!get_config(request.value("args", Json::object()), config, fail)) return fail;
        StreamAnalyzer analyzer;
        std::vector<xdebug_waveform::StreamValidationIssue> issues;
        std::string error;
        analyzer.validate_static(g_fsdb_file, config, issues, error);
        Json out;
        out["summary"] = {{"stream", config.name}, {"handshake", xdebug_waveform::stream_handshake_text(config)},
                          {"packet_enabled", xdebug_waveform::stream_packet_enabled(config)}};
        out["config"] = xdebug_waveform::stream_config_json(config);
        out["issues"] = issue_json(issues);
        out["semantics"] = {{"transfer", xdebug_waveform::stream_handshake_text(config)},
                            {"stall", config.rdy.empty() && config.bp.empty() ? "none" : "enabled"}};
        return out;
    }
};

class StreamValidateHandler : public EngineActionHandler {
public:
    const char* action_name() const override { return "stream.validate"; }
    bool needs_design() const override { return false; }
    bool needs_waveform() const override { return true; }
    Json run(const Json& request) const override {
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

class StreamQueryHandler : public EngineActionHandler {
public:
    const char* action_name() const override { return "stream.query"; }
    bool needs_design() const override { return false; }
    bool needs_waveform() const override { return true; }
    Json run(const Json& request) const override {
        Json args = request.value("args", Json::object());
        Json fail;
        StreamConfig config;
        if (!get_config(args, config, fail)) return fail;
        StreamQueryOptions options;
        std::string error;
        if (!range_from_args(args, request.value("limits", Json::object()), options, error))
            return err("TIME_SPEC_INVALID", error);
        StreamAnalyzer analyzer;
        StreamAnalysis analysis;
        if (!analyzer.analyze(g_fsdb_file, config, options, analysis, error))
            return err(code_for_stream_error(error, "STREAM_ANALYZE_FAILED"), error);

        std::string query = args.value("query", std::string("summary"));
        Json out;
        out["summary"] = xdebug_waveform::stream_summary_json(config, analysis);
        out["query"] = query;
        out["truncated"] = analysis.truncated;
        out["hint"] = analysis.truncated ? "use stream.export for large result" : "";
        if (query == "summary") return out;
        if (query == "first_transfer" || query == "last_transfer") {
            if (!analysis.transfers.empty()) {
                out["row"] = xdebug_waveform::stream_row_json(
                    query == "first_transfer" ? analysis.transfers.front() : analysis.transfers.back());
            }
            return out;
        }
        if (query == "transfer_window") {
            out["rows"] = rows_limited(analysis.transfers, options.limit);
            return out;
        }
        if (query == "first_stall" || query == "last_stall") {
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
            if (packet_index < 0) return err("INVALID_REQUEST", "packet_index must be >= 0");
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
                out["truncated"] = true;
                out["summary"]["truncated"] = true;
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
                return err("INVALID_REQUEST", "field_scope must be beat, stable, or any");
            if (match.field.empty()) return err("MISSING_FIELD", "match.field is required");
            if (match.field_scope == "stable") {
                Json packets = Json::array();
                for (const auto& packet : analysis.packets) {
                    xdebug_waveform::StreamRow pseudo;
                    pseudo.stable_fields = packet.stable_fields;
                    std::string match_error;
                    if (analyzer.match_row(pseudo, match, match_error)) packets.push_back(xdebug_waveform::stream_packet_json(packet));
                    else if (!match_error.empty())
                        return err(code_for_stream_error(match_error, "INVALID_REQUEST"), match_error);
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
                    return err(code_for_stream_error(match_error, "INVALID_REQUEST"), match_error);
                if (static_cast<int>(rows.size()) >= options.limit) break;
            }
            out["rows"] = rows;
            out["summary"]["match_count"] = rows.size();
            out["summary"]["field_scope"] = match.field_scope;
            return out;
        }
        return err("INVALID_REQUEST", "unsupported stream.query type: " + query);
    }
};

class StreamExportHandler : public EngineActionHandler {
public:
    const char* action_name() const override { return "stream.export"; }
    bool needs_design() const override { return false; }
    bool needs_waveform() const override { return true; }
    Json run(const Json& request) const override {
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
        std::string output = args.value("output_file", std::string());
        if (kind == "packet_beats" && output.empty()) return err("MISSING_FIELD", "packet_beats export requires output_file");
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

} // namespace

void register_stream_handlers(EngineActionRegistry& r) {
    r.add(std::unique_ptr<EngineActionHandler>(new StreamConfigLoadHandler));
    r.add(std::unique_ptr<EngineActionHandler>(new StreamConfigListHandler));
    r.add(std::unique_ptr<EngineActionHandler>(new StreamShowHandler));
    r.add(std::unique_ptr<EngineActionHandler>(new StreamValidateHandler));
    r.add(std::unique_ptr<EngineActionHandler>(new StreamQueryHandler));
    r.add(std::unique_ptr<EngineActionHandler>(new StreamExportHandler));
}

} // namespace xdebug_design
