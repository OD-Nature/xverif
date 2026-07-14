#include "axi_transaction_json.h"
#include "core/npi/time_contract.h"

namespace xdebug_waveform {

AxiJson axi_transaction_to_json(npiFsdbFileHandle file,
                                const AxiTransaction& txn,
                                bool include_data) {
    AxiJson out;
    out["direction"] = txn.is_write ? "write" : "read";
    if (txn.is_write) out["phase_order"] = txn.phase_order;
    out["latency"] = xdebug_core::format_duration(
        file, txn.resp_time >= txn.addr_time ? txn.resp_time - txn.addr_time : 0);
    out["response_dependency_violation"] = txn.response_dependency_violation;

    AxiJson address;
    address["channel"] = txn.is_write ? "aw" : "ar";
    if (txn.has_addr_valid_begin_time)
        address["valid_begin_time"] = xdebug_core::format_time(file, txn.addr_valid_begin_time);
    address["handshake_time"] = xdebug_core::format_time(file, txn.addr_time);
    address["addr"] = txn.addr;
    address["id"] = txn.id;
    address["len"] = txn.len;
    address["size"] = txn.size;
    address["burst"] = txn.burst;
    out["address"] = std::move(address);

    if (!txn.data_handshake_times.empty() || !txn.data.empty()) {
        AxiJson data;
        data["channel"] = txn.is_write ? "w" : "r";
        if (txn.has_first_data_valid_begin_time)
            data["valid_begin_time"] = xdebug_core::format_time(
                file, txn.first_data_valid_begin_time);
        data["first_handshake_time"] = xdebug_core::format_time(file, txn.first_data_time);
        data["last_handshake_time"] = xdebug_core::format_time(file, txn.last_data_time);
        data["beat_count"] = txn.data.size();
        data["expected_beat_count"] = txn.expected_beat_count;
        if (include_data) {
            AxiJson beats = AxiJson::array();
            for (size_t i = 0; i < txn.data.size(); ++i) {
                AxiJson beat = {
                    {"index", i + 1},
                    {"handshake_time", xdebug_core::format_time(
                        file, i < txn.data_handshake_times.size()
                            ? txn.data_handshake_times[i] : txn.first_data_time)},
                    {"data", txn.data[i]},
                };
                if (txn.is_write && i < txn.wstrb.size()) beat["wstrb"] = txn.wstrb[i];
                if (!txn.is_write && i < txn.data_resp.size()) beat["resp"] = txn.data_resp[i];
                beat["last"] = i < txn.data_last.size()
                    ? txn.data_last[i] : i + 1 == txn.data.size();
                beats.push_back(std::move(beat));
            }
            data["beats"] = std::move(beats);
        }
        out["data"] = std::move(data);
    }

    out["response"] = {
        {"channel", txn.is_write ? "b" : "r"},
        {"handshake_time", xdebug_core::format_time(file, txn.resp_time)},
        {"resp", txn.resp},
    };
    return out;
}

} // namespace xdebug_waveform
