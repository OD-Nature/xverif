#pragma once

#include "npi_fsdb.h"
#include "npi_L1.h"

#include <string>
#include <utility>

namespace xdebug_core {

struct TimeParseOptions {
    bool allow_max = false;
    bool use_fsdb_max = false;
    bool allow_negative = false;
    std::string default_unit = "ns";
};

enum class TimeRenderUnit {
    Ns,
    Ps,
    Us,
    Auto
};

struct TimeRenderOptions {
    TimeRenderUnit unit = TimeRenderUnit::Ns;
};

class ScopedTimeRenderOptions {
public:
    explicit ScopedTimeRenderOptions(const TimeRenderOptions& options);
    ~ScopedTimeRenderOptions();
    ScopedTimeRenderOptions(const ScopedTimeRenderOptions&) = delete;
    ScopedTimeRenderOptions& operator=(const ScopedTimeRenderOptions&) = delete;

private:
    TimeRenderOptions previous_;
};

bool parse_time_render_unit(const std::string& text,
                            TimeRenderUnit& unit,
                            std::string& error);

bool parse_time(npiFsdbFileHandle fsdb,
                const std::string& text,
                const TimeParseOptions& options,
                npiFsdbTime& out_time,
                std::string& error);

bool convert_time(npiFsdbFileHandle fsdb,
                  double value,
                  const std::string& unit,
                  npiFsdbTime& out_time,
                  std::string& error);

std::string format_time(npiFsdbFileHandle fsdb, npiFsdbTime time);
std::string format_duration(npiFsdbFileHandle fsdb, npiFsdbTime duration);
std::pair<std::string, std::string> format_time_range(npiFsdbFileHandle fsdb,
                                                       npiFsdbTime begin,
                                                       npiFsdbTime end);

}  // namespace xdebug_core
