#include "waveform/cache/analysis_size_estimator.h"
#include "waveform/stream/stream_analyzer.h"

#include <cassert>
#include <iostream>
#include <string>

using namespace xdebug_waveform;

int main() {
    StreamBaseAnalysis base;
    base.field_schema = {"data", "seq", "tag"};
    base.packet_stable_field_schema = {"opcode"};
    for (const auto& name : base.field_schema)
        base.field_columns[name] = std::vector<StreamValue>();
    for (const auto& name : base.packet_stable_field_schema)
        base.packet_stable_field_columns[name] = std::vector<StreamValue>();

    StreamAnalysis legacy;
    for (int i = 0; i < 1000; ++i) {
        StreamSampleMetadata sample;
        sample.time = static_cast<npiFsdbTime>(i * 10);
        sample.vld = true;
        sample.rdy = true;
        sample.transfer = true;
        sample.transfer_ordinal = i;
        base.samples.push_back(sample);
        base.transfer_sample_ids.push_back(static_cast<std::size_t>(i));

        const std::string suffix = std::to_string(i);
        StreamRow row;
        row.cycle = i;
        row.time = sample.time;
        row.vld = true;
        row.rdy = true;
        row.transfer = true;
        for (const auto& name : base.field_schema) {
            StreamValue value{std::string(32 - suffix.size(), '0') + suffix,
                              true};
            base.field_columns[name].push_back(value);
            row.fields[name] = value;
        }
        StreamValue opcode{"10100011", true};
        base.packet_stable_field_columns["opcode"].push_back(opcode);
        row.packet_stable_fields["opcode"] = opcode;
        base.channels.push_back(StreamValue{"00", true});
        row.channel = base.channels.back();
        legacy.transfers.push_back(row);

        if ((i % 4) == 0) base.packets.push_back(StreamBasePacket());
        base.packets.back().transfer_ordinals.push_back(
            static_cast<std::size_t>(i));
    }

    const std::size_t base_bytes = estimate_stream_base_analysis_bytes(base);
    const std::size_t legacy_bytes = estimate_stream_analysis_bytes(legacy);
    assert(base.field_columns["data"].size() ==
           base.transfer_sample_ids.size());
    assert(base.packet_stable_field_columns["opcode"].size() ==
           base.transfer_sample_ids.size());
    assert(base_bytes < legacy_bytes);
    std::cout << "stream base estimator: base=" << base_bytes
              << " legacy=" << legacy_bytes << "\n";
    return 0;
}
