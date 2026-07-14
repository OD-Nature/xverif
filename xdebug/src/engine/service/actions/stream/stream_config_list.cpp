#include "service/engine_action_handler.h"
#include "service/engine_action_registry.h"
#include "service/engine_globals.h"

#include "waveform/common/xdebug_waveform_paths.h"
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
using xdebug_waveform::StreamAnalysis;
using xdebug_waveform::StreamAnalyzer;
using xdebug_waveform::StreamConfig;
using xdebug_waveform::StreamExporter;
using xdebug_waveform::StreamManager;
using xdebug_waveform::StreamQueryOptions;

Json stream_config_list_example() {
    return Json{{"api_version", "xdebug.v1"},
                {"action", "stream.config.list"},
                {"target", {{"session_id", "case_a"}}},
                {"args", Json::object()}};
}
class StreamConfigListHandler : public EngineActionHandler {
public:
    const char* action_name() const override { return "stream.config.list"; }
    bool needs_design() const override { return false; }
    bool needs_waveform() const override { return true; }
    Json run(const Json& request, EngineActionContext& ctx) const override {
        Json args = request.value("args", Json::object());
        Json output = args.value("output", Json::object());
        bool verbose = output.value("verbose", false);
        std::string name = args.value("name", std::string());
        StreamManager manager;
        if (!name.empty()) {
            StreamConfig config;
            if (!manager.get_stream(xdebug_waveform::g_session_id, name, config)) {
                Json example = stream_config_list_example();
                example["args"] = {{"name", "req_stream"}};
                return make_handler_error(
                    "CONFIG_NOT_FOUND",
                    "stream config not found: " + name,
                    {{"invalid_arg", "args.name"},
                     {"expected", "name of a previously loaded stream config"},
                     {"missing_name", name},
                     {"missing_resource", "stream config"},
                     {"correct_example", example},
                     {"example_note", "Example only; omit args.name to list all loaded stream configs."},
                     {"next_actions", Json::array({"Call stream.config.list with args:{} to list loaded stream names.",
                                                    "Call stream.config.load before showing a named stream config."})}});
            }
            return Json{{"summary", {{"name", name}}},
                        {"stream", xdebug_waveform::stream_config_json(config)}};
        }
        auto streams = manager.list_streams(xdebug_waveform::g_session_id);
        Json arr = Json::array();
        for (const auto& stream : streams) {
            if (verbose) arr.push_back(xdebug_waveform::stream_config_json(stream));
            else {
                Json item = {{"name", stream.name},
                             {"sampling_mode", "clock_edge"},
                             {"clock", stream.clock_sample.clock},
                             {"edge", xdebug_waveform::clock_edge_kind_text(stream.clock_sample.edge)},
                             {"handshake", xdebug_waveform::stream_handshake_text(stream)},
                             {"packet", xdebug_waveform::stream_packet_enabled(stream) ? "sop/eop" : "none"},
                             {"field_count", stream.beat_fields.size() +
                                 stream.packet_stable_fields.size() + (stream.data.empty() ? 0 : 1)},
                             {"channel_id_valid", stream.channel_id_valid},
                             {"allow_interleaving", stream.allow_interleaving}};
                if (stream.clock_sample.edge != xdebug_waveform::ClockEdgeKind::Negedge)
                    item["sample_point"] = xdebug_waveform::clock_sample_point_text(stream.clock_sample.sample_point);
                arr.push_back(item);
            }
        }
        return Json{{"summary", {{"count", streams.size()}}}, {"streams", arr}};
    }
};

}  // namespace

std::unique_ptr<EngineActionHandler> make_stream_config_list_handler() {
    return std::unique_ptr<EngineActionHandler>(new StreamConfigListHandler);
}

}  // namespace xdebug_design
