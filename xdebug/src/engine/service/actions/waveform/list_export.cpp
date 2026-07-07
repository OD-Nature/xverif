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
class ListExportHandler : public EngineActionHandler {
public:
    const char* action_name() const override { return "list.export"; }
    bool needs_design() const override { return false; }
    bool needs_waveform() const override { return true; }
    Json run(const Json& r, EngineActionContext& ctx) const override {
        Json a = r.value("args", Json::object());
        std::string n = a.value("name", a.value("list", ""));
        if (n.empty()) return Json({{"error","MISSING_FIELD"},{"message","args.name"}});
        xdebug_waveform::SignalList lst;
        if (!read_list_storage(n, lst))
            return Json({{"error","LIST_NOT_FOUND"},{"message",n}});

        Json tr = a.value("time_range", Json::object());
        std::string bs = tr.value("begin", std::string());
        std::string es = tr.value("end", std::string());
        if (bs.empty() || es.empty())
            return Json({{"error","MISSING_FIELD"},{"message","list.export requires args.time_range.begin/end"}});

        npiFsdbTime begin = 0, end = 0;
        std::string time_error;
        if (!xdebug_waveform::parse_user_time(bs.c_str(), false, begin, time_error) ||
            !xdebug_waveform::parse_user_time(es.c_str(), true, end, time_error))
            return Json({{"error","TIME_SPEC_INVALID"},{"message",time_error.empty() ? "failed to parse list.export time range" : time_error}});
        if (end < begin)
            return Json({{"error","TIME_SPEC_INVALID"},{"message","end time is before begin time"}});
        if (end - begin < 256000ULL)
            return Json({{"error","TIME_RANGE_TOO_SMALL"},{"message","list.export requires at least 256ns; use list.value_at or value.batch_at for point reads"}});

        std::string format = a.value("format", std::string("u64bin"));
        Json output = a.value("output", Json::object());
        std::string output_dir = output.value("path", std::string());
        if (output_dir.empty()) {
            output_dir = xdebug_waveform::xdebug_waveform_list_exports_dir(xdebug_waveform::g_session_id)
                + "/" + n + "_" + std::to_string(begin) + "_" + std::to_string(end)
                + "_" + std::to_string(static_cast<long long>(time(nullptr)));
        }
        xdebug_waveform::ListExportOptions options;
        options.session_id = xdebug_waveform::g_session_id;
        options.list_name = n;
        options.output_dir = output_dir;
        options.format = format;
        options.begin = begin;
        options.end = end;
        xdebug_waveform::ListExportResult result;
        std::string error;
        if (!xdebug_waveform::export_signal_list(xdebug_waveform::g_fsdb_file, lst, options, result, error))
            return Json({{"error","EXPORT_FAILED"},{"message",error}});

        Json out;
        out["summary"] = {
            {"name", n},
            {"signal_count", result.signal_count},
            {"row_count", result.row_count},
            {"format", result.format}
        };
        out["output_dir"] = result.output_dir;
        out["manifest_file"] = result.manifest_file;
        out["signals"] = result.signals;
        auto range = xdebug_core::format_time_range(xdebug_waveform::g_fsdb_file, begin, end);
        out["begin"] = range.first;
        out["end"] = range.second;
        return out;
    }
};

}  // namespace

std::unique_ptr<EngineActionHandler> make_list_export_handler() {
    return std::unique_ptr<EngineActionHandler>(new ListExportHandler);
}

}  // namespace xdebug_design
