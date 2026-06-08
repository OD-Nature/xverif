#include "api/help_text.h"

#include <fstream>
#include <sstream>

namespace xdebug {

namespace {

std::string read_file(const std::string& path) {
    std::ifstream file(path.c_str());
    if (!file) return std::string();
    std::ostringstream text;
    text << file.rdbuf();
    return text.str();
}

const char* fallback_help_text() {
    return
        "xdebug - unified xdebug request interface\n"
        "=========================================\n\n"
        "Usage\n"
        "-----\n"
        "  xdebug -h\n"
        "  xdebug -help\n"
        "      Print this human-readable help and exit with status 0.\n\n"
        "  xdebug -\n"
        "      Read one JSON request from stdin and print one XOUT text response.\n\n"
        "  xdebug request.json\n"
        "      Read one JSON request file and print one XOUT text response.\n\n"
        "  xdebug --json -\n"
        "      Print the original JSON response for scripts and schema tests.\n\n"
        "Request / output contract\n"
        "-------------------------\n"
        "  All capabilities are requested with JSON fields api_version/action/target/args/limits/output.\n"
        "  Default output is XOUT structured text; use --json or output.format=json for JSON.\n\n"
        "Common actions\n"
        "--------------\n"
        "  actions, schema, session.open, session.doctor, trace.driver,\n"
        "  trace.graph, trace.path, rc.generate, value.at, value.batch_at, event.export,\n"
        "  verify.conditions, apb.query, axi.query, axi.analysis,\n"
        "  trace.active_driver.\n\n"
        "Action choice guidance\n"
        "----------------------\n"
        "  Use signal.statistics for active/high cycles, signal.changes for\n"
        "  transition timelines, window.verify for holds, and event.find for\n"
        "  first/last occurrence queries. event.find also accepts inline\n"
        "  args.expr + args.clk + args.signals for one-off event queries.\n"
        "  signal.changes compact output omits\n"
        "  rows unless include_rows/include_all_changes is set.\n\n"
        "  session.open does not silently reuse same-name sessions; pass\n"
        "  args.reuse=true to reuse/rebuild a matching session, or reopen=true\n"
        "  to force replacement.\n\n"
        "Output control\n"
        "--------------\n"
        "  output.verbosity=compact/full/debug; use include_* switches and limits\n"
        "  such as max_items, max_examples, limits.max_rows when details are needed.\n\n"
        "Logs\n"
        "----\n"
        "  Public logs live under ~/.xdebug/sessions/<session_id>/logs/actions.ndjson.\n"
        "  Backend lifecycle and transport logs live under ~/.xdebug/{design,waveform}/sessions/.\n\n"
        "Docs\n"
        "----\n"
        "  xdebug/README.md\n"
        "  xdebug/skill/SKILL.md\n"
        "  xdebug/skill/references/json-api-reference.md\n";
}

} // namespace

std::string help_text(const std::string& executable_dir) {
    std::string text = read_file(executable_dir + "/help.txt");
    if (!text.empty()) return text;

    size_t slash = executable_dir.rfind('/');
    if (slash != std::string::npos) {
        text = read_file(executable_dir.substr(0, slash) + "/xdebug/help.txt");
        if (!text.empty()) return text;
    }

    return fallback_help_text();
}

} // namespace xdebug
