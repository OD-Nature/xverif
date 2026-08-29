#include "runtime/work_dir.h"

#include "common/env_config.h"
#include "common/path_utils.h"

#include <limits.h>
#include <sys/stat.h>
#include <unistd.h>

namespace xdebug {

namespace {

bool ensure_dir(const std::string& path) {
    if (mkdir(path.c_str(), 0700) == 0) return true;
    struct stat st;
    return stat(path.c_str(), &st) == 0 && S_ISDIR(st.st_mode);
}

} // namespace

std::string runtime_work_dir(const std::string& component) {
    std::string home = xdebug_core::env_raw_string("HOME");
    return (home.empty() ? xdebug_core::temporary_dir() : home) + "/.xdebug/work/" + component;
}

bool ensure_runtime_work_dir(const std::string& path) {
    const std::string work = path.substr(0, path.find_last_of('/'));
    const std::string root = work.substr(0, work.find_last_of('/'));
    return ensure_dir(root) && ensure_dir(work) && ensure_dir(path);
}

ScopedRuntimeWorkDir::ScopedRuntimeWorkDir(const std::string& component)
    : path_(runtime_work_dir(component)), changed_(false) {
    char cwd[PATH_MAX] = {};
    if (!getcwd(cwd, sizeof(cwd)) || !ensure_runtime_work_dir(path_)) return;
    previous_ = cwd;
    changed_ = chdir(path_.c_str()) == 0;
}

ScopedRuntimeWorkDir::~ScopedRuntimeWorkDir() {
    if (changed_) chdir(previous_.c_str());
}

bool ScopedRuntimeWorkDir::ok() const {
    return changed_;
}

const std::string& ScopedRuntimeWorkDir::path() const {
    return path_;
}

} // namespace xdebug
