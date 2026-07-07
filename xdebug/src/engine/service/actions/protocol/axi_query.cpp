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

static bool ensure_axi_analyzed(const std::string& name,
                                 xdebug_waveform::AxiConfig& cfg,
                                 std::string& err) {
    xdebug_waveform::AxiManager am;
    if (!am.get_axi(xdebug_waveform::g_session_id, name, cfg)) {
        err = "AXI config not found: " + name;
        return false;
    }
    if (!xdebug_waveform::g_axi_analyzer.analyze(name,
            xdebug_waveform::g_fsdb_file, cfg)) {
        err = "Failed to analyze AXI: " + name;
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

class AxiQueryHandler : public EngineActionHandler {
public:
    const char* action_name() const override { return "axi.query"; }
    bool needs_design() const override { return false; }
    bool needs_waveform() const override { return true; }
    Json run(const Json& r, EngineActionContext& ctx) const override {
        using namespace xdebug_waveform;
        Json a = r.value("args", Json::object());
        std::string name = a.value("name", "");
        if (name.empty()) return Json({{"error","MISSING_FIELD"},{"message","args.name"}});

        AxiConfig cfg; std::string err;
        if (!ensure_axi_analyzed(name, cfg, err))
            return Json({{"error","ANALYZE_FAILED"},{"message",err}});

        std::string dir = a.value("direction", "write");
        bool is_write = (dir != "read");
        std::string addr_str = a.value("address", a.value("addr", ""));
        std::string id_str = a.value("id", "");
        int num = a.value("num", -1);
        bool last = a.value("last", false);

        const AxiTransaction* txn = nullptr;
        bool found = false;
        if (!addr_str.empty()) {
            uint64_t addr = 0;
            std::string parse_err;
            if (!parse_user_uint64_literal(addr_str, addr, parse_err))
                return Json({{"error","VALUE_FORMAT_INVALID"},{"message",parse_err}});
            if (!id_str.empty()) {
                uint64_t id_value = 0;
                if (!parse_user_uint64_literal(id_str, id_value, parse_err))
                    return Json({{"error","VALUE_FORMAT_INVALID"},{"message",parse_err}});
                id_str = std::to_string(id_value);
            }
            if (!id_str.empty()) {
                if (num >= 0)
                    found = is_write ? g_axi_analyzer.get_write_by_addr_num(name, addr, id_str.c_str(), (size_t)num, txn)
                                     : g_axi_analyzer.get_read_by_addr_num(name, addr, id_str.c_str(), (size_t)num, txn);
                else if (last)
                    found = is_write ? g_axi_analyzer.get_write_by_addr_last(name, addr, id_str.c_str(), txn)
                                     : g_axi_analyzer.get_read_by_addr_last(name, addr, id_str.c_str(), txn);
                else
                    found = is_write ? g_axi_analyzer.get_write_by_addr(name, addr, id_str.c_str(), txn)
                                     : g_axi_analyzer.get_read_by_addr(name, addr, id_str.c_str(), txn);
            } else {
                if (num >= 0)
                    found = is_write ? g_axi_analyzer.get_write_by_addr_num(name, addr, (size_t)num, txn)
                                     : g_axi_analyzer.get_read_by_addr_num(name, addr, (size_t)num, txn);
                else if (last)
                    found = is_write ? g_axi_analyzer.get_write_by_addr_last(name, addr, txn)
                                     : g_axi_analyzer.get_read_by_addr_last(name, addr, txn);
                else
                    found = is_write ? g_axi_analyzer.get_write_by_addr(name, addr, txn)
                                     : g_axi_analyzer.get_read_by_addr(name, addr, txn);
            }
        } else if (!id_str.empty()) {
            if (num >= 0)
                found = is_write ? g_axi_analyzer.get_write_by_num(name, id_str.c_str(), (size_t)num, txn)
                                 : g_axi_analyzer.get_read_by_num(name, id_str.c_str(), (size_t)num, txn);
            else if (last)
                found = is_write ? g_axi_analyzer.get_write_last(name, id_str.c_str(), txn)
                                 : g_axi_analyzer.get_read_last(name, id_str.c_str(), txn);
        } else if (num >= 0) {
            found = is_write ? g_axi_analyzer.get_write_by_num(name, (size_t)num, txn)
                             : g_axi_analyzer.get_read_by_num(name, (size_t)num, txn);
        } else if (last) {
            found = is_write ? g_axi_analyzer.get_write_last(name, txn)
                             : g_axi_analyzer.get_read_last(name, txn);
        } else {
            size_t cnt = is_write ? g_axi_analyzer.get_write_count(name)
                                  : g_axi_analyzer.get_read_count(name);
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
            tj["time"] = txn->addr_time;
            tj["addr"] = txn->addr; tj["id"] = txn->id;
            tj["len"] = txn->len; tj["size"] = txn->size;
            tj["burst"] = txn->burst; tj["is_write"] = txn->is_write;
            if (!txn->data.empty()) { Json da = Json::array(); for (auto& d : txn->data) da.push_back(d); tj["data"] = da; }
            out["transaction"] = tj;
            out["summary"]["addr"] = txn->addr;
        }
        return out;
    }
};

}  // namespace

std::unique_ptr<EngineActionHandler> make_axi_query_handler() {
    return std::unique_ptr<EngineActionHandler>(new AxiQueryHandler);
}

}  // namespace xdebug_design
