#include "cmd_ai.h"
#include "../service/action_support.h"
#include <chrono>
#include <algorithm>
#include <cstdio>
#include <iostream>
#include <string>
#include <vector>

namespace xdebug_waveform {

void print_actions() {
    Json actions = Json::array({
        "session.open", "session.list", "session.doctor", "session.gc", "session.kill",
        "cursor.set", "cursor.get", "cursor.list", "cursor.delete", "cursor.use",
        "scope.list", "rc.generate",
        "value.at", "value.batch_at",
        "list.create", "list.add", "list.delete", "list.show", "list.value_at", "list.validate", "list.diff",
        "apb.config.load", "apb.config.list", "apb.query", "apb.cursor",
        "axi.config.load", "axi.config.list", "axi.query", "axi.cursor", "axi.analysis",
        "event.config.load", "event.config.list", "event.find", "event.export",
        "verify.conditions", "expr.eval_at",
        "window.verify", "signal.changes", "signal.stability", "signal.trend", "signal.statistics",
        "sampled_pulse.inspect", "inspect_signal", "detect_anomaly", "handshake.inspect",
        "axi.channel_stall", "axi.outstanding_timeline", "axi.request_response_pair",
        "axi.latency_outlier", "apb.transfer_window"
    });
    Json out;
    out["api_version"] = kApiVersion;
    out["actions"] = actions;
    out["implemented"] = Json::array({
        "session.open", "session.list", "session.doctor", "session.gc", "session.kill",
        "cursor.set", "cursor.get", "cursor.list", "cursor.delete", "cursor.use",
        "scope.list", "rc.generate", "value.at", "value.batch_at",
        "list.create", "list.add", "list.delete", "list.show", "list.value_at", "list.validate", "list.diff",
        "apb.config.load", "apb.config.list", "apb.query", "apb.cursor",
        "axi.config.load", "axi.config.list", "axi.query", "axi.cursor", "axi.analysis",
        "event.config.load", "event.config.list", "event.find", "event.export",
        "verify.conditions", "expr.eval_at",
        "window.verify", "signal.changes", "signal.stability", "signal.trend", "signal.statistics",
        "sampled_pulse.inspect", "inspect_signal", "detect_anomaly", "handshake.inspect",
        "axi.channel_stall", "axi.outstanding_timeline", "axi.request_response_pair",
        "axi.latency_outlier", "apb.transfer_window"
    });
    out["planned"] = Json::array();
    print_json(out);
}

void print_schema() {
    Json schema;
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema";
    schema["title"] = "xdebug.internal.v1 request";
    schema["type"] = "object";
    schema["required"] = Json::array({"api_version", "action"});
    schema["properties"] = {
        {"api_version", {{"const", kApiVersion}}},
        {"request_id", {{"type", "string"}}},
        {"action", {{"type", "string"}}},
        {"target", {{"type", "object"}}},
        {"args", {{"type", "object"}, {"description", "Action arguments. Time fields accept TimeSpec strings such as 100ns, @deadlock, @deadlock-20ns, @deadlock-10cycle(clk), or @+5ns. Range actions also accept around/before/after. Structured TimeSpec objects are planned but not implemented in this build."}}},
        {"limits", {{"type", "object"}}},
        {"output", {
            {"type", "object"},
            {"properties", {
                {"verbosity", {
                    {"type", "string"},
                    {"enum", Json::array({"compact", "full", "debug"})},
                    {"default", "compact"},
                    {"description", "compact omits session/tool/meta empty scaffolding; full returns the complete envelope; debug keeps full diagnostic session details."}
                }}
            }}
        }}
    };
    schema["xdebug_waveform_response_verbosity"] = {
        {"default", "compact"},
        {"compact", "Only key fields are returned. Successful responses omit tool, session, empty warnings, empty suggested_next_actions, and meta.elapsed_ms. meta.truncated is kept when true."},
        {"full", "Return the complete compatibility envelope."},
        {"debug", "Return the complete envelope with session/socket/pid/fingerprint diagnostics."}
    };
    schema["xdebug_waveform_time_spec"] = {
        {"implemented", Json::array({"absolute time", "@cursor", "@cursor+duration", "@cursor-duration", "@+duration", "@-duration", "@cursor+Ncycle(clk)", "@cursor-Ncycle(clk)", "@cursor+Nposedge(clk)", "@cursor-Nnegedge(clk)", "around/before/after range"})},
        {"planned", Json::array({"structured TimeSpec object"})}
    };
    schema["xdebug_waveform_value_shape"] = {
        {"fields", Json::array({"value", "known"})},
        {"description", "AI signal value objects only contain the display value string and known boolean. Use args.format to choose the display format."}
    };
        schema["xdebug_waveform_event_aggregate"] = {
        {"action", "event.export"},
        {"args", Json::object({{"aggregate", Json::object({{"count", true}, {"group_by", Json::array({"alias_or_field"})}, {"events", false}})}})}
    };
    schema["xdebug_waveform_sampled_pulse_inspect"] = {
        {"action", "sampled_pulse.inspect"},
        {"required_args", Json::array({"clock", "valid", "time_range"})},
        {"optional_args", Json::array({"payload", "payloads", "sampling", "format", "max_samples", "max_events", "max_findings"})},
        {"description", "Compare raw valid/payload transitions against DUT clock-sampled valid cycles and report unsampled pulse risks."}
    };
    schema["xdebug_waveform_transport"] = {
        {"default", "uds"},
        {"values", Json::array({"uds", "tcp"})},
        {"tcp", "session.open accepts args.transport=tcp with optional bind_host/host/port. port 0 or omitted lets the server bind an automatically assigned port and write it to endpoint.json."}
    };
    print_json(schema);
}

int print_error_and_return(const Json& req,
                                  const std::string& action,
                                  const std::string& code,
                                  const std::string& msg,
                                  long long elapsed_ms) {
    print_json(finalize_response(req, error_response(req, action, code, msg, true, elapsed_ms)));
    return 1;
}

bool action_known(const std::string& action) {
    static const std::vector<std::string> implemented = {
        "session.open", "session.list", "session.doctor", "session.gc", "session.kill",
        "cursor.set", "cursor.get", "cursor.list", "cursor.delete", "cursor.use",
        "scope.list", "rc.generate", "value.at", "value.batch_at",
        "list.create", "list.add", "list.delete", "list.show", "list.value_at", "list.validate", "list.diff",
        "apb.config.load", "apb.config.list", "apb.query", "apb.cursor",
        "axi.config.load", "axi.config.list", "axi.query", "axi.cursor", "axi.analysis",
        "event.config.load", "event.config.list", "event.find", "event.export",
        "verify.conditions", "expr.eval_at",
        "window.verify", "signal.changes", "signal.stability", "signal.trend", "signal.statistics",
        "sampled_pulse.inspect", "inspect_signal", "detect_anomaly", "handshake.inspect",
        "axi.channel_stall", "axi.outstanding_timeline", "axi.request_response_pair",
        "axi.latency_outlier", "apb.transfer_window"
    };
    return std::find(implemented.begin(), implemented.end(), action) != implemented.end();
}

bool server_ai_action(const std::string& action) {
    static const std::vector<std::string> server_actions = {
        "cursor.set", "cursor.get", "cursor.list", "cursor.delete", "cursor.use",
        "expr.eval_at", "window.verify", "signal.changes", "signal.stability", "signal.trend", "signal.statistics",
        "sampled_pulse.inspect", "inspect_signal", "detect_anomaly", "handshake.inspect",
        "axi.channel_stall", "axi.outstanding_timeline", "axi.request_response_pair",
        "axi.latency_outlier", "apb.transfer_window"
    };
    return std::find(server_actions.begin(), server_actions.end(), action) != server_actions.end();
}

int cmd_ai(int argc, char** argv) {
    if (argc < 3) {
        fprintf(stderr, "Usage: %s ai <query|schema|actions> ...\n", argv[0]);
        return 1;
    }
    std::string sub = argv[2];
    if (sub == "actions") {
        print_actions();
        return 0;
    }
    if (sub == "schema") {
        print_schema();
        return 0;
    }
    if (sub != "query") {
        fprintf(stderr, "Unknown ai subcommand: %s\n", sub.c_str());
        return 1;
    }

    std::string text;
    if (argc >= 5 && std::string(argv[3]) == "--json") {
        text = argv[4];
    } else if (argc >= 4 && std::string(argv[3]) == "-") {
        text = read_stream(std::cin);
    } else if (argc >= 4) {
        if (!read_file(argv[3], text)) {
            Json empty = Json::object();
            print_json(error_response(empty, "", "INVALID_REQUEST", std::string("cannot read request file: ") + argv[3], true, 0));
            return 1;
        }
    } else {
        fprintf(stderr, "Usage: %s ai query <request.json>|-|--json '<json>'\n", argv[0]);
        return 1;
    }

    auto start = std::chrono::steady_clock::now();
    Json req;
    try {
        req = Json::parse(text);
    } catch (const std::exception& e) {
        Json empty = Json::object();
        print_json(error_response(empty, "", "INVALID_REQUEST", std::string("invalid JSON: ") + e.what(), true, 0));
        return 1;
    }
    auto elapsed = std::chrono::duration_cast<std::chrono::milliseconds>(std::chrono::steady_clock::now() - start).count();
    std::string api;
    if (!get_string(req, "api_version", api) || api != kApiVersion) {
        return print_error_and_return(req, string_or(req, "action", ""), "UNSUPPORTED_API_VERSION", "api_version must be xdebug.internal.v1", elapsed);
    }
    return run_query(req, elapsed);
}


} // namespace xdebug_waveform
