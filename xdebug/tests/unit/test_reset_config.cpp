#include "waveform/common/reset_config.h"

#include <cassert>

using xdebug_waveform::ResetConfig;

int main() {
    ResetConfig config;
    std::string error;
    assert(xdebug_waveform::parse_reset_config(
        {{"signal", "top.rst"}, {"polarity", "active_low"}}, config, error));
    assert(xdebug_waveform::reset_is_active(config, "0"));
    assert(!xdebug_waveform::reset_is_active(config, "1"));
    assert(xdebug_waveform::reset_is_active(config, "X"));

    assert(xdebug_waveform::parse_reset_config(
        {{"signal", "top.rst"}, {"polarity", "active_high"}}, config, error));
    assert(xdebug_waveform::reset_is_active(config, "1'b1"));
    assert(!xdebug_waveform::reset_is_active(config, "1'b0"));
    assert(xdebug_waveform::reset_is_active(config, "Z"));
    assert(!xdebug_waveform::parse_reset_config(
        {{"signal", "top.rst"}, {"polarity", "low"}}, config, error));
    return 0;
}
