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
        {"signal_spacing", 5},
        {"cursor", "120ns"},
        {"main_marker", "120ns"},
        {"zoom", {{"begin", "0ns"}, {"end", "500ns"}}},
        {"groups", Json::array({
            {
                {"name", "ClockReset"},
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
            {{"name", "test"}, {"time", "10347.651ns"}, {"color", "ID_CYAN5"}, {"linestyle", "long_dashed"}}
        })}
    };

    RcConfig cfg;
    err.clear();
    assert(parse_rc_config_json(doc, cfg, err));
    assert(validate_rc_time_refs(cfg, nullptr, err));
    assert(normalize_rc_user_marker_times(cfg, nullptr, err));
    Json counts = rc_config_counts(cfg);
    assert(counts["group_count"] == 4);
    assert(counts["signal_count"] == 6);
    assert(counts["expr_signal_count"] == 1);
    assert(counts["marker_count"] == 1);

    std::string rc = render_signal_rc(cfg);
    assert(rc.find("openDirFile") == std::string::npos);
    assert(rc.find("activeDirFile") == std::string::npos);
    const size_t first_statement = rc.find("windowTimeUnit 1ns");
    assert(first_statement != std::string::npos);
    assert(rc.find("fileTimeScale") > first_statement);
    assert(rc.find("addGroup \"ClockReset\"") != std::string::npos);
    assert(rc.find("addGroup -e ") == std::string::npos);
    assert(rc.find("addSubGroup -e ") == std::string::npos);
    assert(rc.find("addSignal -h 15 -BIN /top/rst_n") != std::string::npos);
    assert(rc.find("addSignal -w analog -ds pwl -gx -gy -us m -gs2 10 -h 40 /top/u_adc/sample[11:0]") != std::string::npos);
    assert(rc.find("addSubGroup \"AW\"") != std::string::npos);
    assert(rc.find("addSignal -UNSIGNED -HEX /top/u_axi/awaddr[31:0]") != std::string::npos);
    const size_t expr = rc.find("addExprSig -b 1 -n UUU aw_fire \"/top/u_axi/awvalid\" & \"/top/u_axi/awready\"");
    const size_t axi_group = rc.find("addGroup \"AXI\"");
    const size_t aw_group = rc.find("addSubGroup \"AW\"");
    const size_t expr_signal = rc.find("addSignal -h 18 /aw_fire");
    assert(expr != std::string::npos);
    assert(axi_group != std::string::npos);
    assert(aw_group != std::string::npos);
    assert(expr_signal != std::string::npos);
    assert(expr < axi_group);
    assert(aw_group < expr_signal);
    assert(rc.find("addExprSig", axi_group) == std::string::npos);
    assert(rc.find("endSubGroup \"AW\"", expr_signal) != std::string::npos);
    assert(rc.find("userMarker 10347.651 test ID_CYAN5 long_dashed") != std::string::npos);

    auto refs = collect_rc_signal_refs(cfg);
    assert(refs.size() == 8);
    auto times = collect_rc_time_refs(cfg);
    assert(times.size() == 5);

    Json removed_expanded = {
        {"groups", Json::array({
            {{"name", "Removed"}, {"expanded", true}}
        })}
    };
    RcConfig removed_expanded_cfg;
    err.clear();
    assert(!parse_rc_config_json(removed_expanded, removed_expanded_cfg, err));
    assert(err.find("group.expanded is not supported") != std::string::npos);

    Json nested_removed_expanded = {
        {"groups", Json::array({
            {
                {"name", "Parent"},
                {"subgroups", Json::array({
                    {{"name", "RemovedSubgroup"}, {"expanded", false}}
                })}
            }
        })}
    };
    RcConfig nested_removed_expanded_cfg;
    err.clear();
    assert(!parse_rc_config_json(
        nested_removed_expanded, nested_removed_expanded_cfg, err));
    assert(err.find("group.expanded is not supported") != std::string::npos);

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

    Json deprecated_window_unit = {
        {"window_time_unit", "1ns"},
        {"groups", Json::array({{{"name", "G"}}})}
    };
    err.clear();
    assert(!parse_rc_config_json(deprecated_window_unit, bad_cfg, err));
    assert(err.find("window_time_unit is not supported") != std::string::npos);

    Json unitless_marker = {
        {"groups", Json::array({{{"name", "G"}}})},
        {"user_markers", Json::array({{{"name", "bad"}, {"time", "42"}}})}
    };
    err.clear();
    assert(parse_rc_config_json(unitless_marker, bad_cfg, err));
    assert(!normalize_rc_user_marker_times(bad_cfg, nullptr, err));
    assert(err.find("explicit unit") != std::string::npos);

    err.clear();
    assert(rc_fsdb_path_to_slash("top.u.packet.field", "top.u", err) ==
           "/top/u/packet.field");
    assert(rc_fsdb_path_to_slash("top.u.packet.field", "top.u.packet", err) ==
           "/top/u/packet/field");
    assert(rc_fsdb_path_to_slash("top.g[2].packets[1].header.opcode[3:0]",
                                 "top.g[2]", err) ==
           "/top/g[2]/packets[1].header.opcode[3:0]");
    assert(rc_fsdb_path_to_slash("packet.field", "", err) == "/packet.field");
    assert(err.empty());
    assert(rc_fsdb_path_to_slash("top.u2.packet.field", "top.u", err).empty());
    assert(!err.empty());

    RcConfig member_cfg;
    err.clear();
    assert(parse_rc_config_json(Json::parse(R"({"groups":[{
        "name":"Outer","subgroups":[{
            "name":"Members","signals":["top.u.packet.field"],
            "expr_signals":[{"name":"member_expr","bit_size":8,
                "expr":"$field","signals":{"field":"top.u.packet.field"}}]
        }]
    }]})"), member_cfg, err));
    assert(bind_rc_signal_paths(member_cfg,
        {{"top.u.packet.field", "/top/u/packet.field"}}, err));
    const std::string member_rc = render_signal_rc(member_cfg);
    assert(member_rc.find("addSignal /top/u/packet.field\n") != std::string::npos);
    assert(member_rc.find("addExprSig -b 8 member_expr \"/top/u/packet.field\"") != std::string::npos);
    const auto member_refs = collect_rc_signal_refs(member_cfg);
    assert(member_refs.size() == 2);
    assert(member_refs[0].rc_path == "/top/u/packet.field");
    assert(member_refs[1].rc_path == "/top/u/packet.field");
    assert(!bind_rc_signal_paths(member_cfg, {}, err));
    assert(err.find("unresolved rc signal path") != std::string::npos);

    RcConfig nested_groups;
    err.clear();
    assert(parse_rc_config_json(Json::parse(R"({"groups":[{
        "name":"Top","subgroups":[
            {"name":"First","subgroups":[{"name":"Inner","signals":["top.a"]}]},
            {"name":"Second","signals":["top.b"]}
        ]
    }]})"), nested_groups, err));
    const std::string grouped_rc = render_signal_rc(nested_groups);
    assert(grouped_rc.find(
        "addSubGroup \"First\"\naddSubGroup \"Inner\"\naddSignal /top/a\n"
        "endSubGroup \"Inner\"\nendSubGroup \"First\"\n"
        "addSubGroup \"Second\"\naddSignal /top/b\nendSubGroup \"Second\"\n") != std::string::npos);

    return 0;
}
