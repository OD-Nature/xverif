#include "service/engine_action_handler.h"
#include "service/engine_action_registry.h"
#include "service/engine_globals.h"

#include "waveform/apb/apb_manager.h"
#include "waveform/apb/apb_analyzer.h"
#include "waveform/axi/axi_manager.h"
#include "waveform/axi/axi_analyzer.h"
#include "waveform/axi/axi_exporter.h"
#include "waveform/common/xdebug_waveform_paths.h"
#include "waveform/value/logic_value.h"

#include <fstream>
#include <memory>
#include <ctime>
#include <sstream>
#include <algorithm>

namespace xdebug_design {
namespace {
class AxiExportHandler : public EngineActionHandler {
public:
    const char* action_name() const override { return "axi.export"; }
    bool needs_design() const override { return false; }
    bool needs_waveform() const override { return true; }
    Json run(const Json& r, EngineActionContext& ctx) const override {
        using namespace xdebug_waveform;
        Json a = r.value("args", Json::object());
        std::string name = a.value("name", "");
        if (name.empty()) return Json({{"error","MISSING_FIELD"},{"message","args.name"}});

        AxiManager am;
        AxiConfig cfg;
        if (!am.get_axi(g_session_id, name, cfg))
            return Json({{"error","CONFIG_NOT_FOUND"},{"message","AXI config not found: " + name}});

        Json tr = a.value("time_range", Json::object());
        std::string begin_s;
        std::string end_s;
        if (tr.is_object()) {
            begin_s = tr.value("begin", std::string());
            end_s = tr.value("end", std::string());
        }
        if (begin_s.empty() || end_s.empty())
            return Json({{"error","MISSING_FIELD"},{"message","axi.export requires args.time_range.begin/end"}});

        npiFsdbTime begin = 0, end = 0;
        std::string time_err;
        if (!parse_user_time(begin_s.c_str(), false, begin, time_err))
            return Json({{"error","TIME_SPEC_INVALID"},{"message",time_err}});
        if (!parse_user_time(end_s.c_str(), true, end, time_err))
            return Json({{"error","TIME_SPEC_INVALID"},{"message",time_err}});
        if (end < begin)
            return Json({{"error","TIME_SPEC_INVALID"},{"message","axi.export end time is before begin time"}});

        Json output = a.value("output", Json::object());
        std::string format = output.value("file_format", std::string("tsv"));
        if (format != "tsv" && format != "csv")
            return Json({{"error","INVALID_REQUEST"},{"message","output.file_format must be tsv or csv"}});

        std::string output_prefix = output.value("path", std::string());
        if (output_prefix.empty()) {
            std::ostringstream oss;
            oss << xdebug_waveform_axi_exports_dir(g_session_id)
                << "/" << name << "_" << begin << "_" << end << "_" << std::time(nullptr);
            output_prefix = oss.str();
        }

        AxiExporter exporter;
        AxiExportResult result;
        result.format = format;
        std::string error;
        if (!exporter.scan(g_fsdb_file, cfg, begin, end, result, error))
            return Json({{"error","ANALYZE_FAILED"},{"message",error}});
        result.format = format;

        auto txn_json = [](const AxiExportTransaction& txn) {
            npiFsdbTime latency = txn.completion_time >= txn.addr_time ? txn.completion_time - txn.addr_time : 0;
            return Json{{"seq", txn.seq},
                        {"direction", txn.is_write ? "write" : "read"},
                        {"completion_time", format_time(txn.completion_time)},
                        {"addr_time", format_time(txn.addr_time)},
                        {"first_data_time", format_time(txn.first_data_time)},
                        {"last_data_time", format_time(txn.last_data_time)},
                        {"latency", format_duration(latency)},
                        {"id", txn.id},
                        {"addr", txn.addr},
                        {"len", txn.len},
                        {"size", txn.size},
                        {"burst", txn.burst},
                        {"resp", txn.resp},
                        {"beat_count", txn.beat_count},
                        {"expected_beat_count", txn.expected_beat_count}};
        };

        Json summary = {{"name", name},
                        {"write_count", result.writes.size()},
                        {"read_count", result.reads.size()},
                        {"total_count", result.writes.size() + result.reads.size()},
                        {"row_count", result.writes.size() + result.reads.size()},
                        {"format", format},
                        {"status", output_prefix.empty() ? "preview" : "written"},
                        {"output_written", !output_prefix.empty()},
                        {"truncated", false}};

        if (output_prefix.empty()) {
            Json preview;
            preview["writes"] = Json::array();
            preview["reads"] = Json::array();
            size_t wlimit = std::min<size_t>(result.writes.size(), 8);
            size_t rlimit = std::min<size_t>(result.reads.size(), 8);
            for (size_t i = 0; i < wlimit; ++i) preview["writes"].push_back(txn_json(result.writes[i]));
            for (size_t i = 0; i < rlimit; ++i) preview["reads"].push_back(txn_json(result.reads[i]));
            Json out;
            out["summary"] = summary;
            out["name"] = name;
            out["begin"] = format_time(begin);
            out["end"] = format_time(end);
            out["scan_begin"] = format_time(result.scan_begin);
            out["scan_end"] = format_time(result.scan_end);
            out["preview"] = preview;
            out["write_count"] = result.writes.size();
            out["read_count"] = result.reads.size();
            out["total_count"] = result.writes.size() + result.reads.size();
            return out;
        }

        std::string write_file, read_file, meta_file;
        if (!exporter.write_files(output_prefix, result, write_file, read_file, meta_file, error))
            return Json({{"error","EXPORT_FAILED"},{"message",error}});

        Json out;
        summary["output"] = {{"path", output_prefix},
                             {"write_path", write_file},
                             {"read_path", read_file},
                             {"meta_path", meta_file},
                             {"file_format", format}};
        out["summary"] = summary;
        out["name"] = name;
        out["begin"] = format_time(begin);
        out["end"] = format_time(end);
        out["scan_begin"] = format_time(result.scan_begin);
        out["scan_end"] = format_time(result.scan_end);
        out["write_count"] = result.writes.size();
        out["read_count"] = result.reads.size();
        out["total_count"] = result.writes.size() + result.reads.size();
        return out;
    }
};

}  // namespace

std::unique_ptr<EngineActionHandler> make_axi_export_handler() {
    return std::unique_ptr<EngineActionHandler>(new AxiExportHandler);
}

}  // namespace xdebug_design
