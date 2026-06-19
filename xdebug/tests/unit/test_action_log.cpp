#include "logging/action_log.h"

#include <cassert>
#include <cstdlib>
#include <fstream>
#include <sstream>
#include <string>
#include <sys/wait.h>
#include <unistd.h>
#include <vector>

using xdebug_core::Json;

static std::string read_file(const std::string& path) {
    std::ifstream in(path.c_str());
    std::ostringstream ss;
    ss << in.rdbuf();
    return ss.str();
}

static Json read_last_json_line(const std::string& path) {
    std::ifstream in(path.c_str());
    std::string line;
    std::string last;
    while (std::getline(in, line)) {
        if (!line.empty()) last = line;
    }
    assert(!last.empty());
    return Json::parse(last);
}

static std::vector<Json> read_json_lines(const std::string& path) {
    std::ifstream in(path.c_str());
    std::vector<Json> rows;
    std::string line;
    while (std::getline(in, line)) {
        if (!line.empty()) rows.push_back(Json::parse(line));
    }
    return rows;
}

static bool exists(const std::string& path) {
    return access(path.c_str(), F_OK) == 0;
}

int main() {
    std::string home = "/tmp/xdebug_action_log_test_" + std::to_string(getpid());
    setenv("HOME", home.c_str(), 1);

    Json request = {
        {"api_version", "xdebug.v1"},
        {"trace_id", "trace-case-a"},
        {"request_id", "case-a-1"},
        {"span_id", "span-dispatch"},
        {"action", "value.at"},
        {"target", {{"session_id", "case_a"}, {"daidir", "/tmp/foo.daidir"}}},
        {"args", {{"signal", "top.u.ready"}, {"time", "75ns"}, {"radix", "hex"},
                  {"include_trace", true}, {"samples", Json::array({1, 2, 3})}}},
        {"output", {{"verbosity", "compact"}}}
    };
    Json response = {
        {"ok", false},
        {"request_id", "case-a-1"},
        {"action", "value.at"},
        {"summary", {{"signal", "top.u.ready"}}},
        {"data", {{"trace", Json::array({1, 2, 3})}, {"small", true}}},
        {"error", {{"code", "SIGNAL_NOT_FOUND"}, {"message", "missing"}}},
        {"meta", {{"truncated", false}}}
    };

    Json sanitized = xdebug_core::sanitize_for_log(response);
    assert(sanitized["data"]["trace"] == "<omitted:large-field>");
    assert(sanitized.value("log_truncated", false));

    xdebug_core::update_public_session_manifest("case_a", "design", "/tmp/foo.daidir", "");
    std::string manifest_path = xdebug_core::public_session_dir("case_a") + "/session.json";
    Json manifest = Json::parse(read_file(manifest_path));
    assert(manifest["session_id"] == "case_a");
    assert(manifest["mode"] == "design");
    assert(manifest["daidir"] == "/tmp/foo.daidir");
    assert(manifest["logs"]["public_actions"] == xdebug_core::public_action_log_path("case_a"));
    assert(manifest["logs"]["public_stdio"] == xdebug_core::public_stdio_log_path("case_a"));

    Json summary = xdebug_core::request_summary_for_log(request);
    assert(summary["request_id"] == "case-a-1");
    assert(summary["trace_id"] == "trace-case-a");
    assert(summary["args"]["signal"] == "top.u.ready");
    assert(summary["args"]["time"] == "75ns");
    assert(summary["args"]["radix"] == "hex");
    assert(!summary["args"].contains("include_trace"));
    assert(!summary["args"].contains("samples"));

    setenv("XDEBUG_LOG_PATH_MODE", "basename", 1);
    Json basename_summary = xdebug_core::request_summary_for_log(request);
    assert(basename_summary["target"]["daidir"] == "foo.daidir");
    setenv("XDEBUG_LOG_PATH_MODE", "hash", 1);
    Json hash_summary = xdebug_core::request_summary_for_log(request);
    assert(hash_summary["target"]["daidir"].get<std::string>().find("<path:") == 0);
    unsetenv("XDEBUG_LOG_PATH_MODE");

    xdebug_core::log_action_event("public", "xdebug", "case_a", "value.at", "end", false, 12,
                                  {{"request", xdebug_core::request_summary_for_log(request)},
                                   {"response", xdebug_core::response_summary_for_log(response)},
                                   {"request_compact", xdebug_core::sanitize_for_log(request)},
                                   {"response_compact", xdebug_core::sanitize_for_log(response)}});
    Json event = read_last_json_line(xdebug_core::public_action_log_path("case_a"));
    assert(event["layer"] == "public");
    assert(event["component"] == "xdebug");
    assert(event["session_id"] == "case_a");
    assert(event["request_id"] == "case-a-1");
    assert(event["trace_id"] == "trace-case-a");
    assert(event["action"] == "value.at");
    assert(event["phase"] == "end");
    assert(event["ok"] == false);
    assert(event["elapsed_ms"] == 12);

    xdebug_core::log_lifecycle_event("waveform", "case_a", "npi_fsdb_open.failed", false,
                                     {{"fsdb", "/tmp/a.fsdb"}});
    Json lifecycle_event = read_last_json_line(xdebug_core::component_log_path("waveform", "case_a", "lifecycle"));
    assert(lifecycle_event["component"] == "waveform");
    assert(lifecycle_event["phase"] == "npi_fsdb_open.failed");

    xdebug_core::log_stdio_event("case_a", "loop.validate_failed", false,
                                 {{"request_id", "stdio-1"}, {"action", "actions"},
                                  {"error", {{"code", "UNSUPPORTED_API_VERSION"}}}});
    Json stdio_event = read_last_json_line(xdebug_core::public_stdio_log_path("case_a"));
    assert(stdio_event["component"] == "xdebug");
    assert(stdio_event["request_id"] == "stdio-1");
    assert(stdio_event["phase"] == "loop.validate_failed");

    Json huge = request;
    huge["request_id"] = "huge-1";
    Json huge_rsp = response;
    huge_rsp["request_id"] = "huge-1";
    for (int i = 0; i < 150; ++i) {
        huge["args"][std::string("field_") + std::to_string(i)] = std::string(4096, 'x');
        huge_rsp["data"][std::string("field_") + std::to_string(i)] = std::string(4096, 'y');
    }
    xdebug_core::log_action_event("public", "xdebug", "huge_case", "value.at", "end", false, 9,
                                  {{"request", xdebug_core::request_summary_for_log(huge)},
                                   {"response", xdebug_core::response_summary_for_log(huge_rsp)},
                                   {"request_compact", huge},
                                   {"response_compact", huge_rsp}});
    Json huge_event = read_last_json_line(xdebug_core::public_action_log_path("huge_case"));
    assert(huge_event.value("log_truncated", false));
    assert(huge_event.contains("payload_sidecars"));
    assert(huge_event["payload_sidecars"].contains("request_compact"));
    assert(huge_event["payload_sidecars"].contains("response_compact"));
    assert(exists(huge_event["payload_sidecars"]["request_compact"]["path"].get<std::string>()));
    assert(exists(huge_event["payload_sidecars"]["response_compact"]["path"].get<std::string>()));

    setenv("XDEBUG_LOG_MAX_BYTES", "1200", 1);
    setenv("XDEBUG_LOG_MAX_FILES", "2", 1);
    for (int i = 0; i < 8; ++i) {
        xdebug_core::log_action_event("public", "xdebug", "rotate_case", "actions", "end", true, i,
                                      {{"request_id", std::string("rotate-") + std::to_string(i)},
                                       {"padding", std::string(300, 'r')}});
    }
    unsetenv("XDEBUG_LOG_MAX_BYTES");
    unsetenv("XDEBUG_LOG_MAX_FILES");
    assert(exists(xdebug_core::public_action_log_path("rotate_case") + ".1"));

    const int child_count = 4;
    const int events_per_child = 20;
    for (int child = 0; child < child_count; ++child) {
        pid_t pid = fork();
        assert(pid >= 0);
        if (pid == 0) {
            for (int i = 0; i < events_per_child; ++i) {
                xdebug_core::log_action_event("public", "xdebug", "concurrent_case", "actions", "end", true, i,
                                              {{"request_id", std::string("child-") + std::to_string(child) +
                                                               "-" + std::to_string(i)}});
            }
            _exit(0);
        }
    }
    for (int child = 0; child < child_count; ++child) {
        int status = 0;
        assert(wait(&status) > 0);
        assert(WIFEXITED(status) && WEXITSTATUS(status) == 0);
    }
    std::vector<Json> concurrent = read_json_lines(xdebug_core::public_action_log_path("concurrent_case"));
    assert(concurrent.size() == static_cast<size_t>(child_count * events_per_child));
    for (const auto& row : concurrent) {
        assert(row["session_id"] == "concurrent_case");
        assert(row["phase"] == "end");
    }

    return 0;
}
