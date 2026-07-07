#include "service/engine_action_handler.h"
#include "service/engine_action_registry.h"
#include "service/engine_globals.h"
#include "waveform_action_support.h"

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

namespace xdebug_design {
namespace {
class ListDiffHandler : public EngineActionHandler {
public:
    const char* action_name() const override { return "list.diff"; }
    bool needs_design() const override { return false; }
    bool needs_waveform() const override { return true; }
    Json run(const Json& r, EngineActionContext& ctx) const override {
        Json a = r.value("args", Json::object());
        Json tr = a.value("time_range", Json::object());
        std::string n = a.value("name", "");
        std::string bs = tr.value("begin", "");
        std::string es = tr.value("end", "");
        if (n.empty() || bs.empty() || es.empty())
            return Json({{"error","MISSING_FIELD"},{"message","args.name and args.time_range.begin/end"}});
        xdebug_waveform::SignalList lst;
        if (!read_list_storage(n, lst))
            return Json({{"error","LIST_NOT_FOUND"},{"message",n}});
        npiFsdbTime bt = 0, et = 0;
        std::string time_error;
        if (!xdebug_waveform::parse_user_time(bs.c_str(), false, bt, time_error) ||
            !xdebug_waveform::parse_user_time(es.c_str(), false, et, time_error))
            return Json({{"error","TIME_SPEC_INVALID"},{"message",time_error}});
        npiFsdbTime dt = 0;
        bool found = xdebug_waveform::find_list_diff(
            xdebug_waveform::g_fsdb_file, lst.signals, bt, et, dt);
        Json out;
        if (found) {
            std::string formatted = xdebug_core::format_time(xdebug_waveform::g_fsdb_file, dt);
            out["summary"] = {{"name", n}, {"diff_found", true}, {"diff_time", formatted}};
        } else {
            out["summary"] = {{"name", n}, {"diff_found", false}, {"diff_time", ""}};
        }
        return out;
    }
};

}  // namespace

std::unique_ptr<EngineActionHandler> make_list_diff_handler() {
    return std::unique_ptr<EngineActionHandler>(new ListDiffHandler);
}

}  // namespace xdebug_design
