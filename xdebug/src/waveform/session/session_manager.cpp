#include "session_manager.h"
#include "session_transport.h"
#include "../common/xdebug_waveform_paths.h"
#include "../protocol/protocol.h"
#include "logging/action_log.h"
#include "session/session_types.h"
#include "transport/file_exchange.h"

#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <unistd.h>
#include <sys/wait.h>
#include <sys/time.h>
#include <sys/stat.h>
#include <signal.h>
#include <fcntl.h>
#include <sys/file.h>
#include <set>
#include <limits.h>
#include <cerrno>
#include <cstdarg>
#include <strings.h>

namespace xdebug_waveform {

namespace {

int open_registry_lock() {
    char lock_path[SOCK_PATH_LEN];
    xdebug_waveform_ensure_home();
    get_registry_lock_path(lock_path);
    return open(lock_path, O_RDWR | O_CREAT, 0600);
}

bool env_debug_enabled() {
    const char* env = getenv("XDEBUG_WAVEFORM_DEBUG");
    return env && env[0] != '\0' && strcmp(env, "0") != 0 &&
           strcasecmp(env, "false") != 0 && strcasecmp(env, "off") != 0;
}

int session_start_timeout_sec() {
    const char* env = getenv("XDEBUG_WAVEFORM_SESSION_START_TIMEOUT_SEC");
    if (!env || env[0] == '\0') return 180;
    int value = atoi(env);
    return value > 0 ? value : 180;
}

std::string default_transport_from_env() {
    const char* env = getenv("XDEBUG_TRANSPORT");
    if (env && *env) return std::string(env);
    return "uds";
}

bool valid_transport(const std::string& transport) {
    return transport == "uds" || transport == "tcp" || transport == "file";
}

}  // namespace

const char* session_health_status_name(SessionHealthStatus status) {
    switch (status) {
        case SessionHealthStatus::Healthy:
            return "healthy";
        case SessionHealthStatus::RegistryMissing:
            return "registry_missing";
        case SessionHealthStatus::ProcessExited:
            return "process_exited";
        case SessionHealthStatus::SocketMissing:
            return "socket_missing";
        case SessionHealthStatus::ConnectFailed:
            return "connect_failed";
        case SessionHealthStatus::PingFailed:
            return "ping_failed";
        case SessionHealthStatus::FsdbChanged:
            return "fsdb_changed";
        case SessionHealthStatus::FsdbMissing:
            return "fsdb_missing";
    }
    return "unknown";
}

SessionManager::SessionManager() : registry_(new SessionRegistry()) {
    debug_.enabled = env_debug_enabled();
}

SessionManager::~SessionManager() {
}

void SessionManager::set_debug_enabled(bool enabled) {
    debug_.enabled = enabled;
}

bool SessionManager::debug_enabled() const {
    return debug_.enabled;
}

void SessionManager::debug_log(const char* fmt, ...) const {
    if (!debug_.enabled) return;
    fprintf(stderr, "[xdebug_waveform-debug] ");
    va_list ap;
    va_start(ap, fmt);
    vfprintf(stderr, fmt, ap);
    va_end(ap);
    fprintf(stderr, "\n");
    fflush(stderr);
}

std::string SessionManager::canonicalize_fsdb_path(const std::string& fsdb_file) {
    char resolved[PATH_MAX];
    if (realpath(fsdb_file.c_str(), resolved)) {
        return std::string(resolved);
    }
    return fsdb_file;
}

bool SessionManager::populate_fsdb_metadata(const std::string& fsdb_file, SessionInfo& session) {
    struct stat st;
    if (stat(fsdb_file.c_str(), &st) != 0) return false;
    session.fsdb_file = fsdb_file;
    session.fsdb_mtime = static_cast<long>(st.st_mtime);
    session.fsdb_size = static_cast<long long>(st.st_size);
    session.fsdb_dev = static_cast<unsigned long long>(st.st_dev);
    session.fsdb_inode = static_cast<unsigned long long>(st.st_ino);
    return true;
}

bool SessionManager::current_fsdb_metadata(const SessionInfo& session, SessionInfo& current) {
    current = session;
    return populate_fsdb_metadata(session.fsdb_file, current);
}

bool SessionManager::fsdb_metadata_matches(const SessionInfo& expected, const SessionInfo& current) const {
    return xdebug_core::resource_content_matches(expected.fsdb_mtime,
                                                 expected.fsdb_size,
                                                 current.fsdb_mtime,
                                                 current.fsdb_size);
}

WaitForServerResult SessionManager::wait_for_server(const std::string& session_id, pid_t pid) {
    WaitForServerResult result;

    int timeout_sec = session_start_timeout_sec();
    int iterations = timeout_sec * 10;
    if (iterations <= 0) iterations = 600;
    result.timeout_sec = timeout_sec;

    debug_log("wait_for_server: session=%s pid=%d timeout_sec=%d",
              session_id.c_str(), pid, timeout_sec);
    xdebug_core::log_lifecycle_event("waveform", session_id, "wait_for_server.begin", true,
                                     {{"pid", static_cast<int>(pid)}, {"timeout_sec", timeout_sec}});

    for (int i = 0; i < iterations; ++i) {
        usleep(100000);
        result.elapsed_ms = (i + 1) * 100L;

        SessionInfo endpoint;
        bool endpoint_ready = read_endpoint_file(session_id, endpoint);
        if (!endpoint_ready) {
            endpoint.session_id = session_id;
            endpoint.transport = "uds";
            endpoint.socket_path = xdebug_waveform_socket_path(session_id);
            endpoint_ready = access(endpoint.socket_path.c_str(), F_OK) == 0;
        }
        result.socket_exists = endpoint_ready;
        if (endpoint_ready) {
            if (is_file_transport(endpoint)) {
                result.connect_ok = true;
                result.ping_ok = ping_session_endpoint(endpoint);
                if (result.ping_ok) {
                    result.ok = true;
                    result.reason = "ready";
                    result.endpoint = endpoint;
                    xdebug_core::log_lifecycle_event("waveform", session_id, "wait_for_server.ready", true,
                                                     {{"elapsed_ms", result.elapsed_ms}, {"socket_exists", result.socket_exists},
                                                      {"connect_ok", result.connect_ok}, {"ping_ok", result.ping_ok},
                                                      {"transport", endpoint.transport}, {"file_dir", endpoint.file_dir}});
                    return result;
                }
                continue;
            }
            int fd = connect_session_endpoint(endpoint);
            if (fd >= 0) {
                result.connect_ok = true;
                close(fd);
                result.ping_ok = ping_session_endpoint(endpoint);
                debug_log("wait_for_server: endpoint transport=%s host=%s port=%d socket=%s connect_ok=1 ping_ok=%d elapsed_ms=%ld",
                          endpoint.transport.c_str(), endpoint.host.c_str(), endpoint.port,
                          endpoint.socket_path.c_str(), result.ping_ok ? 1 : 0, result.elapsed_ms);
                if (result.ping_ok) {
                    result.ok = true;
                    result.reason = "ready";
                    result.endpoint = endpoint;
                    xdebug_core::log_lifecycle_event("waveform", session_id, "wait_for_server.ready", true,
                                                     {{"elapsed_ms", result.elapsed_ms}, {"socket_exists", result.socket_exists},
                                                      {"connect_ok", result.connect_ok}, {"ping_ok", result.ping_ok},
                                                      {"transport", endpoint.transport}, {"socket_path", endpoint.socket_path},
                                                      {"host", endpoint.host}, {"port", endpoint.port}});
                    return result;
                }
            } else {
                debug_log("wait_for_server: endpoint_exists=1 connect_ok=0 elapsed_ms=%ld errno=%d(%s)",
                          result.elapsed_ms, errno, strerror(errno));
            }
        }

        int status;
        if (waitpid(pid, &status, WNOHANG) > 0) {
            result.child_exited = true;
            result.child_status = status;
            result.reason = "child_exited";
            debug_log("wait_for_server: child_exited status=%d elapsed_ms=%ld socket_exists=%d connect_ok=%d ping_ok=%d",
                      status, result.elapsed_ms, result.socket_exists ? 1 : 0,
                      result.connect_ok ? 1 : 0, result.ping_ok ? 1 : 0);
            xdebug_core::log_lifecycle_event("waveform", session_id, "wait_for_server.child_exited", false,
                                             {{"elapsed_ms", result.elapsed_ms}, {"child_status", status},
                                              {"socket_exists", result.socket_exists}, {"connect_ok", result.connect_ok},
                                              {"ping_ok", result.ping_ok}});
            return result;
        }
    }

    result.reason = result.socket_exists
        ? (result.connect_ok ? "ping_failed" : "endpoint_connect_failed")
        : "timeout_waiting_endpoint";
    debug_log("wait_for_server: timeout reason=%s elapsed_ms=%ld child_alive=%d endpoint_exists=%d connect_ok=%d ping_ok=%d",
              result.reason.c_str(), result.elapsed_ms,
              kill(pid, 0) == 0 ? 1 : 0,
              result.socket_exists ? 1 : 0,
              result.connect_ok ? 1 : 0,
              result.ping_ok ? 1 : 0);
    xdebug_core::log_lifecycle_event("waveform", session_id, "wait_for_server.timeout", false,
                                     {{"reason", result.reason}, {"elapsed_ms", result.elapsed_ms},
                                      {"socket_exists", result.socket_exists}, {"connect_ok", result.connect_ok},
                                      {"ping_ok", result.ping_ok}});
    if (kill(pid, 0) == 0 && result.reason == "timeout_waiting_endpoint") {
        char log_path[SOCK_PATH_LEN];
        get_debug_log_path(log_path, session_id);
        debug_log("wait_for_server: server is still alive; it may still be opening FSDB. Increase XDEBUG_WAVEFORM_SESSION_START_TIMEOUT_SEC or inspect %s", log_path);
    }
    return result;
}

pid_t SessionManager::spawn_server(const std::string& session_id, const std::string& fsdb_file,
                                   const SessionInfo& endpoint) {
    // Get path to current executable
    char self_path[1024] = {};
    ssize_t len = readlink("/proc/self/exe", self_path, sizeof(self_path) - 1);
    if (len < 0) {
        return -1;
    }

    // Build server argv: [exe, "--server", session_id, fsdb_file, transport args...]
    std::vector<char*> argv;
    argv.push_back(self_path);
    argv.push_back((char*)"--server");

    argv.push_back(const_cast<char*>(session_id.c_str()));

    char* fsdb_file_str = const_cast<char*>(fsdb_file.c_str());
    argv.push_back(fsdb_file_str);
    std::string transport_arg = "--transport";
    std::string transport_value = endpoint.transport.empty() ? "uds" : endpoint.transport;
    std::string bind_arg = "--bind";
    std::string bind_value = endpoint.bind_host;
    std::string host_arg = "--host";
    std::string host_value = endpoint.host;
    std::string port_arg = "--port";
    std::string port_value = std::to_string(endpoint.port);
    std::string auth_arg = "--auth";
    std::string auth_value = endpoint.auth_token;
    argv.push_back(const_cast<char*>(transport_arg.c_str()));
    argv.push_back(const_cast<char*>(transport_value.c_str()));
    argv.push_back(const_cast<char*>(bind_arg.c_str()));
    argv.push_back(const_cast<char*>(bind_value.c_str()));
    argv.push_back(const_cast<char*>(host_arg.c_str()));
    argv.push_back(const_cast<char*>(host_value.c_str()));
    argv.push_back(const_cast<char*>(port_arg.c_str()));
    argv.push_back(const_cast<char*>(port_value.c_str()));
    argv.push_back(const_cast<char*>(auth_arg.c_str()));
    argv.push_back(const_cast<char*>(auth_value.c_str()));
    argv.push_back(nullptr);

    pid_t pid = fork();
    if (pid < 0) {
        return -1;
    }

    if (pid == 0) {
        // Detach the session server from the caller so it survives short-lived
        // CLI invocations such as `xdebug_waveform open ...`.
        if (setsid() < 0) {
            _exit(1);
        }
        signal(SIGHUP, SIG_IGN);

        // Child process - exec server
        execv(self_path, argv.data());
        perror("execv");
        _exit(1);
    }

    return pid;
}

std::string SessionManager::create_session(const std::string& fsdb_file, const std::string& session_id) {
    SessionTransportOptions transport;
    return create_session(fsdb_file, session_id, transport);
}

std::string SessionManager::create_session(const std::string& fsdb_file,
                                           const std::string& session_id,
                                           const SessionTransportOptions& transport_options) {
    if (!SessionRegistry::is_valid_session_name(session_id)) {
        debug_log("create_session: reason=invalid_session_id session=%s", session_id.c_str());
        xdebug_core::log_lifecycle_event("waveform", session_id, "create_session.invalid_session_id", false);
        return "";
    }
    std::string requested_transport = transport_options.transport.empty() ? default_transport_from_env() : transport_options.transport;
    if (!valid_transport(requested_transport)) {
        debug_log("create_session: reason=invalid_transport transport=%s", requested_transport.c_str());
        xdebug_core::log_lifecycle_event("waveform", session_id, "create_session.invalid_transport", false,
                                         {{"transport", requested_transport}});
        return "";
    }
    std::string canonical = canonicalize_fsdb_path(fsdb_file);
    debug_log("create_session: input_fsdb=%s canonical_fsdb=%s", fsdb_file.c_str(), canonical.c_str());
    xdebug_core::log_lifecycle_event("waveform", session_id, "create_session.canonicalized", true,
                                     {{"fsdb", canonical}, {"input_fsdb", fsdb_file}});
    SessionInfo metadata;
    if (!populate_fsdb_metadata(canonical, metadata)) {
        debug_log("create_session: reason=fsdb_stat_failed path=%s errno=%d(%s)",
                  canonical.c_str(), errno, strerror(errno));
        xdebug_core::log_lifecycle_event("waveform", session_id, "create_session.fsdb_stat_failed", false,
                                         {{"fsdb", canonical}, {"errno", errno}, {"message", strerror(errno)}});
        return "";
    }

    int lock_fd = open_registry_lock();
    if (lock_fd < 0) {
        char lock_path[SOCK_PATH_LEN];
        get_registry_lock_path(lock_path);
        debug_log("create_session: reason=registry_lock_open_failed lock=%s errno=%d(%s)",
                  lock_path, errno, strerror(errno));
        xdebug_core::log_lifecycle_event("waveform", session_id, "create_session.registry_lock_open_failed", false,
                                         {{"lock_path", lock_path}, {"errno", errno}, {"message", strerror(errno)}});
        return "";
    }
    if (flock(lock_fd, LOCK_EX) != 0) {
        debug_log("create_session: reason=registry_lock_failed errno=%d(%s)", errno, strerror(errno));
        xdebug_core::log_lifecycle_event("waveform", session_id, "create_session.registry_lock_failed", false,
                                         {{"errno", errno}, {"message", strerror(errno)}});
        close(lock_fd);
        return "";
    }

    cleanup();
    if (registry_->exists(session_id)) {
        debug_log("create_session: reason=session_id_exists session=%s", session_id.c_str());
        xdebug_core::log_lifecycle_event("waveform", session_id, "create_session.session_id_exists", false);
        flock(lock_fd, LOCK_UN);
        close(lock_fd);
        return "";
    }
    if (!xdebug_waveform_ensure_session_dir(session_id)) {
        debug_log("create_session: reason=session_dir_create_failed session=%s", session_id.c_str());
        xdebug_core::log_lifecycle_event("waveform", session_id, "create_session.session_dir_failed", false);
        flock(lock_fd, LOCK_UN);
        close(lock_fd);
        return "";
    }

    SessionInfo endpoint;
    endpoint.session_id = session_id;
    endpoint.transport = requested_transport;
    endpoint.socket_path = xdebug_waveform_socket_path(session_id);
    endpoint.file_dir = xdebug_core::file_transport_dir(xdebug_waveform_session_dir(session_id));
    endpoint.bind_host = transport_options.bind_host.empty()
        ? (endpoint.transport == "tcp" ? "127.0.0.1" : "")
        : transport_options.bind_host;
    endpoint.host = transport_options.host.empty()
        ? (endpoint.bind_host == "0.0.0.0" || endpoint.bind_host == "::" ? current_host_name() : endpoint.bind_host)
        : transport_options.host;
    endpoint.port = endpoint.transport == "tcp" ? transport_options.port : 0;
    endpoint.server_host = current_host_name();
    endpoint.auth_token = endpoint.transport == "tcp" ? generate_auth_token() : "";

    pid_t pid = spawn_server(session_id, canonical, endpoint);
    if (pid < 0) {
        debug_log("create_session: reason=spawn_failed session=%s errno=%d(%s)", session_id.c_str(), errno, strerror(errno));
        xdebug_core::log_lifecycle_event("waveform", session_id, "create_session.spawn_failed", false,
                                         {{"errno", errno}, {"message", strerror(errno)}});
        xdebug_waveform_remove_session_dir(session_id);
        flock(lock_fd, LOCK_UN);
        close(lock_fd);
        return "";
    }

    char sock_path[SOCK_PATH_LEN];
    get_sock_path(sock_path, session_id);
    char debug_log_path[SOCK_PATH_LEN];
    get_debug_log_path(debug_log_path, session_id);
    debug_log("create_session: spawned_server session=%s pid=%d socket=%s debug_log=%s",
              session_id.c_str(), pid, sock_path, debug_log_path);
    xdebug_core::log_lifecycle_event("waveform", session_id, "create_session.spawned_server", true,
                                     {{"pid", static_cast<int>(pid)}, {"socket_path", sock_path},
                                      {"debug_log", debug_log_path}, {"transport", endpoint.transport},
                                      {"host", endpoint.host}, {"port", endpoint.port}});

    WaitForServerResult wait = wait_for_server(session_id, pid);
    if (!wait.ok) {
        debug_log("create_session: reason=%s elapsed_ms=%ld child_exited=%d child_status=%d socket_exists=%d connect_ok=%d ping_ok=%d",
                  wait.reason.c_str(), wait.elapsed_ms, wait.child_exited ? 1 : 0,
                  wait.child_status, wait.socket_exists ? 1 : 0,
                  wait.connect_ok ? 1 : 0, wait.ping_ok ? 1 : 0);
        xdebug_core::log_lifecycle_event("waveform", session_id, "create_session.startup_failed", false,
                                         {{"reason", wait.reason}, {"elapsed_ms", wait.elapsed_ms},
                                          {"child_exited", wait.child_exited}, {"child_status", wait.child_status},
                                          {"socket_exists", wait.socket_exists}, {"connect_ok", wait.connect_ok},
                                          {"ping_ok", wait.ping_ok}});
        kill(pid, SIGTERM);
        unlink(sock_path);
        xdebug_waveform_remove_session_dir(session_id);
        flock(lock_fd, LOCK_UN);
        close(lock_fd);
        return "";
    }

    SessionInfo session;
    session.session_id = session_id;
    session.transport = wait.endpoint.transport.empty() ? endpoint.transport : wait.endpoint.transport;
    session.socket_path = wait.endpoint.socket_path.empty() ? sock_path : wait.endpoint.socket_path;
    session.file_dir = wait.endpoint.file_dir.empty() ? endpoint.file_dir : wait.endpoint.file_dir;
    session.host = wait.endpoint.host.empty() ? endpoint.host : wait.endpoint.host;
    session.bind_host = wait.endpoint.bind_host.empty() ? endpoint.bind_host : wait.endpoint.bind_host;
    session.port = wait.endpoint.port ? wait.endpoint.port : endpoint.port;
    session.server_host = wait.endpoint.server_host.empty() ? endpoint.server_host : wait.endpoint.server_host;
    session.auth_token = wait.endpoint.auth_token.empty() ? endpoint.auth_token : wait.endpoint.auth_token;
    session.server_pid = pid;
    session.fsdb_file = canonical;
    session.created_at = time(nullptr);
    session.last_active = session.created_at;
    populate_fsdb_metadata(canonical, session);

    if (!registry_->add(session)) {
        debug_log("create_session: reason=registry_add_failed session=%s", session_id.c_str());
        xdebug_core::log_lifecycle_event("waveform", session_id, "create_session.registry_add_failed", false);
        kill(pid, SIGTERM);
        unlink(sock_path);
        xdebug_waveform_remove_session_dir(session_id);
        flock(lock_fd, LOCK_UN);
        close(lock_fd);
        return "";
    }

    SessionHealth health = diagnose_session(session_id);
    if (!health.healthy) {
        debug_log("create_session: reason=post_create_health_failed session=%s status=%s message=%s",
                  session_id.c_str(), session_health_status_name(health.status), health.message.c_str());
        xdebug_core::log_lifecycle_event("waveform", session_id, "create_session.post_create_health_failed", false,
                                         {{"status", session_health_status_name(health.status)}, {"message", health.message}});
        kill(pid, SIGTERM);
        registry_->remove(session_id);
        unlink(sock_path);
        flock(lock_fd, LOCK_UN);
        close(lock_fd);
        return "";
    }

    flock(lock_fd, LOCK_UN);
    close(lock_fd);
    debug_log("create_session: success session=%s pid=%d transport=%s host=%s port=%d socket=%s",
              session_id.c_str(), pid, session.transport.c_str(), session.host.c_str(),
              session.port, session.socket_path.c_str());
    xdebug_core::log_lifecycle_event("waveform", session_id, "create_session.success", true,
                                     {{"pid", static_cast<int>(pid)}, {"fsdb", session.fsdb_file},
                                      {"transport", session.transport}, {"socket_path", session.socket_path},
                                      {"host", session.host}, {"port", session.port}});
    return session_id;
}

bool SessionManager::stop_process(const SessionInfo& session, bool remove_record, bool remove_events) {
    xdebug_core::log_lifecycle_event("waveform", session.session_id, "stop_process.begin", true,
                                     {{"pid", session.server_pid}, {"remove_record", remove_record},
                                      {"remove_events", remove_events}, {"socket_path", session.socket_path}});
    send_quit_to_endpoint(session);

    int status;
    if (is_local_session_host(session)) {
        for (int i = 0; i < 10; ++i) {
            if (waitpid(session.server_pid, &status, WNOHANG) > 0) break;
            if (kill(session.server_pid, 0) != 0) break;
            usleep(100000);
        }
        if (kill(session.server_pid, 0) == 0) {
            xdebug_core::log_lifecycle_event("waveform", session.session_id, "stop_process.sigterm", true,
                                             {{"pid", session.server_pid}});
            kill(session.server_pid, SIGTERM);
            usleep(300000);
        }
        if (kill(session.server_pid, 0) == 0) {
            xdebug_core::log_lifecycle_event("waveform", session.session_id, "stop_process.sigkill", true,
                                             {{"pid", session.server_pid}});
            kill(session.server_pid, SIGKILL);
            usleep(100000);
        }
        waitpid(session.server_pid, &status, WNOHANG);
    }

    unlink(session.socket_path.c_str());
    if (remove_record) registry_->remove(session.session_id);
    if (!remove_record && remove_events) xdebug_waveform_remove_session_dir(session.session_id);
    xdebug_core::log_lifecycle_event("waveform", session.session_id, "stop_process.end", true);
    return true;
}

bool SessionManager::restart_session(const std::string& session_id) {
    debug_log("restart_session: begin session=%s", session_id.c_str());
    xdebug_core::log_lifecycle_event("waveform", session_id, "restart_session.begin", true);
    int lock_fd = open_registry_lock();
    if (lock_fd < 0) {
        debug_log("restart_session: reason=registry_lock_open_failed errno=%d(%s)",
                  errno, strerror(errno));
        xdebug_core::log_lifecycle_event("waveform", session_id, "restart_session.registry_lock_open_failed", false,
                                         {{"errno", errno}, {"message", strerror(errno)}});
        return false;
    }
    if (flock(lock_fd, LOCK_EX) != 0) {
        debug_log("restart_session: reason=registry_lock_failed errno=%d(%s)",
                  errno, strerror(errno));
        xdebug_core::log_lifecycle_event("waveform", session_id, "restart_session.registry_lock_failed", false,
                                         {{"errno", errno}, {"message", strerror(errno)}});
        close(lock_fd);
        return false;
    }

    SessionInfo old_session;
    if (!registry_->get(session_id, old_session)) {
        debug_log("restart_session: reason=registry_missing session=%s", session_id.c_str());
        xdebug_core::log_lifecycle_event("waveform", session_id, "restart_session.registry_missing", false);
        flock(lock_fd, LOCK_UN);
        close(lock_fd);
        return false;
    }

    SessionInfo metadata;
    if (!current_fsdb_metadata(old_session, metadata)) {
        debug_log("restart_session: reason=fsdb_stat_failed path=%s errno=%d(%s)",
                  old_session.fsdb_file.c_str(), errno, strerror(errno));
        xdebug_core::log_lifecycle_event("waveform", session_id, "restart_session.fsdb_stat_failed", false,
                                         {{"fsdb", old_session.fsdb_file}, {"errno", errno}, {"message", strerror(errno)}});
        flock(lock_fd, LOCK_UN);
        close(lock_fd);
        return false;
    }
    debug_log("restart_session: fsdb_stat mtime=%ld size=%lld dev=%llu inode=%llu",
              metadata.fsdb_mtime, metadata.fsdb_size,
              metadata.fsdb_dev, metadata.fsdb_inode);

    debug_log("restart_session: stopping_old_process pid=%d socket=%s",
              old_session.server_pid, old_session.socket_path.c_str());
    stop_process(old_session, false, false);

    if (!is_local_session_host(old_session)) {
        debug_log("restart_session: reason=remote_restart_required server_host=%s current_host=%s",
                  old_session.server_host.c_str(), current_host_name().c_str());
        xdebug_core::log_lifecycle_event("waveform", session_id, "restart_session.remote_restart_required", false,
                                         {{"server_host", old_session.server_host}, {"current_host", current_host_name()}});
        flock(lock_fd, LOCK_UN);
        close(lock_fd);
        return false;
    }

    pid_t pid = spawn_server(session_id, old_session.fsdb_file, old_session);
    if (pid < 0) {
        debug_log("restart_session: reason=spawn_failed errno=%d(%s)",
                  errno, strerror(errno));
        xdebug_core::log_lifecycle_event("waveform", session_id, "restart_session.spawn_failed", false,
                                         {{"errno", errno}, {"message", strerror(errno)}});
        flock(lock_fd, LOCK_UN);
        close(lock_fd);
        return false;
    }
    debug_log("restart_session: spawned_server pid=%d", pid);
    xdebug_core::log_lifecycle_event("waveform", session_id, "restart_session.spawned_server", true,
                                     {{"pid", static_cast<int>(pid)}});
    WaitForServerResult wait = wait_for_server(session_id, pid);
    if (!wait.ok) {
        debug_log("restart_session: reason=%s elapsed_ms=%ld child_exited=%d child_status=%d socket_exists=%d connect_ok=%d ping_ok=%d",
                  wait.reason.c_str(), wait.elapsed_ms, wait.child_exited ? 1 : 0,
                  wait.child_status, wait.socket_exists ? 1 : 0,
                  wait.connect_ok ? 1 : 0, wait.ping_ok ? 1 : 0);
        xdebug_core::log_lifecycle_event("waveform", session_id, "restart_session.startup_failed", false,
                                         {{"reason", wait.reason}, {"elapsed_ms", wait.elapsed_ms},
                                          {"child_exited", wait.child_exited}, {"child_status", wait.child_status},
                                          {"socket_exists", wait.socket_exists}, {"connect_ok", wait.connect_ok},
                                          {"ping_ok", wait.ping_ok}});
        kill(pid, SIGTERM);
        char sock_path[SOCK_PATH_LEN];
        get_sock_path(sock_path, session_id);
        unlink(sock_path);
        flock(lock_fd, LOCK_UN);
        close(lock_fd);
        return false;
    }

    SessionInfo session = old_session;
    char sock_path[SOCK_PATH_LEN];
    get_sock_path(sock_path, session_id);
    if (!wait.endpoint.transport.empty()) {
        session.transport = wait.endpoint.transport;
        session.socket_path = wait.endpoint.socket_path.empty() ? sock_path : wait.endpoint.socket_path;
        session.file_dir = wait.endpoint.file_dir.empty() ? old_session.file_dir : wait.endpoint.file_dir;
        session.host = wait.endpoint.host;
        session.bind_host = wait.endpoint.bind_host;
        session.port = wait.endpoint.port;
        session.server_host = wait.endpoint.server_host;
        session.auth_token = wait.endpoint.auth_token;
    } else {
        session.socket_path = sock_path;
    }
    session.server_pid = pid;
    session.last_active = time(nullptr);
    populate_fsdb_metadata(session.fsdb_file, session);

    bool ok = registry_->upsert(session);
    debug_log("restart_session: registry_upsert=%d session=%s pid=%d",
              ok ? 1 : 0, session_id.c_str(), pid);
    xdebug_core::log_lifecycle_event("waveform", session_id, "restart_session.registry_upsert", ok,
                                     {{"pid", static_cast<int>(pid)}});
    flock(lock_fd, LOCK_UN);
    close(lock_fd);
    return ok;
}

bool SessionManager::ensure_session_current(const std::string& session_id) {
    debug_log("ensure_session_current: begin session=%s", session_id.c_str());
    xdebug_core::log_lifecycle_event("waveform", session_id, "ensure_session_current.begin", true);
    SessionInfo session;
    if (!registry_->get(session_id, session)) {
        debug_log("ensure_session_current: reason=registry_missing session=%s", session_id.c_str());
        xdebug_core::log_lifecycle_event("waveform", session_id, "ensure_session_current.registry_missing", false);
        return false;
    }

    SessionInfo current;
    if (!current_fsdb_metadata(session, current)) {
        debug_log("ensure_session_current: reason=fsdb_stat_failed path=%s errno=%d(%s)",
                  session.fsdb_file.c_str(), errno, strerror(errno));
        xdebug_core::log_lifecycle_event("waveform", session_id, "ensure_session_current.fsdb_stat_failed", false,
                                         {{"fsdb", session.fsdb_file}, {"errno", errno}, {"message", strerror(errno)}});
        return false;
    }
    if (!fsdb_metadata_matches(session, current)) {
        bool identity_changed = xdebug_core::resource_identity_differs(session.fsdb_dev,
                                                                       session.fsdb_inode,
                                                                       current.fsdb_dev,
                                                                       current.fsdb_inode);
        debug_log("ensure_session_current: fsdb_changed session=%s old_mtime=%ld new_mtime=%ld old_size=%lld new_size=%lld old_dev=%llu new_dev=%llu old_inode=%llu new_inode=%llu",
                  session_id.c_str(), session.fsdb_mtime, current.fsdb_mtime,
                  session.fsdb_size, current.fsdb_size,
                  session.fsdb_dev, current.fsdb_dev,
                  session.fsdb_inode, current.fsdb_inode);
        xdebug_core::log_lifecycle_event("waveform", session_id, "ensure_session_current.resource_changed", false,
                                         {{"old_mtime", session.fsdb_mtime}, {"new_mtime", current.fsdb_mtime},
                                          {"old_size", session.fsdb_size}, {"new_size", current.fsdb_size},
                                          {"old_dev", session.fsdb_dev}, {"new_dev", current.fsdb_dev},
                                          {"old_inode", session.fsdb_inode}, {"new_inode", current.fsdb_inode},
                                          {"identity_changed", identity_changed}});
        return false;
    }
    if (xdebug_core::resource_identity_differs(session.fsdb_dev,
                                               session.fsdb_inode,
                                               current.fsdb_dev,
                                               current.fsdb_inode)) {
        debug_log("ensure_session_current: fsdb_identity_changed session=%s old_dev=%llu new_dev=%llu old_inode=%llu new_inode=%llu content_match=1",
                  session_id.c_str(), session.fsdb_dev, current.fsdb_dev,
                  session.fsdb_inode, current.fsdb_inode);
        xdebug_core::log_lifecycle_event("waveform", session_id, "ensure_session_current.fsdb_identity_changed", true,
                                         {{"old_dev", session.fsdb_dev}, {"new_dev", current.fsdb_dev},
                                          {"old_inode", session.fsdb_inode}, {"new_inode", current.fsdb_inode},
                                          {"content_match", true}, {"identity_changed", true}});
    }
    SessionHealth health = diagnose_session(session_id);
    debug_log("ensure_session_current: diagnose status=%s healthy=%d message=%s",
              session_health_status_name(health.status), health.healthy ? 1 : 0,
              health.message.c_str());
    xdebug_core::log_lifecycle_event("waveform", session_id, "ensure_session_current.diagnose", health.healthy,
                                     {{"status", session_health_status_name(health.status)}, {"message", health.message}});
    return health.healthy;
}

bool SessionManager::touch_session(const std::string& session_id) {
    return registry_->touch(session_id, time(nullptr));
}

bool SessionManager::kill_session(const std::string& session_id) {
    debug_log("kill_session: begin session=%s", session_id.c_str());
    xdebug_core::log_lifecycle_event("waveform", session_id, "kill_session.begin", true);
    SessionInfo session;
    if (!registry_->get(session_id, session)) {
        debug_log("kill_session: reason=registry_missing session=%s", session_id.c_str());
        xdebug_core::log_lifecycle_event("waveform", session_id, "kill_session.registry_missing", false);
        return false;
    }

    SessionHealth health = diagnose_session(session_id);
    debug_log("kill_session: health status=%s healthy=%d message=%s",
              session_health_status_name(health.status), health.healthy ? 1 : 0,
              health.message.c_str());
    if (!health.healthy) {
        if (is_local_session_host(session) && kill(session.server_pid, 0) == 0) {
            debug_log("kill_session: stale_process_alive pid=%d sending SIGTERM", session.server_pid);
            xdebug_core::log_lifecycle_event("waveform", session_id, "kill_session.stale_sigterm", true,
                                             {{"pid", session.server_pid}});
            kill(session.server_pid, SIGTERM);
            usleep(300000);
            if (kill(session.server_pid, 0) == 0) kill(session.server_pid, SIGKILL);
        }
        registry_->remove(session_id);
        xdebug_core::log_lifecycle_event("waveform", session_id, "kill_session.removed_unhealthy", true,
                                         {{"status", session_health_status_name(health.status)}, {"message", health.message}});
        return true;
    }

    return stop_process(session, true, true);
}

bool SessionManager::kill_all_sessions() {
    std::vector<SessionInfo> sessions = list_sessions();
    debug_log("kill_all_sessions: count=%zu", sessions.size());
    xdebug_core::log_lifecycle_event("waveform", "adhoc", "kill_all.begin", true,
                                     {{"count", sessions.size()}});
    for (const auto& session : sessions) {
        kill_session(session.session_id);
    }
    registry_->clear_all();
    xdebug_core::log_lifecycle_event("waveform", "adhoc", "kill_all.end", true);
    return true;
}

bool SessionManager::get_session(const std::string& session_id, SessionInfo& info) {
    return registry_->get(session_id, info);
}

bool SessionManager::get_latest_session(SessionInfo& info) {
    return registry_->get_latest(info);
}

std::vector<SessionInfo> SessionManager::list_sessions() {
    cleanup();
    std::vector<SessionInfo> sessions;
    registry_->load_all(sessions);
    return sessions;
}

bool SessionManager::gc_sessions() {
    debug_log("gc_sessions: begin");
    xdebug_core::log_lifecycle_event("waveform", "adhoc", "gc.begin", true);
    cleanup();
    const char* env_timeout = getenv("XDEBUG_WAVEFORM_IDLE_TIMEOUT_SEC");
    int timeout = env_timeout ? atoi(env_timeout) : 1800;
    if (timeout <= 0) timeout = 1800;
    debug_log("gc_sessions: idle_timeout_sec=%d", timeout);
    xdebug_core::log_lifecycle_event("waveform", "adhoc", "gc.timeout", true,
                                     {{"idle_timeout_sec", timeout}});
    std::vector<SessionInfo> sessions;
    registry_->load_all(sessions);
    time_t now = time(nullptr);
    for (const auto& session : sessions) {
        time_t last = session.last_active ? session.last_active : session.created_at;
        if (last > 0 && now - last > timeout) {
            debug_log("gc_sessions: removing_idle session=%s pid=%d idle_sec=%ld timeout_sec=%d",
                      session.session_id.c_str(),
                      session.server_pid,
                      static_cast<long>(now - last),
                      timeout);
            xdebug_core::log_lifecycle_event("waveform", session.session_id, "gc.removing_idle", true,
                                             {{"pid", session.server_pid},
                                              {"idle_sec", static_cast<long>(now - last)},
                                              {"timeout_sec", timeout}});
            stop_process(session, true, true);
        }
    }
    cleanup();
    debug_log("gc_sessions: done");
    xdebug_core::log_lifecycle_event("waveform", "adhoc", "gc.end", true);
    return true;
}

SessionHealth SessionManager::diagnose_session(const std::string& session_id) {
    SessionHealth health;
    health.session_id = session_id;
    debug_log("diagnose_session: begin session=%s", session_id.c_str());

    SessionInfo session;
    if (!registry_->get(session_id, session)) {
        health.status = SessionHealthStatus::RegistryMissing;
        health.message = "Session is not present in the registry";
        debug_log("diagnose_session: status=%s message=%s",
                  session_health_status_name(health.status),
                  health.message.c_str());
        xdebug_core::log_lifecycle_event("waveform", session_id, "diagnose.registry_missing", false);
        return health;
    }

    health.info = session;
    debug_log("diagnose_session: registry pid=%d transport=%s socket=%s host=%s port=%d fsdb=%s",
              session.server_pid,
              session.transport.c_str(),
              session.socket_path.c_str(),
              session.host.c_str(),
              session.port,
              session.fsdb_file.c_str());

    SessionInfo current;
    if (!current_fsdb_metadata(session, current)) {
        health.status = SessionHealthStatus::FsdbMissing;
        health.message = "FSDB file is missing or cannot be stat'ed";
        debug_log("diagnose_session: status=%s message=%s",
                  session_health_status_name(health.status),
                  health.message.c_str());
        xdebug_core::log_lifecycle_event("waveform", session_id, "diagnose.fsdb_missing", false,
                                         {{"fsdb", session.fsdb_file}});
        return health;
    }
    debug_log("diagnose_session: fsdb_stat old_mtime=%ld new_mtime=%ld old_size=%lld new_size=%lld old_dev=%llu new_dev=%llu old_inode=%llu new_inode=%llu",
              (long)session.fsdb_mtime,
              (long)current.fsdb_mtime,
              (long long)session.fsdb_size,
              (long long)current.fsdb_size,
              (unsigned long long)session.fsdb_dev,
              (unsigned long long)current.fsdb_dev,
              (unsigned long long)session.fsdb_inode,
              (unsigned long long)current.fsdb_inode);
    if (!fsdb_metadata_matches(session, current)) {
        bool identity_changed = xdebug_core::resource_identity_differs(session.fsdb_dev,
                                                                       session.fsdb_inode,
                                                                       current.fsdb_dev,
                                                                       current.fsdb_inode);
        health.status = SessionHealthStatus::FsdbChanged;
        health.message = "FSDB file changed since session was opened";
        debug_log("diagnose_session: status=%s message=%s",
                  session_health_status_name(health.status),
                  health.message.c_str());
        xdebug_core::log_lifecycle_event("waveform", session_id, "diagnose.fsdb_changed", false,
                                         {{"fsdb", session.fsdb_file},
                                          {"old_mtime", session.fsdb_mtime}, {"new_mtime", current.fsdb_mtime},
                                          {"old_size", session.fsdb_size}, {"new_size", current.fsdb_size},
                                          {"old_dev", session.fsdb_dev}, {"new_dev", current.fsdb_dev},
                                          {"old_inode", session.fsdb_inode}, {"new_inode", current.fsdb_inode},
                                          {"identity_changed", identity_changed}});
        return health;
    }
    if (xdebug_core::resource_identity_differs(session.fsdb_dev,
                                               session.fsdb_inode,
                                               current.fsdb_dev,
                                               current.fsdb_inode)) {
        debug_log("diagnose_session: fsdb_identity_changed old_dev=%llu new_dev=%llu old_inode=%llu new_inode=%llu content_match=1",
                  (unsigned long long)session.fsdb_dev,
                  (unsigned long long)current.fsdb_dev,
                  (unsigned long long)session.fsdb_inode,
                  (unsigned long long)current.fsdb_inode);
        xdebug_core::log_lifecycle_event("waveform", session_id, "diagnose.fsdb_identity_changed", true,
                                         {{"fsdb", session.fsdb_file},
                                          {"old_dev", session.fsdb_dev}, {"new_dev", current.fsdb_dev},
                                          {"old_inode", session.fsdb_inode}, {"new_inode", current.fsdb_inode},
                                          {"content_match", true}, {"identity_changed", true}});
    }

    if (is_local_session_host(session) && kill(session.server_pid, 0) != 0) {
        health.status = SessionHealthStatus::ProcessExited;
        health.message = "Server process is not running";
        debug_log("diagnose_session: status=%s pid=%d errno=%d(%s)",
                  session_health_status_name(health.status),
                  session.server_pid,
                  errno,
                  strerror(errno));
        xdebug_core::log_lifecycle_event("waveform", session_id, "diagnose.process_exited", false,
                                         {{"pid", session.server_pid}, {"errno", errno}, {"message", strerror(errno)}});
        return health;
    }
    debug_log("diagnose_session: process_alive_or_remote pid=%d", session.server_pid);

    if (!is_tcp_transport(session) && !is_file_transport(session) && access(session.socket_path.c_str(), F_OK) != 0) {
        health.status = SessionHealthStatus::SocketMissing;
        health.message = "Server socket file is missing";
        debug_log("diagnose_session: status=%s socket=%s errno=%d(%s)",
                  session_health_status_name(health.status),
                  session.socket_path.c_str(),
                  errno,
                  strerror(errno));
        xdebug_core::log_lifecycle_event("waveform", session_id, "diagnose.socket_missing", false,
                                         {{"socket_path", session.socket_path}, {"errno", errno}, {"message", strerror(errno)}});
        return health;
    }
    debug_log("diagnose_session: endpoint_exists path=%s", session.socket_path.c_str());

    if (!is_file_transport(session)) {
    int fd = connect_session_endpoint(session);
    if (fd < 0) {
        health.status = SessionHealthStatus::ConnectFailed;
        health.message = "Server socket exists but cannot be connected";
        debug_log("diagnose_session: status=%s socket=%s",
                  session_health_status_name(health.status),
                  session.socket_path.c_str());
        xdebug_core::log_lifecycle_event("waveform", session_id, "diagnose.connect_failed", false,
                                         {{"transport", session.transport}, {"socket_path", session.socket_path},
                                          {"host", session.host}, {"port", session.port}});
        return health;
    }
    close(fd);
    }
    debug_log("diagnose_session: connect_ok transport=%s", session.transport.c_str());

    if (!ping_session_endpoint(session)) {
        health.status = SessionHealthStatus::PingFailed;
        health.message = "Server did not respond to PING";
        debug_log("diagnose_session: status=%s socket=%s",
                  session_health_status_name(health.status),
                  session.socket_path.c_str());
        xdebug_core::log_lifecycle_event("waveform", session_id, "diagnose.ping_failed", false,
                                         {{"socket_path", session.socket_path}});
        return health;
    }
    debug_log("diagnose_session: ping_ok socket=%s", session.socket_path.c_str());

    health.healthy = true;
    health.status = SessionHealthStatus::Healthy;
    health.message = "Session is healthy";
    debug_log("diagnose_session: status=%s message=%s",
              session_health_status_name(health.status),
                  health.message.c_str());
    xdebug_core::log_lifecycle_event("waveform", session_id, "diagnose.healthy", true,
                                     {{"pid", session.server_pid}, {"transport", session.transport}});
    return health;
}

bool SessionManager::is_session_alive(const std::string& session_id) {
    return diagnose_session(session_id).healthy;
}

std::string SessionManager::get_socket_path(const std::string& session_id) {
    char path[SOCK_PATH_LEN];
    get_sock_path(path, session_id);
    return std::string(path);
}

void SessionManager::cleanup() {
    std::vector<SessionInfo> before;
    registry_->load_all(before);
    debug_log("cleanup: before_count=%zu", before.size());
    xdebug_core::log_lifecycle_event("waveform", "adhoc", "cleanup.begin", true,
                                     {{"before_count", before.size()}});
    registry_->cleanup_stale();
    std::vector<SessionInfo> after;
    registry_->load_all(after);
    xdebug_core::log_lifecycle_event("waveform", "adhoc", "cleanup.end", true,
                                     {{"before_count", before.size()}, {"after_count", after.size()}});
    debug_log("cleanup: after_count=%zu", after.size());
}

} // namespace xdebug_waveform
