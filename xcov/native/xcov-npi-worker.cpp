#include <algorithm>
#include <cerrno>
#include <cstring>
#include <filesystem>
#include <iostream>
#include <map>
#include <set>
#include <stdexcept>
#include <string>
#include <unistd.h>
#include <vector>

#include "json.hpp"
#include "npi.h"
#include "npi_cov.h"

using json = nlohmann::json;

namespace {

class WorkerError : public std::runtime_error {
 public:
  WorkerError(std::string code, std::string message)
      : std::runtime_error(std::move(message)), code_(std::move(code)) {}
  const std::string &code() const { return code_; }

 private:
  std::string code_;
};

void write_all(int fd, const std::string &text) {
  std::size_t offset = 0;
  while (offset < text.size()) {
    ssize_t count = ::write(fd, text.data() + offset, text.size() - offset);
    if (count < 0) {
      if (errno == EINTR) continue;
      throw std::runtime_error(std::string("protocol write failed: ") + std::strerror(errno));
    }
    offset += static_cast<std::size_t>(count);
  }
}

void send_json(int fd, const json &value) { write_all(fd, value.dump() + "\n"); }

std::string cov_str(npiCovProperty_e property, npiCovHandle handle) {
  const char *value = npi_cov_get_str(property, handle);
  return value ? std::string(value) : std::string();
}

std::string normalize_path(const std::string &value) {
  if (value.empty()) return value;
  try {
    return std::filesystem::weakly_canonical(std::filesystem::path(value)).string();
  } catch (const std::exception &) {
    return value;
  }
}

int cov_int(npiCovProperty_e property, npiCovHandle handle,
            npiCovHandle test = nullptr) {
  return npi_cov_get(property, handle, test);
}

const char *type_name(int type) {
  switch (type) {
    case npiCovDatabase: return "npiCovDatabase";
    case npiCovTest: return "npiCovTest";
    case npiCovInstance: return "npiCovInstance";
    case npiCovLineMetric: return "npiCovLineMetric";
    case npiCovToggleMetric: return "npiCovToggleMetric";
    case npiCovFsmMetric: return "npiCovFsmMetric";
    case npiCovConditionMetric: return "npiCovConditionMetric";
    case npiCovBranchMetric: return "npiCovBranchMetric";
    case npiCovAssertMetric: return "npiCovAssertMetric";
    case npiCovTestbenchMetric: return "npiCovTestbenchMetric";
    case npiCovBlock: return "npiCovBlock";
    case npiCovStmtBin: return "npiCovStmtBin";
    case npiCovSignal: return "npiCovSignal";
    case npiCovSignalBit: return "npiCovSignalBit";
    case npiCovToggleBin: return "npiCovToggleBin";
    case npiCovFsm: return "npiCovFsm";
    case npiCovStates: return "npiCovStates";
    case npiCovTransitions: return "npiCovTransitions";
    case npiCovSequences: return "npiCovSequences";
    case npiCovStateBin: return "npiCovStateBin";
    case npiCovTransBin: return "npiCovTransBin";
    case npiCovSeqBin: return "npiCovSeqBin";
    case npiCovCondition: return "npiCovCondition";
    case npiCovConditionBin: return "npiCovConditionBin";
    case npiCovConditionTerm: return "npiCovConditionTerm";
    case npiCovBranch: return "npiCovBranch";
    case npiCovBranchBin: return "npiCovBranchBin";
    case npiCovBranchTerm: return "npiCovBranchTerm";
    case npiCovAssert: return "npiCovAssert";
    case npiCovSuccessBin: return "npiCovSuccessBin";
    case npiCovAttemptBin: return "npiCovAttemptBin";
    case npiCovFailureBin: return "npiCovFailureBin";
    case npiCovVacuousBin: return "npiCovVacuousBin";
    case npiCovIncompleteBin: return "npiCovIncompleteBin";
    case npiCovCovergroup: return "npiCovCovergroup";
    case npiCovCoverpoint: return "npiCovCoverpoint";
    case npiCovCross: return "npiCovCross";
    case npiCovCoverBin: return "npiCovCoverBin";
    case npiCovCoverInstance: return "npiCovCoverInstance";
    case npiCovCoverProperty: return "npiCovCoverProperty";
    case npiCovCoverSequence: return "npiCovCoverSequence";
    case npiCovFirstmatchBin: return "npiCovFirstmatchBin";
    default: return "npiCovUnknown";
  }
}

npiCovObjType_e metric_type(const std::string &metric) {
  if (metric == "line") return npiCovLineMetric;
  if (metric == "toggle") return npiCovToggleMetric;
  if (metric == "fsm") return npiCovFsmMetric;
  if (metric == "condition") return npiCovConditionMetric;
  if (metric == "branch") return npiCovBranchMetric;
  if (metric == "assert") return npiCovAssertMetric;
  return npiCovInvalid;
}

bool starts_with_scope(const std::string &name, const std::string &scope) {
  if (scope.empty()) return true;
  if (name == scope) return true;
  return name.size() > scope.size() && name.compare(0, scope.size(), scope) == 0
      && name[scope.size()] == '.';
}

std::string parent_scope(const std::string &name) {
  std::size_t pos = name.rfind('.');
  return pos == std::string::npos ? std::string() : name.substr(0, pos);
}

std::string short_name(const std::string &name) {
  std::size_t pos = name.rfind('.');
  return pos == std::string::npos ? name : name.substr(pos + 1);
}

std::string canonical_full_name(int type, const std::string &name,
                                const std::string &raw_full_name,
                                const std::string &parent_full_name,
                                const std::string &scope) {
  if (type == npiCovSignal && !name.empty()) return scope + "." + name;
  if (type == npiCovSignalBit && !name.empty()) {
    std::string parent_short = short_name(parent_full_name);
    if (name.compare(0, parent_short.size(), parent_short) == 0) {
      std::string owner = parent_scope(parent_full_name);
      return owner.empty() ? name : owner + "." + name;
    }
    return parent_full_name + "." + name;
  }
  if (type == npiCovToggleBin || type == npiCovStmtBin
      || type == npiCovConditionBin || type == npiCovBranchBin
      || type == npiCovStateBin || type == npiCovTransBin
      || type == npiCovSeqBin || type == npiCovAttemptBin
      || type == npiCovSuccessBin || type == npiCovFailureBin
      || type == npiCovIncompleteBin || type == npiCovFirstmatchBin
      || type == npiCovCoverBin) {
    return parent_full_name.empty() ? name : parent_full_name + "." + name;
  }
  if (!raw_full_name.empty()) return raw_full_name;
  return parent_full_name.empty() ? name : parent_full_name + "." + name;
}

int scope_depth(const std::string &name) {
  return static_cast<int>(std::count(name.begin(), name.end(), '.'));
}

double coverage_pct(int covered, int coverable) {
  return coverable > 0 ? 100.0 * static_cast<double>(covered) / coverable : 0.0;
}

json status_flags(npiCovHandle object, npiCovHandle test, int covered, int coverable) {
  json flags = json::array();
  flags.push_back(coverable > 0 && covered >= coverable ? "covered" : "not_covered");
  const std::pair<npiCovStatus_e, const char *> statuses[] = {
      {npiCovStatusExcluded, "excluded"},
      {npiCovStatusPartiallyExcluded, "partially_excluded"},
      {npiCovStatusExcludedAtCompileTime, "excluded_at_compile_time"},
      {npiCovStatusExcludedAtReportTime, "excluded_at_report_time"},
      {npiCovStatusUnreachable, "unreachable"},
      {npiCovStatusIllegal, "illegal"},
      {npiCovStatusProven, "proven"},
      {npiCovStatusAttempted, "attempted"},
      {npiCovStatusPartiallyAttempted, "partially_attempted"},
  };
  for (const auto &entry : statuses) {
    if (npi_cov_has_status(entry.first, object, test) == 1) flags.push_back(entry.second);
  }
  return flags;
}

struct Source {
  bool valid = false;
  std::string type;
  std::string name;
  std::string full_name;
  std::string file;
  int line = -1;
};

struct WalkContext {
  json path = json::object();
  Source source;
  std::string parent_full_name;
};

Source own_source(npiCovHandle object, npiCovHandle test, int type,
                  const std::string &name, const std::string &full_name) {
  Source source;
  source.file = normalize_path(cov_str(npiCovFileName, object));
  source.line = cov_int(npiCovLineNo, object, test);
  source.valid = !source.file.empty() && source.line > 0;
  source.type = type_name(type);
  source.name = name;
  source.full_name = full_name;
  return source;
}

json source_json(const Source &source) {
  return {{"file", source.file}, {"line", source.line}};
}

std::string object_value(npiCovHandle object, npiCovHandle test) {
  std::string value = cov_str(npiCovValue, object);
  if (!value.empty()) return value;
  int int_value = cov_int(npiCovValue, object, test);
  return int_value == -1 ? std::string() : std::to_string(int_value);
}

std::string toggle_transition(npiCovHandle object, npiCovHandle test,
                              const std::string &fallback) {
  int transition = cov_int(npiCovToggleType, object, test);
  if (transition == npiCovToggle01) return "0 -> 1";
  if (transition == npiCovToggle10) return "1 -> 0";
  return fallback;
}

std::string collect_terms(npiCovHandle object, npiCovHandle test, int wanted_type) {
  std::vector<std::string> terms;
  npiCovHandle iter = npi_cov_iter_start(npiCovChild, object);
  if (!iter) return {};
  npiCovHandle child;
  while ((child = npi_cov_iter_next(iter))) {
    if (cov_int(npiCovType, child, test) == wanted_type) {
      std::string name = cov_str(npiCovName, child);
      std::string value = object_value(child, test);
      if (!name.empty() && !value.empty() && name != value) name += ":" + value;
      else if (name.empty()) name = value;
      if (!name.empty()) terms.push_back(name);
    }
    npi_cov_release_handle(child);
  }
  npi_cov_iter_stop(iter);
  std::string joined;
  for (std::size_t i = 0; i < terms.size(); ++i) {
    if (i) joined += ";";
    joined += terms[i];
  }
  return joined;
}

std::string functional_scope(const json &path) {
  if (!path.contains("covergroup")) return {};
  std::string name = path["covergroup"].get<std::string>();
  std::size_t package = name.find("::");
  if (package != std::string::npos) name = name.substr(0, package);
  std::size_t dot = name.rfind('.');
  return dot == std::string::npos ? std::string() : name.substr(0, dot);
}

class CoverageWorker {
 public:
  explicit CoverageWorker(std::string vdb) : vdb_(std::move(vdb)) {}
  ~CoverageWorker() { close(); }

  void open(const char *program) {
    int argc = 1;
    char *argv_storage[2] = {const_cast<char *>(program), nullptr};
    char **argv = argv_storage;
    std::cerr << "[xcov-native] initializing NPI" << std::endl;
    if (npi_init(argc, argv) != 1) throw WorkerError("NPI_INIT_FAILED", "npi_init failed");
    npi_initialized_ = true;
    std::cerr << "[xcov-native] opening VDB: " << vdb_ << std::endl;
    db_ = npi_cov_open(vdb_.c_str());
    if (!db_) throw WorkerError("VDB_OPEN_FAILED", "npi_cov_open failed: " + vdb_);
    std::cerr << "[xcov-native] enumerating and merging tests" << std::endl;
    npiCovHandle iter = npi_cov_iter_start(npiCovTest, db_);
    if (!iter) return;
    npiCovHandle test;
    while ((test = npi_cov_iter_next(iter))) {
      std::string name = cov_str(npiCovName, test);
      tests_.push_back({name, test});
      test_map_[name] = test;
      if (!merged_test_) merged_test_ = test;
      else {
        npiCovHandle merged = npi_cov_merge_test(merged_test_, test, nullptr);
        if (merged) merged_test_ = merged;
      }
    }
    npi_cov_iter_stop(iter);
    std::cerr << "[xcov-native] ready: " << tests_.size() << " tests" << std::endl;
  }

  void close() {
    if (closed_) return;
    closed_ = true;
    if (db_) {
      npi_cov_close(db_);
      db_ = nullptr;
    }
    if (npi_initialized_) {
      npi_end();
      npi_initialized_ = false;
    }
  }

  json tests() const {
    json rows = json::array();
    for (const auto &entry : tests_) rows.push_back({{"name", entry.first}});
    return rows;
  }

  json summary() {
    int top_count = 0;
    npiCovHandle iter = npi_cov_iter_start(npiCovInstance, db_);
    if (iter) {
      npiCovHandle instance;
      while ((instance = npi_cov_iter_next(iter))) {
        ++top_count;
        npi_cov_release_handle(instance);
      }
      npi_cov_iter_stop(iter);
    }
    return {{"test_count", tests_.size()}, {"top_scope_count", top_count}};
  }

  json scopes() {
    json rows = json::array();
    npiCovHandle iter = npi_cov_iter_start(npiCovInstance, db_);
    if (!iter) return rows;
    npiCovHandle instance;
    while ((instance = npi_cov_iter_next(iter))) {
      walk_scopes(instance, rows);
      npi_cov_release_handle(instance);
    }
    npi_cov_iter_stop(iter);
    return rows;
  }

  json items(const json &args) {
    std::set<std::string> metrics;
    if (args.contains("metrics") && args["metrics"].is_array()) {
      for (const auto &metric : args["metrics"]) metrics.insert(metric.get<std::string>());
    }
    if (metrics.empty()) {
      metrics = {"line", "toggle", "branch", "condition", "fsm", "assert", "functional"};
    }
    if (args.value("functional_only", false)) metrics = {"functional"};
    std::string scope = args.value("scope", "");
    npiCovHandle test = test_handle(args.value("test", "merged"));
    json rows = json::array();

    for (const std::string &metric : metrics) {
      if (metric == "functional") continue;
      npiCovObjType_e metric_object = metric_type(metric);
      if (metric_object == npiCovInvalid) continue;
      npiCovHandle iter = npi_cov_iter_start(npiCovInstance, db_);
      if (!iter) continue;
      npiCovHandle instance;
      while ((instance = npi_cov_iter_next(iter))) {
        walk_instance_items(instance, test, metric, metric_object, scope, rows);
        npi_cov_release_handle(instance);
      }
      npi_cov_iter_stop(iter);
    }
    if (metrics.count("functional")) walk_functional(test, scope, rows);
    return rows;
  }

 private:
  npiCovHandle test_handle(const std::string &name) const {
    if (name.empty() || name == "merged") return merged_test_;
    if (name == "each") {
      throw WorkerError("TEST_MODE_NOT_SUPPORTED", "test=each is not implemented");
    }
    auto found = test_map_.find(name);
    if (found == test_map_.end()) throw WorkerError("TEST_NOT_FOUND", "test not found: " + name);
    return found->second;
  }

  void walk_scopes(npiCovHandle instance, json &rows) {
    std::string name = cov_str(npiCovName, instance);
    std::string full_name = cov_str(npiCovFullName, instance);
    if (full_name.empty()) full_name = name;
    std::string file = normalize_path(cov_str(npiCovFileName, instance));
    int line = cov_int(npiCovLineNo, instance);
    json row = {
        {"name", name}, {"full_name", full_name},
        {"parent", parent_scope(full_name).empty() ? json(nullptr) : json(parent_scope(full_name))},
        {"depth", scope_depth(full_name)}, {"type", "npiCovInstance"},
        {"def_name", cov_str(npiCovDefName, instance)},
        {"evidence", {{"file", file}, {"line", line}}},
    };
    rows.push_back(row);
    npiCovHandle iter = npi_cov_iter_start(npiCovInstance, instance);
    if (!iter) return;
    npiCovHandle child;
    while ((child = npi_cov_iter_next(iter))) {
      walk_scopes(child, rows);
      npi_cov_release_handle(child);
    }
    npi_cov_iter_stop(iter);
  }

  void walk_instance_items(npiCovHandle instance, npiCovHandle test,
                           const std::string &metric, npiCovObjType_e metric_object,
                           const std::string &scope, json &rows) {
    std::string instance_name = cov_str(npiCovFullName, instance);
    if (instance_name.empty()) instance_name = cov_str(npiCovName, instance);
    if (starts_with_scope(instance_name, scope)) {
      npiCovHandle root = npi_cov_handle(metric_object, instance);
      if (root) {
        WalkContext context;
        context.parent_full_name = instance_name;
        npiCovHandle iter = npi_cov_iter_start(npiCovChild, root);
        if (iter) {
          npiCovHandle child;
          while ((child = npi_cov_iter_next(iter))) {
            walk_object(child, test, metric, instance_name, context, rows);
            npi_cov_release_handle(child);
          }
          npi_cov_iter_stop(iter);
        }
        npi_cov_release_handle(root);
      }
    }
    npiCovHandle iter = npi_cov_iter_start(npiCovInstance, instance);
    if (!iter) return;
    npiCovHandle child;
    while ((child = npi_cov_iter_next(iter))) {
      walk_instance_items(child, test, metric, metric_object, scope, rows);
      npi_cov_release_handle(child);
    }
    npi_cov_iter_stop(iter);
  }

  void walk_object(npiCovHandle object, npiCovHandle test,
                   const std::string &metric, const std::string &scope,
                   const WalkContext &parent, json &rows) {
    int type = cov_int(npiCovType, object, test);
    std::string name = cov_str(npiCovName, object);
    std::string full_name = canonical_full_name(
        type, name, cov_str(npiCovFullName, object), parent.parent_full_name, scope);
    Source own = own_source(object, test, type, name, full_name);
    Source source = own.valid ? own : parent.source;
    WalkContext context = parent;
    context.parent_full_name = full_name;
    if (own.valid) context.source = own;

    if (metric == "toggle") {
      if (type == npiCovSignal) {
        context.path["toggle_signal"] = full_name;
        int is_port = cov_int(npiCovIsPort, object, test);
        if (is_port != -1) context.path["toggle_is_port"] = is_port != 0;
      } else if (type == npiCovSignalBit) {
        context.path["toggle_bit"] = full_name;
        if (!context.path.contains("toggle_signal")) context.path["toggle_signal"] = full_name;
        int is_port = cov_int(npiCovIsPort, object, test);
        if (is_port != -1) context.path["toggle_is_port"] = is_port != 0;
      } else if (type == npiCovToggleBin) {
        context.path["toggle_transition"] = toggle_transition(object, test, name);
      }
    } else if (metric == "condition") {
      if (type == npiCovCondition) {
        context.path["condition"] = full_name;
        std::string terms = collect_terms(object, test, npiCovConditionTerm);
        if (!terms.empty()) context.path["condition_terms"] = terms;
      } else if (type == npiCovConditionBin) {
        std::string value = object_value(object, test);
        context.path["condition_bin"] = value.empty() ? name : value;
      }
    } else if (metric == "branch") {
      if (type == npiCovBranch) {
        context.path["branch"] = full_name;
        std::string terms = collect_terms(object, test, npiCovBranchTerm);
        if (!terms.empty()) context.path["branch_terms"] = terms;
      } else if (type == npiCovBranchBin) {
        std::string value = object_value(object, test);
        context.path["branch_bin"] = value.empty() ? name : value;
      }
    } else if (metric == "assert") {
      if (type == npiCovAssert || type == npiCovCoverProperty || type == npiCovCoverSequence) {
        const char *kind = type == npiCovAssert ? "assertion"
            : type == npiCovCoverProperty ? "cover_property" : "cover_sequence";
        context.path["assert_kind"] = kind;
        context.path["assert_object"] = full_name;
        int severity = cov_int(npiCovSeverity, object, test);
        int category = cov_int(npiCovCategory, object, test);
        if (severity != -1) context.path["severity"] = severity;
        if (category != -1) context.path["category"] = category;
      } else if (type == npiCovAttemptBin || type == npiCovSuccessBin
                 || type == npiCovFailureBin || type == npiCovIncompleteBin
                 || type == npiCovFirstmatchBin) {
        context.path["assert_bin"] = name;
      }
    }

    int covered = cov_int(npiCovCovered, object, test);
    int coverable = cov_int(npiCovCoverable, object, test);
    int count = cov_int(npiCovCount, object, test);
    json row = {
        {"metric", metric}, {"type", type_name(type)}, {"scope", scope},
        {"name", name}, {"full_name", full_name},
        {"covered", covered}, {"coverable", coverable},
        {"missing", coverable - covered}, {"count", count},
        {"coverage_pct", coverable > 0 ? json(coverage_pct(covered, coverable)) : json(nullptr)},
        {"status", status_flags(object, test, covered, coverable)},
        {"evidence", source.valid ? source_json(source) : json({{"file", ""}, {"line", -1}})},
    };
    for (auto it = context.path.begin(); it != context.path.end(); ++it) row[it.key()] = it.value();
    std::string value = object_value(object, test);
    if (!value.empty()) row["value"] = value;
    if (source.valid && !own.valid) {
      row["evidence_source"] = {
          {"inherited", true}, {"type", source.type}, {"name", source.name},
          {"full_name", source.full_name},
      };
    }
    rows.push_back(row);

    npiCovHandle iter = npi_cov_iter_start(npiCovChild, object);
    if (!iter) return;
    npiCovHandle child;
    while ((child = npi_cov_iter_next(iter))) {
      walk_object(child, test, metric, scope, context, rows);
      npi_cov_release_handle(child);
    }
    npi_cov_iter_stop(iter);
  }

  void walk_functional(npiCovHandle test, const std::string &scope_filter, json &rows) {
    npiCovHandle root = npi_cov_handle(npiCovTestbenchMetric, test);
    if (!root) return;
    WalkContext context;
    npiCovHandle iter = npi_cov_iter_start(npiCovChild, root);
    if (iter) {
      npiCovHandle child;
      while ((child = npi_cov_iter_next(iter))) {
        walk_functional_object(child, test, scope_filter, context, rows);
        npi_cov_release_handle(child);
      }
      npi_cov_iter_stop(iter);
    }
    npi_cov_release_handle(root);
  }

  void walk_functional_object(npiCovHandle object, npiCovHandle test,
                              const std::string &scope_filter,
                              const WalkContext &parent, json &rows) {
    int type = cov_int(npiCovType, object, test);
    std::string name = cov_str(npiCovName, object);
    std::string full_name = cov_str(npiCovFullName, object);
    if (full_name.empty()) {
      full_name = parent.parent_full_name;
      if (!full_name.empty() && !name.empty()) full_name += ".";
      full_name += name;
    }
    WalkContext context = parent;
    context.parent_full_name = full_name;
    if (type == npiCovCovergroup) context.path = {{"covergroup", name}};
    else if (type == npiCovCoverpoint) context.path["coverpoint"] = name;
    else if (type == npiCovCross) context.path["cross"] = name;
    else if (type == npiCovCoverBin) context.path["bin"] = name;

    Source own = own_source(object, test, type, name, full_name);
    Source source = own.valid ? own : parent.source;
    if (own.valid) context.source = own;
    std::string scope = functional_scope(context.path);
    if (starts_with_scope(scope.empty() ? full_name : scope, scope_filter)) {
      int covered = cov_int(npiCovCovered, object, test);
      int coverable = cov_int(npiCovCoverable, object, test);
      int count = cov_int(npiCovCount, object, test);
      json row = {
          {"metric", "functional"}, {"type", type_name(type)}, {"scope", scope},
          {"name", name}, {"full_name", full_name},
          {"covered", covered}, {"coverable", coverable},
          {"missing", coverable - covered}, {"count", count},
          {"coverage_pct", coverable > 0 ? json(coverage_pct(covered, coverable)) : json(nullptr)},
          {"status", status_flags(object, test, covered, coverable)},
          {"evidence", source.valid ? source_json(source) : json({{"file", ""}, {"line", -1}})},
      };
      for (auto it = context.path.begin(); it != context.path.end(); ++it) row[it.key()] = it.value();
      if (source.valid && !own.valid) {
        row["evidence_source"] = {
            {"inherited", true}, {"type", source.type}, {"name", source.name},
            {"full_name", source.full_name},
        };
      }
      rows.push_back(row);
    }
    npiCovHandle iter = npi_cov_iter_start(npiCovChild, object);
    if (!iter) return;
    npiCovHandle child;
    while ((child = npi_cov_iter_next(iter))) {
      walk_functional_object(child, test, scope_filter, context, rows);
      npi_cov_release_handle(child);
    }
    npi_cov_iter_stop(iter);
  }

  std::string vdb_;
  npiCovHandle db_ = nullptr;
  npiCovHandle merged_test_ = nullptr;
  std::vector<std::pair<std::string, npiCovHandle>> tests_;
  std::map<std::string, npiCovHandle> test_map_;
  bool npi_initialized_ = false;
  bool closed_ = false;
};

}  // namespace

int main(int argc, char **argv) {
  int protocol_fd = ::dup(STDOUT_FILENO);
  if (protocol_fd < 0) return 2;
  ::dup2(STDERR_FILENO, STDOUT_FILENO);
  if (argc != 2) {
    send_json(protocol_fd, {{"ok", false}, {"protocol", "xcov.native.v1"},
                            {"error", "usage: xcov-npi-worker <vdb>"}});
    return 2;
  }
  try {
    CoverageWorker worker(argv[1]);
    worker.open(argv[0]);
    send_json(protocol_fd, {{"ok", true}, {"protocol", "xcov.native.v1"},
                            {"version", 1}, {"pid", ::getpid()}});
    std::string line;
    while (std::getline(std::cin, line)) {
      if (line.empty()) continue;
      json request;
      json response;
      try {
        request = json::parse(line);
        response["id"] = request.value("id", 0);
        std::string action = request.value("action", "");
        json args = request.value("args", json::object());
        if (action == "tests") response["data"] = worker.tests();
        else if (action == "summary") response["data"] = worker.summary();
        else if (action == "scopes") response["data"] = worker.scopes();
        else if (action == "items") response["data"] = worker.items(args);
        else if (action == "close") response["data"] = {{"closed", true}};
        else throw WorkerError("UNKNOWN_ACTION", "unknown native action: " + action);
        response["ok"] = true;
        send_json(protocol_fd, response);
        if (action == "close") break;
      } catch (const WorkerError &error) {
        response["id"] = request.value("id", 0);
        response["ok"] = false;
        response["error"] = {{"code", error.code()}, {"message", error.what()}};
        send_json(protocol_fd, response);
      } catch (const std::exception &error) {
        response["id"] = request.value("id", 0);
        response["ok"] = false;
        response["error"] = {{"code", "NATIVE_QUERY_FAILED"}, {"message", error.what()}};
        send_json(protocol_fd, response);
      }
    }
    worker.close();
  } catch (const WorkerError &error) {
    send_json(protocol_fd, {{"ok", false}, {"protocol", "xcov.native.v1"},
                            {"error", error.what()}, {"code", error.code()}});
    return 3;
  } catch (const std::exception &error) {
    send_json(protocol_fd, {{"ok", false}, {"protocol", "xcov.native.v1"},
                            {"error", error.what()}});
    return 4;
  }
  ::close(protocol_fd);
  return 0;
}
