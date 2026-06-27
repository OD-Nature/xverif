#include "api/text_response_builder.h"
#include "api/xout_renderer.h"

#include <cassert>
#include <string>

using namespace xdebug;

int main() {
    TextResponseBuilder out("xdebug");
    out.emit_header("trace.driver");
    out.emit_section("summary");
    out.emit_kv("signal", "top.u.valid");
    out.emit_kv("known", true);
    out.emit_kv("count", 2);
    out.emit_kv("empty", Json::array());
    out.emit_section("rows");
    out.emit_row({"n0", "top.u.valid", "reg with spaces"});
    out.emit_warning("W", "line1\nline2");
    std::string text = out.str();
    assert(text.find("@xdebug.trace.driver.v1") == 0);
    assert(text.find("summary:\n  signal: top.u.valid\n  known: true\n  count: 2") != std::string::npos);
    assert(text.find("rows:\n  n0 top.u.valid reg with spaces") != std::string::npos);
    assert(text.find("W line1\\nline2") != std::string::npos);
    assert(text.find("empty") == std::string::npos);

    Json response = {
        {"api_version", "xdebug.v1"},
        {"ok", true},
        {"action", "value.at"},
        {"data", {
            {"signal", "top.clk"},
            {"time", "10ns"},
            {"value", Json{{"value", "1"}, {"known", true}}},
            {"known", true}
        }}
    };
    text = render_xout_response(response);
    assert(text.find("@xdebug.value.at.v1") == 0);
    assert(text.find("data:\n  signal: top.clk\n  time: 10ns") != std::string::npos);
    assert(text.find("value: 'h1") != std::string::npos);

    Json sized_value = {
        {"value", "0x4000000c"},
        {"bits", "01000000000000000000000000001100"},
        {"known", true},
        {"width", 32}
    };
    assert(json_to_xout_value(sized_value) == "32'h4000000c");

    Json unsized_hex = {{"value", "'h22"}, {"known", true}};
    assert(json_to_xout_value(unsized_hex) == "'h22");

    Json binary_value = {{"value", "'b1010"}, {"known", true}};
    assert(json_to_xout_value(binary_value) == "4'ha");

    Json unknown_value = {
        {"value", "0xx"},
        {"bits", "10xz"},
        {"known", false},
        {"width", 4}
    };
    assert(json_to_xout_value(unknown_value) == "4'hx known=false bits=10xz width=4");

    Json field_map = {
        {"data", sized_value},
        {"seq", Json{{"value", "0x000c"}, {"bits", "0000000000001100"}, {"known", true}, {"width", 16}}}
    };
    assert(json_to_xout_value(field_map) == "data=32'h4000000c seq=16'h000c");

    Json table_response = {
        {"api_version", "xdebug.v1"},
        {"ok", true},
        {"action", "stream.query"},
        {"data", {
            {"rows", Json::array({
                Json{{"cycle", 18}, {"time", "185ns"}, {"fields", field_map}}
            })}
        }}
    };
    text = render_xout_response(table_response);
    assert(text.find("cycle time fields\n  18 185ns data=32'h4000000c seq=16'h000c") != std::string::npos);
    assert(text.find("bits:") == std::string::npos);
    assert(text.find("known: true") == std::string::npos);

    Json handler_text = {
        {"ok", true},
        {"action", "any.action"},
        {"text", "@xdebug.any.action.v1\nsummary:\n  ok: true\n"}
    };
    text = render_xout_response(handler_text);
    assert(text == "@xdebug.any.action.v1\nsummary:\n  ok: true\n");

    Json error = {
        {"ok", false},
        {"action", "trace.driver"},
        {"error", {
            {"code", "SIGNAL_NOT_FOUND"},
            {"message", "missing\nsignal"},
            {"recoverable", true}
        }}
    };
    text = render_xout_response(error);
    assert(text.find("@xdebug.error.v1") == 0);
    assert(text.find("action: trace.driver") != std::string::npos);
    assert(text.find("code: SIGNAL_NOT_FOUND") != std::string::npos);
    assert(text.find("message: missing\\nsignal") != std::string::npos);
    return 0;
}
