#include "../action_handler.h"
#include "../command_builder.h"

#include "../../protocol/protocol.h"
#include "../../value/logic_value.h"

#include <cstdlib>
#include <string>
#include <vector>

namespace xdebug_waveform {

namespace {

Json ok_out(const WaveformActionContext& ctx) {
    Json out = base_response(ctx.req, ctx.action, true, ctx.elapsed_ms);
    fill_session(out, ctx.info);
    return out;
}

int emit(const WaveformActionContext& ctx, const Json& out, int rc = 0) {
    print_json(finalize_response(ctx.req, out));
    return rc;
}

std::string value_status_from_error(const std::string& err) {
    if (err.find("Signal not found") != std::string::npos ||
        err.find("Failed to read value for signal") != std::string::npos ||
        err.find("SIGNAL_NOT_FOUND") != std::string::npos) return "signal_not_found";
    if (err.find("TIME_OUT_OF_RANGE") != std::string::npos) return "time_out_of_range";
    if (err.find("Invalid time") != std::string::npos ||
        err.find("TIME_SPEC_INVALID") != std::string::npos ||
        err.find("Invalid TimeSpec") != std::string::npos) return "time_invalid";
    return "not_dumped_or_unreadable";
}

std::string value_reason_for_status(const std::string& status, const std::string& signal, const std::string& err) {
    if (status == "signal_not_found") return "Signal path was not found in the FSDB: " + signal;
    if (status == "time_out_of_range") return "Requested time is outside the readable FSDB range";
    if (status == "time_invalid") return "Requested time expression is invalid";
    if (status == "unsupported_format") return err.empty() ? "Requested value format is not supported for this signal value" : err;
    if (!err.empty()) return err;
    return "Value could not be read; the signal may not be dumped or may have no value at the requested time";
}

Json value_suggestions_for_status(const std::string& status, const std::string& signal) {
    Json arr = Json::array();
    if (status == "signal_not_found") {
        arr.push_back({{"action", "scope.list"}, {"reason", "find the real FSDB scope before retrying value.at"},
                       {"args", {{"path", ""}, {"recursive", false}}}});
        arr.push_back({{"action", "signal.resolve"}, {"reason", "resolve candidate waveform signal names"},
                       {"args", {{"signal", signal}}}});
    } else if (status == "not_dumped_or_unreadable") {
        arr.push_back({{"action", "scope.list"}, {"reason", "verify the signal exists in the loaded FSDB"}});
        arr.push_back({{"action", "session.doctor"}, {"reason", "check whether the waveform session is still healthy"}});
    }
    return arr;
}

bool split_csv_like(const std::string& text, std::vector<std::string>& out) {
    out.clear();
    std::string cur;
    int depth = 0;
    for (char ch : text) {
        if (ch == '{') depth++;
        if (ch == '}') depth--;
        if (ch == ',' && depth == 0) {
            out.push_back(trim(cur));
            cur.clear();
        } else {
            cur.push_back(ch);
        }
    }
    if (!cur.empty()) out.push_back(trim(cur));
    return !out.empty();
}

Json parse_array_indexed_value(const std::string& raw, bool& ok, std::string& error) {
    ok = false;
    error.clear();
    std::string s = trim(raw);
    size_t lb = s.find('{');
    size_t rb = s.rfind('}');
    if (lb == std::string::npos || rb == std::string::npos || rb <= lb) {
        error = "format:array_indexed requires an FSDB aggregate value such as 'h{000,001}";
        return Json::object();
    }
    std::string radix = trim(s.substr(0, lb));
    std::string body = s.substr(lb + 1, rb - lb - 1);
    std::vector<std::string> parts;
    if (!split_csv_like(body, parts)) {
        error = "array aggregate has no elements";
        return Json::object();
    }
    Json elements = Json::array();
    Json by_index = Json::object();
    for (size_t i = 0; i < parts.size(); ++i) {
        std::string value = trim(parts[i]);
        elements.push_back({{"index", static_cast<int>(i)}, {"value", value}, {"raw", value}});
        by_index[std::to_string(i)] = value;
    }
    ok = true;
    return {{"raw", raw}, {"radix", radix}, {"index_order", "fsdb_print_order"},
            {"element_count", elements.size()}, {"elements", elements}, {"by_index", by_index}};
}

long long parse_positive_ll(const Json& obj, const char* key, long long def) {
    auto it = obj.find(key);
    if (it == obj.end()) return def;
    if (it->is_number_integer()) return it->get<long long>();
    if (it->is_string()) {
        char* end = nullptr;
        long long v = std::strtoll(it->get<std::string>().c_str(), &end, 10);
        return end && *end == '\0' ? v : def;
    }
    return def;
}

Json make_xbit_hints(const Json& args, const std::string& signal, const std::string& raw) {
    Json hint_args = args.value("slice_hint", Json::object());
    bool include = bool_or(args, "include_xbit_hints", false) ||
                   (args.contains("slice_hint") && args["slice_hint"].is_object());
    if (!include) return Json();
    long long chunk_width = parse_positive_ll(hint_args, "chunk_width", 0);
    if (chunk_width <= 0) {
        return {{"status", "needs_slice_hint"},
                {"message", "Provide args.slice_hint.chunk_width to generate deterministic xbit slice commands"},
                {"signal", signal}, {"raw_value", trim(raw)}};
    }
    long long count = parse_positive_ll(hint_args, "count", 0);
    if (count <= 0) count = 1;
    Json slices = Json::array();
    Json commands = Json::array();
    std::string value = trim(raw);
    for (long long i = 0; i < count; ++i) {
        long long lo = i * chunk_width;
        long long hi = lo + chunk_width - 1;
        Json item = {{"index", i}, {"range", "[" + std::to_string(hi) + ":" + std::to_string(lo) + "]"}};
        if (hint_args.contains("names") && hint_args["names"].is_array() &&
            static_cast<size_t>(i) < hint_args["names"].size() && hint_args["names"][i].is_string()) {
            item["name"] = hint_args["names"][i];
        }
        slices.push_back(item);
        commands.push_back("tools/xbit slice \"" + value + "\" " + std::to_string(hi) + " " + std::to_string(lo) + " --json");
    }
    return {{"status", "ready"}, {"signal", signal}, {"raw_value", value},
            {"chunk_width", chunk_width}, {"count", count}, {"slices", slices}, {"commands", commands}};
}

Json make_value_payload(const Json& args, const std::string& signal, const std::string& raw, bool compact) {
    Json payload = Json::object();
    std::string requested_format = string_or(args, "format", "");
    LogicValue value = logic_value_from_fsdb_raw(raw, fmt_char(args));
    if (requested_format == "array_indexed") {
        bool ok = false;
        std::string error;
        Json indexed = parse_array_indexed_value(raw, ok, error);
        if (ok) {
            payload["status"] = "ok";
            payload["value"] = indexed;
            payload["known"] = !logic_value_has_xz(value);
        } else {
            payload["status"] = "unsupported_format";
            payload["reason"] = value_reason_for_status("unsupported_format", signal, error);
            payload["raw_value"] = logic_value_compact_string(value);
            payload["known"] = !logic_value_has_xz(value);
        }
    } else if (compact) {
        payload["status"] = "ok";
        payload["value"] = logic_value_compact_string(value);
        payload["known"] = !logic_value_has_xz(value);
    } else {
        payload["status"] = "ok";
        payload["value"] = logic_value_json(value);
    }
    Json hints = make_xbit_hints(args, signal, raw);
    if (!hints.is_null()) payload["xbit_hints"] = hints;
    return payload;
}

class ValueAtAction : public WaveformActionHandler {
public:
    const char* action_name() const override { return "value.at"; }

    int run(const WaveformActionContext& ctx) const override {
        std::string signal, time;
        if (!get_string(ctx.args, "signal", signal)) {
            return print_error_and_return(ctx.req, ctx.action, "MISSING_FIELD", "value.at requires args.signal", ctx.elapsed_ms);
        }
        if (!get_string(ctx.args, "at", time) && !get_string(ctx.args, "time", time)) {
            return print_error_and_return(ctx.req, ctx.action, "MISSING_FIELD", "value.at requires args.time or args.at", ctx.elapsed_ms);
        }
        std::string raw;
        std::string err;
        if (!query_value(ctx.sid, signal, time, fmt_char(ctx.args), raw, err)) {
            bool not_found = err.find("Signal not found") != std::string::npos ||
                             err.find("Failed to read value for signal") != std::string::npos ||
                             err.find("SIGNAL_NOT_FOUND") != std::string::npos;
            std::string code = not_found ? "SIGNAL_NOT_FOUND" :
                               err.find("CURSOR_NOT_FOUND") != std::string::npos ? "CURSOR_NOT_FOUND" :
                               err.find("TIME_OUT_OF_RANGE") != std::string::npos ? "TIME_OUT_OF_RANGE" :
                               err.find("CLOCK_OFFSET_UNSUPPORTED") != std::string::npos ? "CLOCK_OFFSET_UNSUPPORTED" :
                               err.find("TIME_SPEC_INVALID") != std::string::npos ? "TIME_SPEC_INVALID" :
                               err.find("Invalid") != std::string::npos ? "TIME_SPEC_INVALID" :
                               "WAVE_QUERY_FAILED";
            return print_error_and_return(ctx.req, ctx.action, code, err, ctx.elapsed_ms);
        }
        Json out = ok_out(ctx);
        LogicValue value = logic_value_from_fsdb_raw(raw, fmt_char(ctx.args));
        out["summary"] = {{"signal", signal}, {"time", time}, {"known", !logic_value_has_xz(value)}};
        out["data"]["signal"] = signal;
        out["data"]["time"] = time;
        bool compact = compact_mode(ctx.req) && !bool_or(ctx.args, "include_raw", false);
        Json payload = make_value_payload(ctx.args, signal, raw, compact);
        if (payload.value("status", std::string()) != "ok") {
            out["summary"]["status"] = payload["status"];
            out["summary"]["known"] = payload.value("known", false);
            out["warnings"].push_back({{"code", "UNSUPPORTED_FORMAT"}, {"message", payload.value("reason", std::string())}});
        }
        if (!compact) {
            Json resolved = resolve_time_spec_json(ctx.sid, time, false, err);
            if (!resolved.is_null()) out["data"]["resolved_time"] = resolved;
            out["data"]["value"] = payload["value"];
        } else {
            out["data"]["value"] = payload["value"];
            out["data"]["known"] = payload.value("known", !logic_value_has_xz(value));
        }
        out["data"]["status"] = payload.value("status", "ok");
        if (payload.contains("reason")) out["data"]["reason"] = payload["reason"];
        if (payload.contains("raw_value")) out["data"]["raw_value"] = payload["raw_value"];
        if (payload.contains("xbit_hints")) out["data"]["xbit_hints"] = payload["xbit_hints"];
        return emit(ctx, out);
    }
};

class ValueBatchAtAction : public WaveformActionHandler {
public:
    const char* action_name() const override { return "value.batch_at"; }

    int run(const WaveformActionContext& ctx) const override {
        std::string time;
        if ((!get_string(ctx.args, "at", time) && !get_string(ctx.args, "time", time)) ||
            !ctx.args.contains("signals") || !ctx.args["signals"].is_array()) {
            return print_error_and_return(ctx.req, ctx.action, "MISSING_FIELD", "value.batch_at requires args.time/args.at and args.signals[]", ctx.elapsed_ms);
        }
        Json arr = Json::array();
        Json values = Json::object();
        Json missing_by_reason = Json::object();
        int unknown = 0, missing = 0;
        for (const auto& s : ctx.args["signals"]) {
            if (!s.is_string()) continue;
            std::string signal = s.get<std::string>();
            std::string raw;
            std::string err;
            Json item;
            item["signal"] = signal;
            item["time"] = time;
            if (query_value(ctx.sid, signal, time, fmt_char(ctx.args), raw, err)) {
                Json payload = make_value_payload(ctx.args, signal, raw, false);
                item["status"] = payload.value("status", "ok");
                item["value"] = payload["value"];
                if (payload.contains("reason")) item["reason"] = payload["reason"];
                if (payload.contains("raw_value")) item["raw_value"] = payload["raw_value"];
                if (payload.contains("xbit_hints")) item["xbit_hints"] = payload["xbit_hints"];
                if (item["status"] == "ok") {
                    LogicValue value = logic_value_from_fsdb_raw(raw, fmt_char(ctx.args));
                    values[signal] = string_or(ctx.args, "format", "") == "array_indexed"
                        ? payload["value"]
                        : Json(logic_value_compact_string(value));
                } else {
                    values[signal] = nullptr;
                    missing++;
                    std::string reason_key = item["status"].get<std::string>();
                    missing_by_reason[reason_key] = missing_by_reason.value(reason_key, 0) + 1;
                }
                if (logic_value_has_xz(logic_value_from_fsdb_raw(raw, fmt_char(ctx.args)))) unknown++;
            } else {
                std::string status = value_status_from_error(err);
                item["status"] = status;
                item["reason"] = value_reason_for_status(status, signal, err);
                item["suggested_next_actions"] = value_suggestions_for_status(status, signal);
                item["value"] = nullptr;
                item["error"] = err;
                values[signal] = nullptr;
                missing++;
                missing_by_reason[status] = missing_by_reason.value(status, 0) + 1;
            }
            arr.push_back(item);
        }
        Json out = ok_out(ctx);
        out["summary"] = {{"time", time}, {"signal_count", arr.size()}, {"x_or_z_count", unknown},
                          {"unknown_count", unknown}, {"missing_count", missing}, {"missing_by_reason", missing_by_reason}};
        if (compact_mode(ctx.req) && !bool_or(ctx.args, "include_raw", false)) {
            out["data"]["values"] = values;
        } else {
            std::string err;
            Json resolved = resolve_time_spec_json(ctx.sid, time, false, err);
            if (!resolved.is_null()) out["data"]["resolved_time"] = resolved;
            out["data"]["values"] = arr;
        }
        if (missing > 0) {
            out["warnings"].push_back({{"code", "VALUE_BATCH_PARTIAL_MISSING"},
                                       {"message", "one or more requested signal values could not be returned"},
                                       {"missing_by_reason", missing_by_reason}});
        }
        return emit(ctx, out);
    }
};

class ScopeListAction : public WaveformActionHandler {
public:
    const char* action_name() const override { return "scope.list"; }

    int run(const WaveformActionContext& ctx) const override {
        std::string path;
        if (!get_string(ctx.args, "path", path)) path = "";
        if (path.empty() || path == ".") path = "/";
        bool recursive = bool_or(ctx.args, "recursive", false);
        Json data;
        std::string err;
        std::string cmd = CommandBuilder(CMD_SCOPE).arg(path).arg(recursive).arg("json").build();
        if (!capture_server_json(ctx.sid, cmd, data, err)) {
            return print_error_and_return(ctx.req, ctx.action, "WAVE_QUERY_FAILED", err, ctx.elapsed_ms);
        }
        bool truncated = false;
        if (data.is_array() && ctx.max_rows >= 0 && data.size() > static_cast<size_t>(ctx.max_rows)) {
            Json limited = Json::array();
            for (int i = 0; i < ctx.max_rows; ++i) limited.push_back(data[i]);
            data = limited;
            truncated = true;
        }
        Json out = ok_out(ctx);
        out["summary"] = {{"path", path}, {"recursive", recursive}, {"signal_count", data.is_array() ? data.size() : 0}, {"truncated", truncated}};
        if (compact_mode(ctx.req) && !bool_or(ctx.args, "include_all_signals", false)) {
            Json preview = Json::array();
            int max_preview = max_examples_arg(ctx.args, ctx.limits, 20);
            if (data.is_array()) {
                for (size_t i = 0; i < data.size() && i < static_cast<size_t>(max_preview); ++i) {
                    preview.push_back(data[i]);
                }
                out["summary"]["truncated"] = truncated || data.size() > static_cast<size_t>(max_preview);
                out["meta"]["truncated"] = out["summary"]["truncated"];
            }
            out["data"]["signals_preview"] = preview;
        } else {
            out["data"]["signals"] = data;
            out["meta"]["truncated"] = truncated;
        }
        return emit(ctx, out);
    }
};

} // namespace

std::unique_ptr<WaveformActionHandler> make_value_at_action() {
    return std::unique_ptr<WaveformActionHandler>(new ValueAtAction());
}

std::unique_ptr<WaveformActionHandler> make_value_batch_at_action() {
    return std::unique_ptr<WaveformActionHandler>(new ValueBatchAtAction());
}

std::unique_ptr<WaveformActionHandler> make_scope_list_action() {
    return std::unique_ptr<WaveformActionHandler>(new ScopeListAction());
}

} // namespace xdebug_waveform
