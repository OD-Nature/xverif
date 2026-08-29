#pragma once

namespace xdebug_design {

// Server main function - called when --server flag is passed
// argv: [exe, --server, session_id, ...design_args...]
int server_main(int argc, char** argv);

// Stable public phase text for a classified engine startup exit code.
const char* engine_startup_failure_phase(int exit_code);

} // namespace xdebug_design
