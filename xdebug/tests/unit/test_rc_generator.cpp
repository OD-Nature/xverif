#include "service/rc_generator.h"

#include <cassert>
#include <string>

using namespace xdebug_waveform;

int main() {
    std::string err;
    assert(rc_dot_path_to_slash("top.u.sig[3:0]", err) == "/top/u/sig[3:0]");
    assert(err.empty());
    std::string bad = rc_dot_path_to_slash("/top/u/sig", err);
    assert(bad.empty());
    assert(err.find("dot hierarchy") != std::string::npos);

    Json doc = {
        {"file_time_scale", "1ns"},
        {"window_time_unit", "1ns"},
        {"signal_spacing", 5},
        {"cursor", "120ns"},
        {"main_marker", "120ns"},
        {"zoom", {{"begin", "0ns"}, {"end", "500ns"}}},
        {"groups", Json::array({
            {
                {"name", "ClockReset"},
                {"expanded", true},
                {"signals", Json::array({
                    "top.clk",
                    {{"path", "top.rst_n"}, {"radix", "bin"}, {"height", 15}}
                })}
            },
            {
                {"name", "Analog"},
                {"signals", Json::array({
                    {
                        {"path", "top.u_adc.sample[11:0]"},
                        {"waveform", "analog"},
                        {"height", 40},
                        {"analog", {
                            {"display_style", "pwl"},
                            {"grid_x", true},
                            {"grid_y", true},
                            {"unit", "m"},
                            {"options", Json::array({"-gs2", "10"})}
                        }}
                    }
                })}
            },
            {
                {"name", "AXI"},
                {"subgroups", Json::array({
                    {
                        {"name", "AW"},
                        {"signals", Json::array({
                            "top.u_axi.awvalid",
                            "top.u_axi.awready",
                            {{"path", "top.u_axi.awaddr[31:0]"}, {"radix", "hex"}, {"notation", "unsigned"}}
                        })},
                        {"expr_signals", Json::array({
                            {
                                {"name", "aw_fire"},
                                {"bit_size", 1},
                                {"notation", "UUU"},
                                {"expr", "$valid & $ready"},
                                {"signals", {
                                    {"valid", "top.u_axi.awvalid"},
                                    {"ready", "top.u_axi.awready"}
                                }}
                            }
                        })}
                    }
                })}
            }
        })},
        {"user_markers", Json::array({
            {{"name", "reset_done"}, {"time", "120ns"}, {"color", "ID_YELLOW5"}, {"linestyle", "solid"}}
        })}
    };

    RcConfig cfg;
    err.clear();
    assert(parse_rc_config_json(doc, cfg, err));
    Json counts = rc_config_counts(cfg);
    assert(counts["group_count"] == 4);
    assert(counts["signal_count"] == 6);
    assert(counts["expr_signal_count"] == 1);
    assert(counts["marker_count"] == 1);

    std::string rc = render_signal_rc(cfg);
    assert(rc.find("openDirFile") == std::string::npos);
    assert(rc.find("activeDirFile") == std::string::npos);
    assert(rc.find("addGroup -e \"ClockReset\"") != std::string::npos);
    assert(rc.find("addSignal -h 15 -BIN /top/rst_n") != std::string::npos);
    assert(rc.find("addSignal -w analog -ds pwl -gx -gy -us m -gs2 10 -h 40 /top/u_adc/sample[11:0]") != std::string::npos);
    assert(rc.find("addSubGroup \"AW\"") != std::string::npos);
    assert(rc.find("addSignal -UNSIGNED -HEX /top/u_axi/awaddr[31:0]") != std::string::npos);
    assert(rc.find("addExprSig -b 1 -n UUU aw_fire \"/top/u_axi/awvalid\" & \"/top/u_axi/awready\"") != std::string::npos);
    assert(rc.find("userMarker 120ns reset_done ID_YELLOW5 solid") != std::string::npos);

    auto refs = collect_rc_signal_refs(cfg);
    assert(refs.size() == 8);
    auto times = collect_rc_time_refs(cfg);
    assert(times.size() == 5);

    Json bad_expr = {
        {"groups", Json::array({
            {
                {"name", "Bad"},
                {"expr_signals", Json::array({
                    {{"name", "bad"}, {"expr", "$missing"}, {"signals", {{"valid", "top.valid"}}}}
                })}
            }
        })}
    };
    RcConfig bad_cfg;
    err.clear();
    assert(!parse_rc_config_json(bad_expr, bad_cfg, err));
    assert(err.find("unknown expr alias") != std::string::npos);

    return 0;
}
