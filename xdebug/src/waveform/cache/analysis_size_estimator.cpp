#include "analysis_size_estimator.h"

#include "waveform/apb/apb_analyzer.h"
#include "waveform/axi/axi_transaction_tracker.h"
#include "waveform/stream/stream_analyzer.h"

#include <map>
#include <string>
#include <vector>

namespace xdebug_waveform {
namespace {

template <typename Key, typename Value>
std::size_t map_storage_bytes(const std::map<Key, Value>& values) {
    // Three links plus allocator/node bookkeeping approximate a red-black tree
    // node. Phase 0 compares this deterministic estimate with RSS and freezes a
    // safety factor; it is not presented as exact allocator introspection.
    return sizeof(values) + values.size() *
        (sizeof(std::pair<const Key, Value>) + 4 * sizeof(void*));
}

std::size_t stream_value_map_bytes(const std::map<std::string, StreamValue>& values) {
    std::size_t bytes = map_storage_bytes(values);
    for (const auto& item : values) {
        bytes += item.first.capacity();
        bytes += item.second.bits.capacity();
    }
    return bytes;
}

std::size_t axi_transaction_bytes_impl(const AxiTransaction& txn) {
    std::size_t bytes = sizeof(AxiTransaction);
    const std::string* strings[] = {
        &txn.addr, &txn.id, &txn.len, &txn.size, &txn.burst, &txn.resp,
        &txn.phase_order,
    };
    for (const std::string* value : strings) bytes += value->capacity();
    const std::vector<std::string>* string_vectors[] = {
        &txn.data, &txn.wstrb, &txn.data_resp,
    };
    for (const std::vector<std::string>* values : string_vectors) {
        bytes += values->capacity() * sizeof(std::string);
        for (const auto& value : *values) bytes += value.capacity();
    }
    bytes += txn.data_handshake_times.capacity() * sizeof(npiFsdbTime);
    bytes += txn.data_last.capacity() * sizeof(bool);
    return bytes;
}

std::size_t axi_transaction_vector_bytes(const std::vector<AxiTransaction>& values) {
    std::size_t bytes = sizeof(values) + values.capacity() * sizeof(AxiTransaction);
    for (const auto& value : values)
        bytes += estimate_axi_transaction_bytes(value) - sizeof(value);
    return bytes;
}

std::size_t stream_row_bytes(const StreamRow& row) {
    return sizeof(StreamRow) + row.stall_reason.capacity() +
        stream_value_map_bytes(row.fields) +
        stream_value_map_bytes(row.packet_stable_fields) +
        row.channel.bits.capacity();
}

std::size_t stream_beat_bytes(const StreamBeat& beat) {
    return sizeof(StreamBeat) + stream_value_map_bytes(beat.fields);
}

std::size_t stream_packet_bytes(const StreamPacket& packet) {
    std::size_t bytes = sizeof(StreamPacket) + packet.channel.bits.capacity();
    bytes += stream_value_map_bytes(packet.packet_stable_fields);
    bytes += stream_value_map_bytes(packet.first_fields);
    bytes += stream_value_map_bytes(packet.last_fields);
    bytes += stream_value_map_bytes(packet.first_filter_fields);
    bytes += stream_value_map_bytes(packet.last_filter_fields);
    bytes += packet.beats.capacity() * sizeof(StreamBeat);
    for (const auto& beat : packet.beats) bytes += stream_beat_bytes(beat) - sizeof(beat);
    bytes += packet.packet_stable_mismatches.capacity() * sizeof(StreamPacketStableMismatch);
    for (const auto& mismatch : packet.packet_stable_mismatches) {
        bytes += mismatch.field.capacity();
        bytes += mismatch.expected.bits.capacity();
        bytes += mismatch.actual.bits.capacity();
    }
    return bytes;
}

}  // namespace

std::size_t estimate_apb_result_bytes(const ApbResult& result) {
    std::size_t bytes = sizeof(ApbResult);
    bytes += result.all.capacity() * sizeof(const ApbTransaction*);
    const std::vector<ApbTransaction>* vectors[] = {&result.writes, &result.reads};
    for (const auto* values : vectors) {
        bytes += values->capacity() * sizeof(ApbTransaction);
        for (const auto& txn : *values) {
            bytes += txn.addr.capacity() + txn.data.capacity();
        }
    }
    return bytes;
}

std::size_t estimate_axi_transaction_bytes(const AxiTransaction& transaction) {
    return axi_transaction_bytes_impl(transaction);
}

std::size_t estimate_axi_result_bytes(const AxiResult& result) {
    std::size_t bytes = sizeof(AxiResult);
    const std::vector<AxiTransaction>* vectors[] = {
        &result.all, &result.writes, &result.reads,
        &result.pending_writes, &result.pending_reads,
    };
    for (const auto* values : vectors) {
        bytes += axi_transaction_vector_bytes(*values) - sizeof(*values);
    }
    bytes += result.outstanding_samples.capacity() * sizeof(AxiOutstandingSample);
    for (const auto& sample : result.outstanding_samples) {
        bytes += map_storage_bytes(sample.read_by_id);
        bytes += map_storage_bytes(sample.write_by_id);
        for (const auto& item : sample.read_by_id) bytes += item.first.capacity();
        for (const auto& item : sample.write_by_id) bytes += item.first.capacity();
    }
    bytes += result.all_by_resp_time.capacity() * sizeof(std::size_t);
    bytes += map_storage_bytes(result.diagnostics.max_write_outstanding_by_id);
    bytes += map_storage_bytes(result.diagnostics.max_read_outstanding_by_id);
    for (const auto& item : result.diagnostics.max_write_outstanding_by_id)
        bytes += item.first.capacity();
    for (const auto& item : result.diagnostics.max_read_outstanding_by_id)
        bytes += item.first.capacity();
    return bytes;
}

std::size_t estimate_stream_analysis_bytes(const StreamAnalysis& analysis) {
    std::size_t bytes = sizeof(StreamAnalysis);
    bytes += analysis.transfers.capacity() * sizeof(StreamRow);
    for (const auto& row : analysis.transfers) bytes += stream_row_bytes(row) - sizeof(row);
    bytes += stream_row_bytes(analysis.first_transfer) - sizeof(analysis.first_transfer);
    bytes += stream_row_bytes(analysis.last_transfer) - sizeof(analysis.last_transfer);
    bytes += analysis.stalls.capacity() * sizeof(StreamStallWindow);
    for (const auto& stall : analysis.stalls) bytes += stall.reason.capacity();
    bytes += analysis.packets.capacity() * sizeof(StreamPacket);
    for (const auto& packet : analysis.packets)
        bytes += stream_packet_bytes(packet) - sizeof(packet);
    bytes += stream_packet_bytes(analysis.first_matched_packet) -
        sizeof(analysis.first_matched_packet);
    bytes += stream_packet_bytes(analysis.last_matched_packet) -
        sizeof(analysis.last_matched_packet);
    return bytes;
}

std::size_t estimate_stream_base_analysis_bytes(
    const StreamBaseAnalysis& analysis) {
    std::size_t bytes = sizeof(StreamBaseAnalysis);
    bytes += analysis.samples.capacity() * sizeof(StreamSampleMetadata);
    for (const auto& sample : analysis.samples)
        bytes += sample.stall_reason.capacity();
    bytes += analysis.transfer_sample_ids.capacity() * sizeof(std::size_t);
    bytes += analysis.channels.capacity() * sizeof(StreamValue);
    for (const auto& channel : analysis.channels)
        bytes += channel.bits.capacity();
    auto add_schema = [&](const std::vector<std::string>& schema) {
        bytes += schema.capacity() * sizeof(std::string);
        for (const auto& name : schema) bytes += name.capacity();
    };
    add_schema(analysis.field_schema);
    add_schema(analysis.packet_stable_field_schema);
    auto add_columns = [&](const std::map<std::string,
                                          std::vector<StreamValue>>& columns) {
        bytes += map_storage_bytes(columns);
        for (const auto& column : columns) {
            bytes += column.first.capacity();
            bytes += column.second.capacity() * sizeof(StreamValue);
            for (const auto& value : column.second)
                bytes += value.bits.capacity();
        }
    };
    add_columns(analysis.field_columns);
    add_columns(analysis.packet_stable_field_columns);
    bytes += analysis.packets.capacity() * sizeof(StreamBasePacket);
    for (const auto& packet : analysis.packets) {
        bytes += packet.transfer_ordinals.capacity() * sizeof(std::size_t);
        bytes += packet.channel.bits.capacity();
        bytes += packet.stable_mismatches.capacity() *
            sizeof(StreamBaseStableMismatch);
        for (const auto& mismatch : packet.stable_mismatches) {
            bytes += mismatch.field.capacity();
            bytes += mismatch.expected.bits.capacity();
            bytes += mismatch.actual.bits.capacity();
        }
    }
    return bytes;
}

}  // namespace xdebug_waveform
