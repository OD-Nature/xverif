#pragma once

#include "stream_analyzer.h"

#include <string>

namespace xdebug_waveform {

class StreamExporter {
public:
    bool export_transfer_file(const std::string& output_file,
                              const std::string& format,
                              const StreamConfig& config,
                              const StreamAnalysis& analysis,
                              std::string& meta_file,
                              std::string& error);
    bool export_packet_file(const std::string& output_file,
                            const std::string& format,
                            const StreamConfig& config,
                            const StreamAnalysis& analysis,
                            std::string& meta_file,
                            std::string& error);
    bool export_packet_beats_file(const std::string& output_file,
                                  const std::string& format,
                                  const StreamConfig& config,
                                  const StreamAnalysis& analysis,
                                  std::string& meta_file,
                                  std::string& error);
};

} // namespace xdebug_waveform
