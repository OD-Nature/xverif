#include "action_support.h"
#include "rc_generator.h"
#include "router_actions.h"
#include "logging/action_log.h"
#include "../list/list_manager.h"
#include "../protocol/protocol.h"
#include <algorithm>
#include <chrono>
#include <cctype>
#include <cstdlib>
#include <exception>
#include <fstream>
#include <map>
#include <sstream>
#include <vector>

namespace xdebug_waveform {

namespace {

std::string value_status_from_error(const std::string& err) {
    if (err.find("Signal not found") != std::string::npos ||
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
    if (requested_format == "array_indexed") {
        bool ok = false;
        std::string error;
        Json indexed = parse_array_indexed_value(raw, ok, error);
        if (ok) {
            payload["status"] = "ok";
            payload["value"] = indexed;
            payload["known"] = !contains_xz(raw);
        } else {
            payload["status"] = "unsupported_format";
            payload["reason"] = value_reason_for_status("unsupported_format", signal, error);
            payload["raw_value"] = trim(raw);
            payload["known"] = !contains_xz(raw);
        }
    } else if (compact) {
        payload["status"] = "ok";
        payload["value"] = trim(raw);
        payload["known"] = !contains_xz(raw);
    } else {
        payload["status"] = "ok";
        payload["value"] = make_value_object(raw);
    }
    Json hints = make_xbit_hints(args, signal, raw);
    if (!hints.is_null()) payload["xbit_hints"] = hints;
    return payload;
}

bool signal_check_ok(const std::string& sid, const std::string& signal, std::string& err) {
    std::string payload;
    return capture_server_text(sid, std::string(CMD_SIGNAL_CHECK) + " " + signal, payload, err);
}

std::string strip_signal_select(const std::string& signal) {
    size_t bracket = signal.find('[');
    if (bracket == std::string::npos) return signal;
    return signal.substr(0, bracket);
}

Json make_rc_validation_error(const Json& req, const std::string& action, const std::string& code,
                              const std::string& message, const SessionInfo& info,
                              const Json& summary, const Json& validation, long long elapsed_ms) {
    Json out = error_response(req, action, code, message, true, elapsed_ms);
    fill_session(out, info);
    out["summary"] = summary;
    out["data"]["validation"] = validation;
    return out;
}

} // namespace

int run_query(const Json& req, long long elapsed_ms) {
    std::string action;
    if (!get_string(req, "action", action)) {
        return print_error_and_return(req, "", "MISSING_FIELD", "request.action is required", elapsed_ms);
    }
    Json target_for_log = req.value("target", Json::object());
    Json args_for_log = req.value("args", Json::object());
    std::string log_sid = string_or(target_for_log, "session_id", string_or(args_for_log, "session_id", string_or(args_for_log, "name", string_or(target_for_log, "name", "adhoc"))));
    xdebug_core::log_action_event("backend", "waveform", log_sid, action, "begin", true, 0,
                                  {{"request", xdebug_core::request_summary_for_log(req)}});
    auto log_return = [&](const Json& out, int rc) -> int {
        xdebug_core::log_action_event("backend", "waveform", log_sid, action, "end", out.value("ok", rc == 0), elapsed_ms,
                                      {{"response", xdebug_core::response_summary_for_log(out)},
                                       {"request", out.value("ok", false) ? xdebug_core::request_summary_for_log(req) : xdebug_core::sanitize_for_log(req)}});
        print_json(finalize_response(req, out));
        return rc;
    };
    if (!action_known(action)) {
        Json out = error_response(req, action, "UNKNOWN_ACTION", "action is not implemented: " + action, true, elapsed_ms);
        return log_return(out, 1);
    }
    Json target = req.value("target", Json::object());
    Json args = req.value("args", Json::object());
    Json limits = req.value("limits", Json::object());
    int max_rows = int_or(limits, "max_rows", int_or(limits, "max_events", 1000));
    bool verbosity_valid = true;
    response_verbosity(req, &verbosity_valid);
    if (!verbosity_valid) {
        return print_error_and_return(req, action, "INVALID_REQUEST", "output.verbosity must be compact, full, or debug", elapsed_ms);
    }

    auto ok_out = [&](const SessionInfo* info = nullptr) {
        Json out = base_response(req, action, true, elapsed_ms);
        if (info) fill_session(out, *info);
        return out;
    };
    auto emit = [&](const Json& out, int rc = 0) -> int {
        xdebug_core::log_action_event("backend", "waveform", log_sid, action, "end", out.value("ok", rc == 0), elapsed_ms,
                                      {{"response", xdebug_core::response_summary_for_log(out)},
                                       {"request", out.value("ok", false) ? xdebug_core::request_summary_for_log(req) : xdebug_core::sanitize_for_log(req)}});
        print_json(finalize_response(req, out));
        return rc;
    };

    bool handled = false;
    int handler_rc = run_session_action(req, action, target, args, elapsed_ms, handled);
    if (handled) return handler_rc;

    std::string sid;
    SessionInfo info;
    std::string err;
    if (!resolve_session(target, true, sid, info, err)) {
        return print_error_and_return(req, action, "SESSION_NOT_FOUND", err, elapsed_ms);
    }

    if (server_ai_action(action)) {
        Json data;
        std::string cmd = std::string(CMD_AI_QUERY) + " " + req.dump();
        if (!capture_server_json(sid, cmd, data, err)) {
            std::string code = err.find("Signal not found") != std::string::npos ? "SIGNAL_NOT_FOUND" :
                               err.find("Clock signal not found") != std::string::npos ? "SIGNAL_NOT_FOUND" :
                               err.find("SIGNAL_NOT_FOUND") != std::string::npos ? "SIGNAL_NOT_FOUND" :
                               err.find("CURSOR_NOT_FOUND") != std::string::npos ? "CURSOR_NOT_FOUND" :
                               err.find("TIME_OUT_OF_RANGE") != std::string::npos ? "TIME_OUT_OF_RANGE" :
                               err.find("CLOCK_OFFSET_UNSUPPORTED") != std::string::npos ? "CLOCK_OFFSET_UNSUPPORTED" :
                               err.find("TIME_SPEC_INVALID") != std::string::npos ? "TIME_SPEC_INVALID" :
                               err.find("Invalid time") != std::string::npos ? "TIME_SPEC_INVALID" :
                               err.find("Invalid TimeSpec") != std::string::npos ? "TIME_SPEC_INVALID" :
                               err.find("config not found") != std::string::npos ? "INVALID_REQUEST" :
                               err.find("expression") != std::string::npos ? "EXPR_PARSE_FAILED" :
                               "WAVE_QUERY_FAILED";
            return print_error_and_return(req, action, code, err, elapsed_ms);
        }
        Json out = ok_out(&info);
        out["data"] = data;
        std::string begin_spec, end_spec;
        bool around_window = false;
        if (build_range_specs(args, begin_spec, end_spec, around_window, err) &&
            (args.contains("time_range") || args.contains("begin") || args.contains("end") || args.contains("around"))) {
            fill_resolved_range(out, sid, begin_spec, end_spec, around_window, err);
        }
        std::string at_spec = string_or(args, "at", string_or(args, "time", ""));
        if (!at_spec.empty() && out["data"].is_object() && !out["data"].contains("resolved_time")) {
            Json resolved = resolve_time_spec_json(sid, at_spec, false, err);
            if (!resolved.is_null()) out["data"]["resolved_time"] = resolved;
        }
        if (data.contains("truncated")) out["meta"]["truncated"] = data["truncated"];
        if (data.contains("findings")) out["findings"] = data["findings"];
        if (data.contains("warnings")) out["warnings"] = data["warnings"];
        if (action == "sampled_pulse.inspect") {
            out["summary"] = {{"sample_count", data.value("sample_count", 0)},
                              {"sampled_high_cycles", data.value("sampled_high_cycles", 0)},
                              {"raw_valid_transition_count", data.value("raw_valid_transition_count", 0)},
                              {"payload_transition_count", data.value("payload_transition_count", 0)},
                              {"risk_count", data.value("risk_count", 0)}};
        } else if (action == "window.verify") {
            out["summary"] = {{"all_passed", data.value("all_passed", false)},
                              {"sample_count", data.value("sample_count", 0)},
                              {"failed_samples", data.value("failed_samples", 0)},
                              {"unknown_samples", data.value("unknown_samples", 0)}};
        } else if (action == "handshake.inspect") {
            out["summary"] = {{"transfer_count", data.value("transfer_count", 0)},
                              {"max_stall_cycles", data.value("max_stall_cycles", 0)}};
        } else if (action == "detect_anomaly") {
            out["summary"] = {{"finding_count", data.value("finding_count", 0)}};
        } else if (action == "signal.changes") {
            out["summary"] = {
                {"transition_count", data.value("transition_count", 0)},
                {"returned_change_rows", data.value("returned_change_rows", 0)},
                {"includes_initial_value", data.value("includes_initial_value", false)},
                {"actual_transition_count", data.value("actual_transition_count", 0)},
                {"first_change", data.value("first_change", Json(nullptr))},
                {"last_change", data.value("last_change", Json(nullptr))},
                {"semantic_note", data.value("semantic_note", "")}
            };
        } else if (action == "signal.statistics") {
            out["summary"] = {
                {"sampling_mode", data.value("sampling_mode", "")},
                {"sample_count", data.value("sample_count", 0)},
                {"transition_count", data.value("transition_count", 0)},
                {"high_cycles", data.value("high_cycles", 0)},
                {"low_cycles", data.value("low_cycles", 0)}
            };
        } else if (data.contains("transaction_count")) {
            out["summary"] = {{"transaction_count", data["transaction_count"]}};
        } else if (data.contains("sample_count")) {
            out["summary"] = {{"sample_count", data["sample_count"]}};
        } else if (data.contains("transition_count")) {
            out["summary"] = {{"transition_count", data["transition_count"]}};
        } else if (data.contains("status")) {
            out["summary"] = {{"status", data["status"]}, {"known", data.value("known", false)}};
        }
        return emit(out);
    }

    if (action == "rc.generate") {
        std::string config_path = string_or(args, "config_path", string_or(args, "json_path", ""));
        std::string rc_path = string_or(args, "rc_path", string_or(args, "output_path", ""));
        if (config_path.empty()) {
            return print_error_and_return(req, action, "MISSING_FIELD", "rc.generate requires args.config_path", elapsed_ms);
        }
        if (rc_path.empty()) {
            return print_error_and_return(req, action, "MISSING_FIELD", "rc.generate requires args.rc_path", elapsed_ms);
        }

        std::string config_text;
        if (!read_file(config_path, config_text)) {
            return print_error_and_return(req, action, "RC_CONFIG_INVALID", "cannot read config_path: " + config_path, elapsed_ms);
        }

        Json config_doc;
        try {
            config_doc = Json::parse(config_text);
        } catch (const std::exception& ex) {
            return print_error_and_return(req, action, "RC_CONFIG_INVALID", std::string("config_path is not valid JSON: ") + ex.what(), elapsed_ms);
        }

        RcConfig config;
        std::string parse_err;
        if (!parse_rc_config_json(config_doc, config, parse_err)) {
            return print_error_and_return(req, action, "RC_CONFIG_INVALID", parse_err, elapsed_ms);
        }

        Json counts = rc_config_counts(config);
        Json summary = {
            {"config_path", config_path},
            {"rc_path", rc_path},
            {"group_count", counts.value("group_count", 0)},
            {"signal_count", counts.value("signal_count", 0)},
            {"expr_signal_count", counts.value("expr_signal_count", 0)},
            {"marker_count", counts.value("marker_count", 0)},
            {"written", false},
            {"valid", true}
        };

        Json validation;
        validation["signals"] = Json::array();
        validation["times"] = Json::array();

        int missing_signal_count = 0;
        for (const auto& ref : collect_rc_signal_refs(config)) {
            std::string check_err;
            bool found = signal_check_ok(sid, ref.input_path, check_err);
            std::string checked_path = ref.input_path;
            bool checked_base_signal = false;
            if (!found) {
                std::string base = strip_signal_select(ref.input_path);
                if (base != ref.input_path) {
                    std::string base_err;
                    if (signal_check_ok(sid, base, base_err)) {
                        found = true;
                        checked_path = base;
                        checked_base_signal = true;
                        check_err.clear();
                    } else if (check_err.empty()) {
                        check_err = base_err;
                    }
                }
            }
            Json item = {
                {"kind", ref.kind},
                {"owner", ref.owner},
                {"input_path", ref.input_path},
                {"rc_path", ref.rc_path},
                {"exists", found},
                {"checked_path", checked_path}
            };
            if (checked_base_signal) item["checked_base_signal"] = true;
            if (!found) {
                item["error"] = check_err;
                missing_signal_count++;
            }
            validation["signals"].push_back(item);
        }

        int invalid_time_count = 0;
        for (const auto& ref : collect_rc_time_refs(config)) {
            std::string time_err;
            Json resolved = resolve_time_spec_json(sid, ref.spec, ref.allow_max, time_err);
            bool ok = !resolved.is_null();
            Json item = {
                {"kind", ref.kind},
                {"owner", ref.owner},
                {"spec", ref.spec},
                {"valid", ok}
            };
            if (ok) item["resolved_time"] = resolved;
            else {
                item["error"] = time_err;
                invalid_time_count++;
            }
            validation["times"].push_back(item);
        }

        bool valid = missing_signal_count == 0 && invalid_time_count == 0;
        summary["valid"] = valid;
        summary["missing_signal_count"] = missing_signal_count;
        summary["invalid_time_count"] = invalid_time_count;

        bool allow_invalid = bool_or(args, "allow_invalid", false);
        if (!valid && !allow_invalid) {
            Json out = make_rc_validation_error(req, action, "RC_VALIDATION_FAILED",
                                                "rc config validation failed; rc file was not written",
                                                info, summary, validation, elapsed_ms);
            return emit(out, 1);
        }

        std::string rc_text = render_signal_rc(config);
        std::string write_err;
        if (!write_text_file_creating_dirs(rc_path, rc_text, write_err)) {
            return print_error_and_return(req, action, "RC_WRITE_FAILED", write_err, elapsed_ms);
        }

        Json out = ok_out(&info);
        summary["written"] = true;
        out["summary"] = summary;
        out["data"]["config_path"] = config_path;
        out["data"]["rc_path"] = rc_path;
        out["data"]["validation"] = validation;
        if (bool_or(args, "include_preview", false)) {
            out["data"]["rc_preview"] = rc_preview_lines(rc_text, int_or(args, "max_preview_lines", 40));
        }
        if (!valid) {
            out["warnings"].push_back({{"code", "RC_VALIDATION_FAILED"},
                                       {"message", "rc file was written because allow_invalid is true"},
                                       {"missing_signal_count", missing_signal_count},
                                       {"invalid_time_count", invalid_time_count}});
        }
        return emit(out);
    }

    if (action == "value.at") {
        std::string signal, time;
        if (!get_string(args, "signal", signal)) {
            return print_error_and_return(req, action, "MISSING_FIELD", "value.at requires args.signal", elapsed_ms);
        }
        if (!get_string(args, "at", time) && !get_string(args, "time", time)) {
            return print_error_and_return(req, action, "MISSING_FIELD", "value.at requires args.time or args.at", elapsed_ms);
        }
        std::string raw;
        if (!query_value(sid, signal, time, fmt_char(args), raw, err)) {
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
            return print_error_and_return(req, action, code, err, elapsed_ms);
        }
        Json out = ok_out(&info);
        out["summary"] = {{"signal", signal}, {"time", time}, {"known", !contains_xz(raw)}};
        out["data"]["signal"] = signal;
        out["data"]["time"] = time;
        bool compact = compact_mode(req) && !bool_or(args, "include_raw", false);
        Json payload = make_value_payload(args, signal, raw, compact);
        if (payload.value("status", std::string()) != "ok") {
            out["summary"]["status"] = payload["status"];
            out["summary"]["known"] = payload.value("known", false);
            out["warnings"].push_back({{"code", "UNSUPPORTED_FORMAT"}, {"message", payload.value("reason", std::string())}});
        }
        if (!compact) {
            Json resolved = resolve_time_spec_json(sid, time, false, err);
            if (!resolved.is_null()) out["data"]["resolved_time"] = resolved;
            out["data"]["value"] = payload["value"];
        } else {
            out["data"]["value"] = payload["value"];
            out["data"]["known"] = payload.value("known", !contains_xz(raw));
        }
        out["data"]["status"] = payload.value("status", "ok");
        if (payload.contains("reason")) out["data"]["reason"] = payload["reason"];
        if (payload.contains("raw_value")) out["data"]["raw_value"] = payload["raw_value"];
        if (payload.contains("xbit_hints")) out["data"]["xbit_hints"] = payload["xbit_hints"];
        return emit(out);
    }

    if (action == "value.batch_at") {
        std::string time;
        if ((!get_string(args, "at", time) && !get_string(args, "time", time)) ||
            !args.contains("signals") || !args["signals"].is_array()) {
            return print_error_and_return(req, action, "MISSING_FIELD", "value.batch_at requires args.time/args.at and args.signals[]", elapsed_ms);
        }
        Json arr = Json::array();
        Json values = Json::object();
        Json missing_by_reason = Json::object();
        int unknown = 0, missing = 0;
        for (const auto& s : args["signals"]) {
            if (!s.is_string()) continue;
            std::string signal = s.get<std::string>();
            std::string raw;
            Json item;
            item["signal"] = signal;
            item["time"] = time;
            if (query_value(sid, signal, time, fmt_char(args), raw, err)) {
                Json payload = make_value_payload(args, signal, raw, false);
                item["status"] = payload.value("status", "ok");
                item["value"] = payload["value"];
                if (payload.contains("reason")) item["reason"] = payload["reason"];
                if (payload.contains("raw_value")) item["raw_value"] = payload["raw_value"];
                if (payload.contains("xbit_hints")) item["xbit_hints"] = payload["xbit_hints"];
                if (item["status"] == "ok") {
                    values[signal] = string_or(args, "format", "") == "array_indexed" ? payload["value"] : Json(trim(raw));
                } else {
                    values[signal] = nullptr;
                    missing++;
                    std::string reason_key = item["status"].get<std::string>();
                    missing_by_reason[reason_key] = missing_by_reason.value(reason_key, 0) + 1;
                }
                if (contains_xz(raw)) unknown++;
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
        Json out = ok_out(&info);
        out["summary"] = {{"time", time}, {"signal_count", arr.size()}, {"x_or_z_count", unknown},
                          {"unknown_count", unknown}, {"missing_count", missing}, {"missing_by_reason", missing_by_reason}};
        if (compact_mode(req) && !bool_or(args, "include_raw", false)) {
            out["data"]["values"] = values;
        } else {
            Json resolved = resolve_time_spec_json(sid, time, false, err);
            if (!resolved.is_null()) out["data"]["resolved_time"] = resolved;
            out["data"]["values"] = arr;
        }
        if (missing > 0) {
            out["warnings"].push_back({{"code", "VALUE_BATCH_PARTIAL_MISSING"},
                                       {"message", "one or more requested signal values could not be returned"},
                                       {"missing_by_reason", missing_by_reason}});
        }
        return emit(out);
    }

    if (action == "scope.list") {
        std::string path;
        if (!get_string(args, "path", path)) path = "";
        if (path.empty() || path == ".") path = "/";
        bool recursive = bool_or(args, "recursive", false);
        Json data;
        std::string cmd = std::string(CMD_SCOPE) + " " + path + " " + (recursive ? "1" : "0") + " json";
        if (!capture_server_json(sid, cmd, data, err)) return print_error_and_return(req, action, "WAVE_QUERY_FAILED", err, elapsed_ms);
        bool truncated = false;
        if (data.is_array() && max_rows >= 0 && data.size() > static_cast<size_t>(max_rows)) {
            Json limited = Json::array();
            for (int i = 0; i < max_rows; ++i) limited.push_back(data[i]);
            data = limited;
            truncated = true;
        }
        Json out = ok_out(&info);
        out["summary"] = {{"path", path}, {"recursive", recursive}, {"signal_count", data.is_array() ? data.size() : 0}, {"truncated", truncated}};
        if (compact_mode(req) && !bool_or(args, "include_all_signals", false)) {
            Json preview = Json::array();
            int max_preview = max_examples_arg(args, limits, 20);
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
        return emit(out);
    }

    if (action.compare(0, 5, "list.") == 0) {
        ListManager lm;
        std::string name = string_or(args, "name", string_or(args, "list", ""));
        if (name.empty() && action != "list.create") lm.get_latest_list(sid, name);
        if (action == "list.create") {
            if (name.empty()) return print_error_and_return(req, action, "MISSING_FIELD", "list.create requires args.name", elapsed_ms);
            if (!lm.create_list(sid, name)) return print_error_and_return(req, action, "INTERNAL_ERROR", "failed to create list", elapsed_ms);
            Json out = ok_out(&info); out["summary"] = {{"name", name}, {"status", "created"}}; return emit(out);
        }
        if (name.empty()) return print_error_and_return(req, action, "MISSING_FIELD", "list action requires args.name or latest list", elapsed_ms);
        if (action == "list.add") {
            std::string signal;
            if (!get_string(args, "signal", signal)) return print_error_and_return(req, action, "MISSING_FIELD", "list.add requires args.signal", elapsed_ms);
            std::string payload;
            if (!capture_server_text(sid, std::string(CMD_SIGNAL_CHECK) + " " + signal, payload, err)) {
                return print_error_and_return(req, action, "SIGNAL_NOT_FOUND", err, elapsed_ms);
            }
            if (!lm.add_signal(sid, name, signal)) return print_error_and_return(req, action, "INTERNAL_ERROR", "failed to add signal", elapsed_ms);
            Json out = ok_out(&info); out["summary"] = {{"name", name}, {"signal", signal}, {"status", "added"}}; return emit(out);
        }
        if (action == "list.delete") {
            std::string signal = string_or(args, "signal", string_or(args, "index", ""));
            if (signal.empty()) return print_error_and_return(req, action, "MISSING_FIELD", "list.delete requires args.signal or args.index", elapsed_ms);
            if (!lm.del_signal(sid, name, signal)) return print_error_and_return(req, action, "INTERNAL_ERROR", "failed to delete signal", elapsed_ms);
            Json out = ok_out(&info); out["summary"] = {{"name", name}, {"removed", signal}}; return emit(out);
        }
        if (action == "list.show") {
            SignalList list;
            if (!lm.get_list(sid, name, list)) return print_error_and_return(req, action, "INVALID_REQUEST", "list not found", elapsed_ms);
            Json arr = Json::array();
            for (size_t i = 0; i < list.signals.size(); ++i) arr.push_back({{"index", i + 1}, {"signal", list.signals[i]}});
            Json out = ok_out(&info); out["summary"] = {{"name", name}, {"signal_count", arr.size()}}; out["data"]["signals"] = arr; return emit(out);
        }
        if (action == "list.value_at") {
            std::string time;
            if (!get_string(args, "at", time) && !get_string(args, "time", time)) {
                return print_error_and_return(req, action, "MISSING_FIELD", "list.value_at requires args.time or args.at", elapsed_ms);
            }
            Json data;
            std::string cmd = std::string(CMD_LIST_VALUE) + " " + name + " " + time + " " + fmt_char(args) + " json";
            bool ok = capture_server_json(sid, cmd, data, err);
            Json out = base_response(req, action, ok, elapsed_ms);
            fill_session(out, info);
            out["summary"] = {{"name", name}, {"time", time}};
            if (data.is_object() && data.contains("values") && data["values"].is_object()) {
                data["values"] = make_value_map(data["values"]);
            } else if (data.is_object()) {
                data = make_value_map(data);
            }
            if (compact_mode(req) && !bool_or(args, "include_raw", false)) {
                Json values = Json::object();
                Json raw_values = data.contains("values") ? data["values"] : data;
                if (raw_values.is_object()) {
                    for (auto it = raw_values.begin(); it != raw_values.end(); ++it) {
                        if (it.value().is_object() && it.value().contains("value")) values[it.key()] = it.value()["value"];
                        else values[it.key()] = it.value();
                    }
                }
                out["data"]["values"] = values;
            } else {
                out["data"] = data;
                Json resolved = resolve_time_spec_json(sid, time, false, err);
                if (!resolved.is_null()) out["data"]["resolved_time"] = resolved;
            }
            if (!ok) out["error"] = {{"code", "SIGNAL_NOT_FOUND"}, {"message", err}, {"recoverable", true}, {"candidates", Json::array()}, {"suggested_actions", Json::array()}};
            return emit(out, ok ? 0 : 1);
        }
        if (action == "list.validate") {
            Json data;
            bool ok = capture_server_json(sid, std::string(CMD_LIST_VALIDATE) + " " + name + " json", data, err);
            Json out = base_response(req, action, ok, elapsed_ms);
            fill_session(out, info);
            out["summary"] = {{"name", name}, {"all_found", ok}};
            out["data"]["signals"] = data;
            if (!ok) out["error"] = {{"code", "SIGNAL_NOT_FOUND"}, {"message", err}, {"recoverable", true}, {"candidates", Json::array()}, {"suggested_actions", Json::array()}};
            return emit(out, ok ? 0 : 1);
        }
        if (action == "list.diff") {
            std::string begin, end;
            bool around_window = false;
            if (!build_range_specs(args, begin, end, around_window, err)) {
                return print_error_and_return(req, action, "TIME_SPEC_INVALID", err, elapsed_ms);
            }
            std::string payload;
            if (!capture_server_text(sid, std::string(CMD_LIST_DIFF) + " " + name + " " + begin + " " + end, payload, err)) {
                return print_error_and_return(req, action, "WAVE_QUERY_FAILED", err, elapsed_ms);
            }
            Json out = ok_out(&info);
            out["summary"] = {{"name", name}, {"diff_time", payload}};
            out["data"]["time"] = payload;
            fill_resolved_range(out, sid, begin, end, around_window, err);
            return emit(out);
        }
    }

    handler_rc = run_protocol_action(req, action, args, limits, sid, info, elapsed_ms, handled);
    if (handled) return handler_rc;

    if (action == "verify.conditions") {
        std::string time;
        if ((!get_string(args, "at", time) && !get_string(args, "time", time)) ||
            !args.contains("conditions") || !args["conditions"].is_array()) {
            return print_error_and_return(req, action, "MISSING_FIELD", "verify.conditions requires args.time/args.at and args.conditions[]", elapsed_ms);
        }
        Json checks = Json::array();
        int passed = 0, failed = 0, unknown = 0;
        for (const auto& cond : args["conditions"]) {
            std::string signal, op, expected;
            get_string(cond, "signal", signal);
            get_string(cond, "op", op);
            get_string(cond, "value", expected);
            Json item = {{"signal", signal}, {"time", time}, {"op", op}, {"expected", expected}};
            std::string raw;
            if (!query_value(sid, signal, time, 'H', raw, err)) {
                item["status"] = "unknown"; item["known"] = false; item["pass"] = nullptr; item["error"] = err; unknown++;
            } else if (contains_xz(raw) || contains_xz(expected)) {
                item["observed"] = make_value_object(raw); item["status"] = "unknown"; item["known"] = false; item["pass"] = nullptr; unknown++;
            } else {
                bool eq = normalize_numeric(raw) == normalize_numeric(expected);
                bool pass = (op == "!=") ? !eq : eq;
                item["observed"] = make_value_object(raw); item["status"] = pass ? "pass" : "fail"; item["known"] = true; item["pass"] = pass;
                if (pass) passed++; else failed++;
            }
            checks.push_back(item);
        }
        Json out = ok_out(&info);
        out["summary"] = {{"verdict", failed == 0 && unknown == 0 ? "pass" : "fail"},
                          {"condition_count", checks.size()},
                          {"all_passed", failed == 0 && unknown == 0},
                          {"passed", passed}, {"failed", failed}, {"unknown", unknown}};
        if (!compact_mode(req) || failed > 0 || unknown > 0) {
            Json filtered = Json::array();
            for (const auto& check : checks) {
                std::string status = check.value("status", std::string());
                if (!compact_mode(req) || status != "pass") filtered.push_back(check);
            }
            out["data"]["checks"] = filtered;
        }
        if (!compact_mode(req)) {
            Json resolved = resolve_time_spec_json(sid, time, false, err);
            if (!resolved.is_null()) out["data"]["resolved_time"] = resolved;
        }
        return emit(out);
    }

    if (action == "expr.eval_at") {
        std::string time, expr;
        if ((!get_string(args, "at", time) && !get_string(args, "time", time)) ||
            !get_string(args, "expr", expr) || !args.contains("signals") || !args["signals"].is_object()) {
            return print_error_and_return(req, action, "MISSING_FIELD", "expr.eval_at requires args.time/args.at, args.expr, args.signals", elapsed_ms);
        }
        Json values = Json::object();
        Json operands = Json::array();
        int unknown = 0;
        for (auto it = args["signals"].begin(); it != args["signals"].end(); ++it) {
            std::string alias = it.key();
            std::string signal = it.value().get<std::string>();
            std::string raw;
            Json item = {{"alias", alias}, {"signal", signal}};
            if (query_value(sid, signal, time, 'H', raw, err)) {
                item["value"] = make_value_object(raw);
                if (contains_xz(raw)) unknown++;
            } else {
                item["value"] = nullptr;
                item["error"] = err;
                unknown++;
            }
            values[alias] = item;
            operands.push_back(item);
        }
        bool expression_ok = false;
        Tri v = evaluate_expression(expr, values, expression_ok);
        if (!expression_ok) return print_error_and_return(req, action, "EXPR_PARSE_FAILED", "failed to parse expression", elapsed_ms);
        Json out = ok_out(&info);
        out["summary"] = {{"expr", expr}, {"expr_value", v == Tri::True ? Json(true) : v == Tri::False ? Json(false) : Json(nullptr)}, {"status", tri_text(v)}, {"known", v != Tri::Unknown}};
        Json resolved = resolve_time_spec_json(sid, time, false, err);
        if (!resolved.is_null()) out["data"]["resolved_time"] = resolved;
        out["data"]["operands"] = operands;
        out["data"]["unknown_count"] = unknown;
        return emit(out);
    }

    return print_error_and_return(req, action, "UNKNOWN_ACTION", "unhandled action: " + action, elapsed_ms);
}


} // namespace xdebug_waveform
