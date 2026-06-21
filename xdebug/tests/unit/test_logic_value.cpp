#include "waveform/value/logic_value.h"

#include <cassert>

using namespace xdebug_waveform;

int main() {
    LogicValue fsdb_hex = logic_value_from_fsdb_raw("22", 'h');
    assert(fsdb_hex.valid);
    assert(fsdb_hex.known);
    assert(logic_value_compact_string(fsdb_hex) == "'h22");

    LogicValue fsdb_sized = logic_value_from_fsdb_raw("22", 'h', 8);
    assert(fsdb_sized.valid);
    assert(fsdb_sized.known);
    assert(fsdb_sized.width == 8);
    assert(logic_value_compact_string(fsdb_sized) == "8'h22");
    assert(logic_value_json(fsdb_sized)["bits"] == "00100010");

    LogicValue unknown = logic_value_from_fsdb_raw("xz", 'h', 8);
    assert(unknown.valid);
    assert(!unknown.known);
    assert(unknown.has_x);
    assert(unknown.has_z);
    assert(logic_value_compact_string(unknown) == "8'hxz");

    LogicValue user_sv = parse_user_logic_literal("8'h22");
    assert(user_sv.valid);
    assert(user_sv.known);
    assert(logic_value_compact_string(user_sv) == "8'h22");
    assert(logic_value_compare_key(user_sv) == "22");

    LogicValue user_bin = parse_user_logic_literal("'b1010");
    assert(user_bin.valid);
    assert(user_bin.width == 4);
    assert(logic_value_compact_string(user_bin) == "4'ha");

    LogicValue user_dec = parse_user_logic_literal("34");
    assert(user_dec.valid);
    assert(logic_value_compact_string(user_dec) == "'h22");

    LogicValue legacy = parse_user_logic_literal("0x22");
    assert(!legacy.valid);
    assert(legacy.error.find("0x prefix is not accepted") != std::string::npos);

    return 0;
}
