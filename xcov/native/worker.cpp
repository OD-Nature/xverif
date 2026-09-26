// Process-owned NPI coverage handles. The wire carries opaque IDs, never pointers.
#include <cstddef>
#include <npi.h>
#include <npi_cov.h>
#include <nlohmann/json.hpp>
#include <cstdio>
#include <cstdlib>
#include <map>
#include <set>
#include <stdexcept>
#include <string>
#include <unistd.h>
using json = nlohmann::json;

class CoverageWorker {
    std::map<unsigned long, npiCovHandle> handles;

    unsigned long next = 1;
    npiCovHandle database = nullptr;
    bool initialized = false;
    std::string executable;
    std::set<std::string> text_arguments;
    const char* text_argument(const json& args, size_t index) {
        return text_arguments.insert(args.at(index).get<std::string>()).first->c_str();
    }
    char* init_values[2] = {nullptr, nullptr};
    char** init_argv = init_values;
    int init_argc = 1;
    json remember(npiCovHandle h) {
        if (!h) return nullptr;
        const auto id = next++;
        handles.emplace(id, h);
        npi_cov_set_permanent_handle(h);
        return json{{"handle", id}};
    }
    npiCovHandle lookup(const json& value) {
        if (value.is_null()) return nullptr;
        return handles.at(value.at("handle").get<unsigned long>());
    }
    json collect(npiCovHandle iterator) {
        json result = json::array();
        if (iterator) {
            while (auto h = npi_cov_iter_next(iterator)) result.push_back(remember(h));
            npi_cov_iter_stop(iterator);
        }
        return result;
    }
public:
    explicit CoverageWorker(const char* path) : executable(path) { init_values[0] = executable.data(); }
    // V-2023.12-SP2 libucapi has a background PdrDomainNameReader that can
    // outlive npi_cov_close and access freed database memory. This process
    // owns one DB: closing it terminates the process after the RPC response.
    // EL persistence is always an explicit save operation, never a destructor.
    json call(const json& request) {
        const auto method = request.at("method").get<std::string>();
        const auto args = request.at("args");
        if (method == "init") {
            if (initialized) throw std::runtime_error("worker is already initialized");
            const int result = npi_init(init_argc, init_argv);
            initialized = result == 1;
            return result;
        }
        if (method == "end") return 1;
        if (!initialized) throw std::runtime_error("worker is not initialized");
        if (method == "open") {
            if (database) throw std::runtime_error("worker already owns a database");
            const auto policy = args.at(1).get<std::string>();
            if (policy != "default" && policy != "strict") throw std::runtime_error("invalid exclusion policy");
            database = npi_cov_open(text_argument(args, 0),
                policy == "strict" ? npiCovExclusionInStrictMode : 0);
            return remember(database);
        }
        if (!database) throw std::runtime_error("worker has no open database");
        if (method == "merge_test") return remember(npi_cov_merge_test(lookup(args.at(0)), lookup(args.at(1))));
        if (method == "release_handle") {
            auto h = lookup(args.at(0));
            if (h == database) throw std::runtime_error("database must be closed, not released");
            // Native objects are session-owned. Dropping a wire reference does
            // not invalidate aliases or asynchronous vendor readers. The worker
            // process reclaims its arena at explicit close.
            handles.erase(args.at(0).at("handle").get<unsigned long>());
            return 1;
        }
        auto h = lookup(request.at("object"));
        if (method == "close") {
            if (h != database) throw std::runtime_error("close requires database");
            return 1;
        }
        if (method == "handle_by_name") return remember(npi_cov_handle_by_name(text_argument(args, 0), h));
        if (method == "load_exclude_file") return npi_cov_load_exclude_file(h, text_argument(args, 0));
        if (method == "save_exclude_file") return npi_cov_save_exclude_file(h, text_argument(args, 0), text_argument(args, 1));
        if (method == "unload_exclusion") return npi_cov_unload_exclusion(h);
        static const std::map<std::string, npiCovObjType_e> singles = {
            {"line_metric_handle", npiCovLineMetric}, {"toggle_metric_handle", npiCovToggleMetric},
            {"branch_metric_handle", npiCovBranchMetric}, {"condition_metric_handle", npiCovConditionMetric},
            {"fsm_metric_handle", npiCovFsmMetric}, {"assert_metric_handle", npiCovAssertMetric},
            {"testbench_metric_handle", npiCovTestbenchMetric}, {"power_metric_handle", npiCovPowerMetric}};
        if (singles.count(method)) return remember(npi_cov_handle(singles.at(method), h));
        static const std::map<std::string, npiCovObjType_e> lists = {
            {"test_handles", npiCovTest}, {"instance_handles", npiCovInstance},
            {"condition_term_handles", npiCovConditionTerm}, {"branch_term_handles", npiCovBranchTerm}};
        if (lists.count(method)) return collect(npi_cov_iter_start(lists.at(method), h));
        if (method == "child_handles") return collect(npi_cov_iter_start(npiCovChild, h));
        static const std::map<std::string, npiCovProperty_e> strings = {
            {"type", npiCovType}, {"name", npiCovName}, {"full_name", npiCovFullName},
            {"def_name", npiCovDefName}, {"file_name", npiCovFileName},
            {"value", npiCovValue}, {"toggle_type", npiCovToggleType}};
        if (strings.count(method)) {
            const char* value = npi_cov_get_str(strings.at(method), h);
            return value ? json(value) : json(nullptr);
        }
        auto test = args.empty() ? nullptr : lookup(args.at(0));
        static const std::map<std::string, npiCovProperty_e> integers = {
            {"line_no", npiCovLineNo}, {"covered", npiCovCovered}, {"coverable", npiCovCoverable},
            {"count", npiCovCount}, {"is_port", npiCovIsPort}, {"severity", npiCovSeverity}, {"category", npiCovCategory}};
        if (integers.count(method)) return npi_cov_get(integers.at(method), h, test);
        static const std::map<std::string, npiCovStatus_e> statuses = {
            {"has_status_excluded", npiCovStatusExcluded}, {"has_status_partially_excluded", npiCovStatusPartiallyExcluded},
            {"has_status_excluded_at_compile_time", npiCovStatusExcludedAtCompileTime},
            {"has_status_excluded_at_report_time", npiCovStatusExcludedAtReportTime},
            {"has_status_unreachable", npiCovStatusUnreachable}, {"has_status_illegal", npiCovStatusIllegal},
            {"has_status_proven", npiCovStatusProven}, {"has_status_attempted", npiCovStatusAttempted},
            {"has_status_partially_attempted", npiCovStatusPartiallyAttempted}};
        if (statuses.count(method)) return npi_cov_has_status(statuses.at(method), h, test);
        if (method == "set_status_excluded_at_report_time") return npi_cov_set_status(npiCovStatusExcludedAtReportTime, h, test, args.at(1).get<int>());
        throw std::runtime_error("unsupported native operation: " + method);
    }
};

int main(int argc, char** argv) {
    if (argc != 2) return 2;
    const int fd = std::stoi(argv[1]);
    FILE* input = fdopen(dup(fd), "r");
    FILE* output = fdopen(fd, "w");
    if (!input || !output) return 2;
    CoverageWorker worker(argv[0]);
    char* line = nullptr; size_t size = 0;
    while (getline(&line, &size, input) >= 0) {
        json reply;
        bool ending = false;
        try {
            const auto request = json::parse(line);
            ending = request.at("method") == "end" || request.at("method") == "close";
            reply = {{"ok", true}, {"result", worker.call(request)}};
        }
        catch (const std::exception& e) { reply = {{"ok", false}, {"error", e.what()}}; }
        const auto encoded = reply.dump() + "\n";
        if (fwrite(encoded.data(), 1, encoded.size(), output) != encoded.size() || fflush(output)) break;
        if (ending && reply.at("ok") == true) {
            // Do not run vendor global destructors or race its background reader.
            // All OS resources (including license sockets) belong to this worker.
            std::_Exit(0);
        }
    }
    free(line); fclose(input); fclose(output);
    std::_Exit(0);
}
