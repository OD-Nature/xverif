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

namespace xdebug_design {
namespace {

static bool ensure_apb_analyzed(const std::string& name,
                                 xdebug_waveform::ApbConfig& cfg,
                                 std::string& err) {
    xdebug_waveform::ApbManager am;
    if (!am.get_apb(xdebug_waveform::g_session_id, name, cfg)) {
        err = "APB config not found: " + name;
        return false;
    }
    if (!xdebug_waveform::g_apb_analyzer.analyze(name,
            xdebug_waveform::g_fsdb_file, cfg)) {
        err = "Failed to analyze APB: " + name;
        return false;
    }
    return true;
}
static bool parse_user_uint64_literal(const std::string& text,
                                      uint64_t& out,
                                      std::string& err) {
    xdebug_waveform::LogicValue value = xdebug_waveform::parse_user_logic_literal(text);
    if (!value.valid) {
        err = value.error;
        return false;
    }
    if (xdebug_waveform::logic_value_has_xz(value) || value.bits.size() > 64) {
        err = "value literal must be known and at most 64 bits: " + text;
        return false;
    }
    out = 0;
    for (char c : value.bits) {
        out <<= 1ULL;
        if (c == '1') out |= 1ULL;
    }
    return true;
}

class ApbQueryHandler : public EngineActionHandler {
public:
    const char* action_name() const override { return "apb.query"; }
    bool needs_design() const override { return false; }
    bool needs_waveform() const override { return true; }
    Json run(const Json& r, EngineActionContext& ctx) const override {
        using namespace xdebug_waveform;
        Json a = r.value("args", Json::object());
        std::string name = a.value("name", "");
        if (name.empty()) return Json({{"error","MISSING_FIELD"},{"message","args.name"}});

        ApbConfig cfg; std::string err;
        if (!ensure_apb_analyzed(name, cfg, err))
            return Json({{"error","ANALYZE_FAILED"},{"message",err}});

        std::string dir = a.value("direction", "write");
        bool is_write = (dir != "read");
        std::string addr_str = a.value("address", a.value("addr", ""));
        int num = a.value("num", -1);
        bool last = a.value("last", false);

        const ApbTransaction* txn = nullptr;
        bool found = false;
        if (!addr_str.empty()) {
            uint64_t addr = 0;
            std::string parse_err;
            if (!parse_user_uint64_literal(addr_str, addr, parse_err))
                return Json({{"error","VALUE_FORMAT_INVALID"},{"message",parse_err}});
            if (num >= 0) {
                found = is_write ? g_apb_analyzer.get_write_by_addr_num(name, addr, (size_t)num, txn)
                                 : g_apb_analyzer.get_read_by_addr_num(name, addr, (size_t)num, txn);
            } else if (last) {
                found = is_write ? g_apb_analyzer.get_write_by_addr_last(name, addr, txn)
                                 : g_apb_analyzer.get_read_by_addr_last(name, addr, txn);
            } else {
                found = is_write ? g_apb_analyzer.get_write_by_addr(name, addr, txn)
                                 : g_apb_analyzer.get_read_by_addr(name, addr, txn);
            }
        } else if (num >= 0) {
            found = is_write ? g_apb_analyzer.get_write_by_num(name, (size_t)num, txn)
                             : g_apb_analyzer.get_read_by_num(name, (size_t)num, txn);
        } else if (last) {
            found = is_write ? g_apb_analyzer.get_write_last(name, txn)
                             : g_apb_analyzer.get_read_last(name, txn);
        } else {
            // No filter — return count
            size_t cnt = is_write ? g_apb_analyzer.get_write_count(name)
                                  : g_apb_analyzer.get_read_count(name);
            Json out;
            out["summary"] = {{"name",name},{"direction",dir},{"count",(int)cnt}};
            out["name"] = name; out["direction"] = dir; out["count"] = (int)cnt;
            return out;
        }

        Json out;
        out["summary"] = {{"name",name},{"direction",dir},{"found",found}};
        out["name"] = name; out["direction"] = dir; out["found"] = found;
        if (found && txn) {
            Json tj;
            tj["time"] = txn->time;
            tj["addr"] = txn->addr;
            tj["data"] = txn->data;
            tj["is_write"] = txn->is_write;
            tj["has_error"] = txn->has_error;
            out["transaction"] = tj;
            out["summary"]["addr"] = txn->addr;
        }
        return out;
    }
};

}  // namespace

std::unique_ptr<EngineActionHandler> make_apb_query_handler() {
    return std::unique_ptr<EngineActionHandler>(new ApbQueryHandler);
}

}  // namespace xdebug_design
