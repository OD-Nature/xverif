#include "../action_handler.h"
#include "../action_support.h"
#include "../../value/logic_value.h"

namespace xdebug_waveform {

namespace {

class VerifyConditionsAction : public WaveformActionHandler {
public:
    const char* action_name() const override { return "verify.conditions"; }

    int run(const WaveformActionContext& ctx) const override {
        std::string time;
        if ((!get_string(ctx.args, "at", time) && !get_string(ctx.args, "time", time)) ||
            !ctx.args.contains("conditions") || !ctx.args["conditions"].is_array()) {
            return print_error_and_return(ctx.req, ctx.action, "MISSING_FIELD",
                "verify.conditions requires args.time/args.at and args.conditions[]", ctx.elapsed_ms);
        }

        Json checks = Json::array();
        int passed = 0, failed = 0, unknown = 0;
        std::string err;

        for (const auto& cond : ctx.args["conditions"]) {
            std::string signal, op, expected;
            get_string(cond, "signal", signal);
            get_string(cond, "op", op);
            get_string(cond, "value", expected);
            if (op.empty()) op = "==";

            LogicValue expected_value = parse_user_logic_literal(expected);
            if (!expected_value.valid) {
                return print_error_and_return(ctx.req, ctx.action, "VALUE_FORMAT_INVALID",
                    expected_value.error, ctx.elapsed_ms);
            }

            Json item = {{"signal", signal}, {"time", time}, {"op", op}, {"expected", expected}};
            std::string raw;

            if (!query_value(ctx.sid, signal, time, 'H', raw, err)) {
                item["status"] = "unknown";
                item["known"] = false;
                item["pass"] = nullptr;
                item["error"] = err;
                unknown++;
            } else {
                LogicValue observed = logic_value_from_fsdb_raw(raw, 'h');
                item["observed"] = logic_value_json(observed);
                if (logic_value_has_xz(observed) || logic_value_has_xz(expected_value)) {
                    item["status"] = "unknown";
                    item["known"] = false;
                    item["pass"] = nullptr;
                    unknown++;
                } else {
                    bool eq = logic_value_compare_key(observed) == logic_value_compare_key(expected_value);
                    bool pass = (op == "!=") ? !eq : eq;
                    item["observed"] = logic_value_json(observed);
                    item["status"] = pass ? "pass" : "fail";
                    item["known"] = true;
                    item["pass"] = pass;
                    if (pass) passed++; else failed++;
                }
            }
            checks.push_back(item);
        }

        Json out = base_response(ctx.req, ctx.action, true, ctx.elapsed_ms);
        fill_session(out, ctx.info);
        out["summary"] = {{"verdict", failed == 0 && unknown == 0 ? "pass" : "fail"},
                          {"condition_count", checks.size()},
                          {"all_passed", failed == 0 && unknown == 0},
                          {"passed", passed}, {"failed", failed}, {"unknown", unknown}};

        if (!compact_mode(ctx.req) || failed > 0 || unknown > 0) {
            Json filtered = Json::array();
            for (const auto& check : checks) {
                std::string status = check.value("status", std::string());
                if (!compact_mode(ctx.req) || status != "pass") filtered.push_back(check);
            }
            out["data"]["checks"] = filtered;
        }
        if (!compact_mode(ctx.req)) {
            Json resolved = resolve_time_spec_json(ctx.sid, time, false, err);
            if (!resolved.is_null()) out["data"]["resolved_time"] = resolved;
        }

        print_json(finalize_response(ctx.req, out));
        return 0;
    }
};

} // namespace

std::unique_ptr<WaveformActionHandler> make_verify_conditions_action() {
    return std::unique_ptr<WaveformActionHandler>(new VerifyConditionsAction());
}

} // namespace xdebug_waveform
