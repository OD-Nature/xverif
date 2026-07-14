#include "service/engine_action_handler.h"
#include "service/engine_action_registry.h"
#include "service/engine_globals.h"

#include "api/text_response_builder.h"
#include "design/protocol/protocol.h"
#include "waveform/server/fsdb_value_reader.h"
#include "waveform/event/event_manager.h"
#include "waveform/event/event_analyzer.h"
#include "waveform/list/list_manager.h"
#include "waveform/list/signal_list.h"
#include "waveform/export/waveform_exporter.h"
#include "waveform/common/xdebug_waveform_paths.h"
#include "waveform/service/action_support.h"
#include "waveform/service/rc_generator.h"
#include "waveform/value/logic_value.h"
#include "core/npi/time_contract.h"

#include "npi.h"
#include "npi_fsdb.h"
#include "npi_L1.h"
#include "npi_hdl.h"

#include <fstream>
#include <memory>
#include <algorithm>
#include <map>
#include <sstream>
#include <vector>
#include <fnmatch.h>

namespace xdebug_design {
namespace {
class ScopeListHandler : public EngineActionHandler {
public:
    const char* action_name() const override { return "scope.list"; }
    bool needs_design() const override { return false; }
    bool needs_waveform() const override { return true; }

    Json run(const Json& request, EngineActionContext& ctx) const override {
        Json args = request.value("args", Json::object());
        std::string path = args.value("path", std::string(""));
        bool recursive = args.value("recursive", true);
        int max_depth = args.value("max_depth", 3);
        std::string name_pattern = args.value("name_pattern", std::string("*"));
        std::string kind = args.value("kind", std::string("all"));
        if (kind != "all" && kind != "scope" && kind != "signal") {
            return make_handler_error("INVALID_REQUEST", "scope.list args.kind must be all, scope, or signal",
                                      {{"invalid_arg", "args.kind"},
                                       {"allowed_values", Json::array({"all", "scope", "signal"})}});
        }
        Json limits = request.value("limits", Json::object());
        int max_rows = limits.value("max_rows", -1);

        FILE* fp = tmpfile();
        if (!fp) return make_handler_error("INTERNAL_ERROR", "tmpfile failed");
        int listed = npi_fsdb_hier_tree_dump_sig(g_fsdb_file, fp, path.c_str(),
                                                  recursive ? max_depth : 1);
        fflush(fp); rewind(fp);

        if (!listed) {
            fclose(fp);
            return make_handler_error(
                path.empty() ? "SCOPE_LIST_FAILED" : "SCOPE_NOT_FOUND",
                path.empty() ? "failed to list waveform roots" : "waveform scope not found: " + path,
                {{"invalid_arg", "args.path"},
                 {"missing_name", path},
                 {"missing_resource", "waveform scope"},
                 {"expected", "existing waveform scope path; use an empty path only for roots"},
                 {"correct_example", {{"api_version", "xdebug.v1"},
                                       {"action", "scope.list"},
                                       {"target", {{"session_id", "wave0"}}},
                                       {"args", {{"path", "top"}, {"recursive", true},
                                                 {"max_depth", 3}}}}},
                 {"next_actions", Json::array({"Call scope.roots to discover valid root paths."})}});
        }

        Json scopes = Json::array();
        Json signals = Json::array();
        size_t scanned_row_count = 0;
        size_t matched_row_count = 0;
        size_t matched_scope_count = 0;
        size_t matched_signal_count = 0;
        char line[4096];
        while (fgets(line, sizeof(line), fp)) {
            size_t len = strlen(line);
            while (len > 0 && (line[len-1]=='\n' || line[len-1]=='\r')) line[--len]='\0';
            if (len == 0) continue;
            std::string s(line, len);
            bool is_scope = s.find("(scope)") != std::string::npos;
            size_t pos = s.find("  (");
            std::string name = (pos != std::string::npos) ? s.substr(0, pos) : s;
            ++scanned_row_count;
            bool kind_matches = kind == "all" || (kind == "scope" && is_scope) ||
                                (kind == "signal" && !is_scope);
            if (!kind_matches || fnmatch(name_pattern.c_str(), name.c_str(), 0) != 0) continue;
            ++matched_row_count;
            if (is_scope) ++matched_scope_count; else ++matched_signal_count;
            if (max_rows >= 0 && static_cast<int>(scopes.size() + signals.size()) >= max_rows) continue;
            if (is_scope) scopes.push_back(name); else signals.push_back(name);
        }
        fclose(fp);

        const size_t returned_row_count = scopes.size() + signals.size();
        bool truncated = returned_row_count < matched_row_count;
        const size_t default_xout_rows = 20;
        Json out;
        out["summary"] = {
            {"path", path},
            {"recursive", recursive},
            {"name_pattern", name_pattern},
            {"kind", kind},
            {"scan_complete", true},
            {"scanned_row_count", static_cast<int>(scanned_row_count)},
            {"matched_row_count", static_cast<int>(matched_row_count)},
            {"returned_row_count", static_cast<int>(returned_row_count)},
            {"returned_scope_count", static_cast<int>(scopes.size())},
            {"returned_signal_count", static_cast<int>(signals.size())},
            {"total_scope_count", static_cast<int>(matched_scope_count)},
            {"total_signal_count", static_cast<int>(matched_signal_count)},
            {"response_truncated", truncated},
            {"rendered_row_count", static_cast<int>(std::min(returned_row_count, default_xout_rows))},
            {"render_truncated", returned_row_count > default_xout_rows},
            {"truncated", truncated},
            {"truncation_scopes", truncated ? Json::array({"response_rows"}) : Json::array()}
        };
        out["scopes"] = scopes;
        out["signals"] = signals;
        return out;
    }

};

}  // namespace

std::unique_ptr<EngineActionHandler> make_scope_list_handler() {
    return std::unique_ptr<EngineActionHandler>(new ScopeListHandler);
}

}  // namespace xdebug_design
