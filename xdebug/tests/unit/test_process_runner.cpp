#include "core/process/process_runner.h"

#include <cassert>
#include <chrono>
#include <string>

int main() {
    xdebug::ProcessRunner runner;

    {
        xdebug::ProcessRequest request;
        request.executable = "sh";
        request.argv = {"-c", "cat; printf 'stderr-ok\\n' >&2"};
        request.stdin_text = "stdin-ok\n";
        request.timeout_ms = 2000;
        xdebug::ProcessResult result = runner.run(request);
        assert(result.exit_code == 0);
        assert(!result.timed_out);
        assert(result.stdout_text == "stdin-ok\n");
        assert(result.stderr_text == "stderr-ok\n");
    }

    {
        xdebug::ProcessRequest request;
        request.executable = "sh";
        request.argv = {
            "-c",
            "i=0; while [ $i -lt 12000 ]; do printf 'stdout-%05d\\n' $i; "
            "printf 'stderr-%05d\\n' $i >&2; i=$((i+1)); done"
        };
        request.timeout_ms = 5000;
        xdebug::ProcessResult result = runner.run(request);
        assert(result.exit_code == 0);
        assert(result.stdout_text.find("stdout-11999") != std::string::npos);
        assert(result.stderr_text.find("stderr-11999") != std::string::npos);
    }

    {
        xdebug::ProcessRequest request;
        request.executable = "sh";
        request.argv = {"-c", "sleep 5"};
        request.timeout_ms = 100;
        const auto begin = std::chrono::steady_clock::now();
        xdebug::ProcessResult result = runner.run(request);
        const long long elapsed_ms = std::chrono::duration_cast<std::chrono::milliseconds>(
            std::chrono::steady_clock::now() - begin).count();
        assert(result.timed_out);
        assert(result.exit_code == -1);
        assert(elapsed_ms < 2000);
    }

    {
        xdebug::ProcessRequest request;
        request.executable = "definitely-missing-xdebug-executable";
        request.timeout_ms = 1000;
        xdebug::ProcessResult result = runner.run(request);
        assert(result.exit_code == 127);
        assert(result.stderr_text.find("failed to exec") != std::string::npos);
    }

    return 0;
}
