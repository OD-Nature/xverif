#pragma once

#include "../session/session_manager.h"
#include "json.hpp"

#include <istream>
#include <string>
#include <vector>

namespace xdebug_design {

using json = nlohmann::json;

extern const char* const API_VERSION;
extern const char* const TOOL_VERSION;

std::string read_stream(std::istream& in);
std::string read_file(const std::string& path);
std::string trim(const std::string& s);
bool starts_with(const std::string& s, const std::string& prefix);
std::string leaf_name(const std::string& signal);
std::string lower_copy(const std::string& s);
bool contains_word_like(const std::string& text, const std::string& token);
std::string next_token_after(const std::string& text, const std::string& key);

json session_to_json(const SessionInfo& s);
SessionTransportOptions request_transport_options(const json& request);
json base_response(const json& request, const std::string& action);
std::string response_verbosity(const json& request);
bool compact_mode(const json& request);
bool include_arg(const json& request, const std::string& key);
int max_examples_arg(const json& request, int def);
json error_response(const json& request,
                    const std::string& action,
                    const std::string& code,
                    const std::string& message,
                    bool recoverable = true,
                    const json& candidates = json::array(),
                    const json& suggested_actions = json::array());
std::vector<std::string> target_dbdir_args(const json& request);
std::string json_session_id(const json& value);
std::string request_session_name(const json& request);
std::string ensure_error_code(const SessionEnsureResult& result);
bool ensure_target_session(const json& request,
                           json& response,
                           std::string& session_id,
                           SessionInfo& session,
                           bool allow_latest = false);
std::string option_string_from_limits_args(const json& request);
bool send_json_command(const std::string& session_id,
                       const std::string& action,
                       const json& args,
                       json& parsed,
                       std::string& error_status,
                       std::string& error_message,
                       json& engine_error);

json parse_expr_ast(const std::string& expr);
std::string expr_op(const json& expr);
bool expr_mentions_signal(const json& expr, const std::string& signal);
json signal_array_from_ast(const json& expr);
json enrich_trace_payload(const json& request, const json& trace);
json make_trace_summary(const json& trace);

json run_trace_action(const json& request, const std::string& mode);
json run_signal_resolve_action(const json& request);
json canonicalize_signal(const json& request);
json trace_expand_like(const json& request, bool explain_only = false);
json trace_path(const json& request);
json source_context(const json& request);
json control_explain(const json& request);
json run_expr_normalize_action(const json& request);
json run_procedural_assignment_action(const json& request);
json run_sequential_update_action(const json& request);
json run_fsm_explain_action(const json& request);
json run_counter_explain_action(const json& request);
json run_port_like_action(const json& request, const std::string& action);

json schema_payload();
json actions_payload();
json handle_request(const json& request);

} // namespace xdebug_design
