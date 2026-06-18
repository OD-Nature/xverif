#include "session_manager.h"
#include "session_transport.h"
#include "../common/xdebug_design_paths.h"
#include "../protocol/protocol.h"
#include "logging/action_log.h"
#include "session/session_types.h"
#include "transport/file_exchange.h"

#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <strings.h>
#include <cstdarg>
#include <unistd.h>
#include <sys/wait.h>
#include <sys/time.h>
#include <signal.h>
#include <sys/stat.h>
#include <limits.h>
#include <fcntl.h>

namespace xdebug_design {

namespace {

std::string default_transport_from_env() {
    const char* env = getenv("XDEBUG_TRANSPORT");
    if (env && *env) return std::string(env);
    return "uds";
}

bool valid_transport(const std::string& transport) {
    return transport == "uds" || transport == "tcp" || transport == "file";
}

}  // namespace

bool xdebug_design_debug_enabled() {
    const char* env = getenv("XDEBUG_DESIGN_DEBUG");
    return env && env[0] != '\0' && strcmp(env, "0") != 0 &&
           strcasecmp(env, "false") != 0 && strcasecmp(env, "off") != 0;
}

void SessionManager::debug_log(const char* fmt, ...) const {
    if (!xdebug_design_debug_enabled()) return;
    fprintf(stderr, "[xdebug_design-debug] ");
    va_list ap;
    va_start(ap, fmt);
    vfprintf(stderr, fmt, ap);
    va_end(ap);
    fprintf(stderr, "\n");
    fflush(stderr);
}

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
        case SessionHealthStatus::DbdirMissing:
            return "dbdir_missing";
        case SessionHealthStatus::DbdirChanged:
            return "dbdir_changed";
    }
    return "unknown";
}

SessionManager::SessionManager() : registry_(new SessionRegistry()) {
}

SessionManager::~SessionManager() {
}

pid_t SessionManager::spawn_server(const std::string& session_id, const std::vector<std::string>& args,
                                   const SessionInfo& endpoint) {
    // Get path to current executable
    char self_path[1024] = {};
    ssize_t len = readlink("/proc/self/exe", self_path, sizeof(self_path) - 1);
    if (len < 0) {
        return -1;
    }

    // Build server argv: [exe, "--server", session_id, ...design_args...]
    std::vector<char*> argv;
    argv.push_back(self_path);
    argv.push_back((char*)"--server");

    std::string session_id_arg = session_id;
    argv.push_back(const_cast<char*>(session_id_arg.c_str()));

    std::vector<std::string> arg_storage = args;  // Keep strings alive
    arg_storage.push_back("--transport");
    arg_storage.push_back(endpoint.transport.empty() ? "uds" : endpoint.transport);
    arg_storage.push_back("--bind");
    arg_storage.push_back(endpoint.bind_host);
    arg_storage.push_back("--host");
    arg_storage.push_back(endpoint.host);
    arg_storage.push_back("--port");
    arg_storage.push_back(std::to_string(endpoint.port));
    arg_storage.push_back("--auth");
    arg_storage.push_back(endpoint.auth_token);
    for (const auto& arg : arg_storage) {
        argv.push_back(const_cast<char*>(arg.c_str()));
    }
    argv.push_back(nullptr);

    pid_t pid = fork();
    if (pid < 0) {
        return -1;
    }

    if (pid == 0) {
        // Detach the session server from the short-lived CLI process so it
        // survives after `xdebug_design open ...` exits.
        if (setsid() < 0) {
            _exit(1);
        }
        signal(SIGHUP, SIG_IGN);

        // Close inherited file descriptors (fds > 2) to avoid leaking
        // pipe ends and other handles into the daemonised engine server.
        int max_fd = sysconf(_SC_OPEN_MAX);
        if (max_fd <= 0 || max_fd > 65536) max_fd = 256;
        for (int i = 3; i < max_fd; ++i) close(i);

        // Child process - exec server
        execv(self_path, argv.data());
        perror("execv");
        _exit(1);
    }

    return pid;
}

std::string SessionManager::canonicalize_dbdir_path(const std::string& dbdir_path) const {
    char resolved[PATH_MAX];
    if (realpath(dbdir_path.c_str(), resolved)) {
        return std::string(resolved);
    }
    return dbdir_path;
}

bool SessionManager::populate_dbdir_metadata(const std::string& dbdir_path, SessionInfo& session) const {
    struct stat st;
    if (stat(dbdir_path.c_str(), &st) != 0) return false;
    if (!S_ISDIR(st.st_mode)) return false;
    session.dbdir_path = dbdir_path;
    session.design_file = dbdir_path;
    session.dbdir_mtime = static_cast<long>(st.st_mtime);
    session.dbdir_size = static_cast<long long>(st.st_size);
    session.dbdir_dev = static_cast<unsigned long long>(st.st_dev);
    session.dbdir_inode = static_cast<unsigned long long>(st.st_ino);
    return true;
}

bool SessionManager::current_dbdir_metadata(const SessionInfo& session, SessionInfo& current) const {
    if (session.dbdir_path.empty()) return false;
    current = session;
    return populate_dbdir_metadata(session.dbdir_path, current);
}

bool SessionManager::dbdir_metadata_matches(const SessionInfo& expected, const SessionInfo& current) const {
    return xdebug_core::resource_content_matches(expected.dbdir_mtime,
                                                 expected.dbdir_size,
                                                 current.dbdir_mtime,
                                                 current.dbdir_size);
}

bool SessionManager::parse_open_args(const std::vector<std::string>& args,
                                     std::string& canonical_dbdir,
                                     std::vector<std::string>& canonical_args) const {
    // The unified engine accepts both -dbdir and/or -fsdb.
    // Validate daidir if present; fsdb is validated by the engine at startup.
    canonical_args = args;
    bool has_daidir = false;

    for (size_t i = 0; i + 1 < args.size(); ++i) {
        if (args[i] == "-dbdir") {
            std::string dbdir = args[i + 1];
            while (dbdir.size() > 1 && dbdir.back() == '/') dbdir.pop_back();
            const std::string suffix = ".daidir";
            if (dbdir.size() < suffix.size() ||
                dbdir.compare(dbdir.size() - suffix.size(), suffix.size(), suffix) != 0)
                return false;
            canonical_dbdir = canonicalize_dbdir_path(dbdir);
            SessionInfo metadata;
            if (!populate_dbdir_metadata(canonical_dbdir, metadata))
                return false;
            canonical_args[i + 1] = canonical_dbdir;
            has_daidir = true;
        }
    }

    // At least one resource is required.
    if (!has_daidir && canonical_args.empty())
        return false;
    return true;
}

WaitForServerResult SessionManager::wait_for_server(const std::string& session_id, pid_t pid) {
    WaitForServerResult result;

    int timeout_sec = 60;
    const char* env = getenv("XDEBUG_DESIGN_SESSION_START_TIMEOUT_SEC");
    if (env && *env) {
        int v = atoi(env);
        if (v > 0) timeout_sec = v;
    }
    int loops = timeout_sec * 10;
    if (loops <= 0) loops = 600;
    debug_log("wait_for_server: session=%s pid=%d timeout_sec=%d",
              session_id.c_str(), pid, timeout_sec);
    xdebug_core::log_lifecycle_event("design", session_id, "wait_for_server.begin", true,
                                     {{"pid", static_cast<int>(pid)}, {"timeout_sec", timeout_sec}});

    for (int i = 0; i < loops; ++i) {
        usleep(100000);  // 100ms
        result.elapsed_ms = (i + 1) * 100L;

        SessionInfo endpoint;
        bool endpoint_ready = read_endpoint_file(session_id, endpoint);
        if (!endpoint_ready) {
            endpoint.session_id = session_id;
            endpoint.transport = "uds";
            endpoint.socket_path = xdebug_design_socket_path(session_id);
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
                    xdebug_core::log_lifecycle_event("design", session_id, "wait_for_server.ready", true,
                                                     {{"elapsed_ms", result.elapsed_ms}, {"socket_exists", result.socket_exists},
                                                      {"connect_ok", result.connect_ok}, {"ping_ok", result.ping_ok},
                                                      {"transport", result.endpoint.transport},
                                                      {"file_dir", result.endpoint.file_dir}});
                    return result;
                }
            } else {
            int fd = connect_session_endpoint(endpoint);
            if (fd >= 0) {
                result.connect_ok = true;
                close(fd);
                result.ping_ok = ping_session_endpoint(endpoint);
                if (result.ping_ok) {
                    result.ok = true;
                    result.reason = "ready";
                    result.endpoint = endpoint;
                    debug_log("wait_for_server: socket_exists=1 connect_ok=1 ping_ok=1 elapsed_ms=%ld",
                              result.elapsed_ms);
                    xdebug_core::log_lifecycle_event("design", session_id, "wait_for_server.ready", true,
                                                     {{"elapsed_ms", result.elapsed_ms}, {"socket_exists", result.socket_exists},
                                                      {"connect_ok", result.connect_ok}, {"ping_ok", result.ping_ok},
                                                      {"transport", result.endpoint.transport},
                                                      {"socket_path", result.endpoint.socket_path},
                                                      {"host", result.endpoint.host}, {"port", result.endpoint.port}});
                    return result;
                }
            }
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
            xdebug_core::log_lifecycle_event("design", session_id, "wait_for_server.child_exited", false,
                                             {{"elapsed_ms", result.elapsed_ms}, {"child_status", status},
                                              {"socket_exists", result.socket_exists}, {"connect_ok", result.connect_ok},
                                              {"ping_ok", result.ping_ok}});
            return result;
        }
    }

    result.reason = result.socket_exists ? (result.connect_ok ? "ping_failed" : "socket_connect_failed")
                                         : "timeout_waiting_socket";
    debug_log("wait_for_server: timeout reason=%s elapsed_ms=%ld socket_exists=%d connect_ok=%d ping_ok=%d",
              result.reason.c_str(), result.elapsed_ms, result.socket_exists ? 1 : 0,
              result.connect_ok ? 1 : 0, result.ping_ok ? 1 : 0);
    xdebug_core::log_lifecycle_event("design", session_id, "wait_for_server.timeout", false,
                                     {{"reason", result.reason}, {"elapsed_ms", result.elapsed_ms},
                                      {"socket_exists", result.socket_exists}, {"connect_ok", result.connect_ok},
                                      {"ping_ok", result.ping_ok}});
    return result;
}

SessionEnsureResult SessionManager::ensure_session(const std::vector<std::string>& design_args, const std::string& session_name) {
    SessionTransportOptions transport;
    return ensure_session(design_args, session_name, transport);
}

SessionEnsureResult SessionManager::ensure_session(const std::vector<std::string>& design_args,
                                                   const std::string& session_name,
                                                   const SessionTransportOptions& transport_options) {
    SessionEnsureResult result;

    std::string canonical_dbdir;
    std::vector<std::string> canonical_args;
    if (!parse_open_args(design_args, canonical_dbdir, canonical_args)) {
        debug_log("ensure_session: reason=invalid_args");
        xdebug_core::log_lifecycle_event("design", session_name, "ensure_session.invalid_args", false);
        result.status = "invalid_args";
        result.message = "Usage: open [-dbdir <simv.daidir>] [-fsdb <waves.fsdb>] ...";
        return result;
    }
    debug_log("ensure_session: canonical_dbdir=%s", canonical_dbdir.c_str());
    xdebug_core::log_lifecycle_event("design", session_name, "ensure_session.canonicalized", true,
                                     {{"dbdir", canonical_dbdir}});

    if (!SessionRegistry::is_valid_session_name(session_name)) {
        result.status = "invalid_session_id";
        result.message = "Session name is required and must be 1-256 chars using [A-Za-z0-9_.-]";
        debug_log("ensure_session: reason=invalid_session_id name=%s", session_name.c_str());
        xdebug_core::log_lifecycle_event("design", session_name, "ensure_session.invalid_session_id", false);
        return result;
    }
    std::string requested_transport = transport_options.transport.empty() ? default_transport_from_env() : transport_options.transport;
    if (!valid_transport(requested_transport)) {
        result.status = "invalid_transport";
        result.message = "transport must be uds, tcp, or file";
        xdebug_core::log_lifecycle_event("design", session_name, "ensure_session.invalid_transport", false,
                                         {{"transport", requested_transport}});
        return result;
    }

    // Clean up stale sessions first
    debug_log("ensure_session: cleanup_stale_begin");
    xdebug_core::log_lifecycle_event("design", session_name, "cleanup.begin", true);
    cleanup();
    debug_log("ensure_session: cleanup_stale_done");
    xdebug_core::log_lifecycle_event("design", session_name, "cleanup.end", true);

    if (registry_->exists(session_name)) {
        result.status = "session_id_exists";
        result.message = "Session id already exists: " + session_name;
        debug_log("ensure_session: reason=session_id_exists name=%s", session_name.c_str());
        xdebug_core::log_lifecycle_event("design", session_name, "ensure_session.session_id_exists", false);
        return result;
    }

    std::string session_id = session_name;
    if (!xdebug_design_ensure_session_dir(session_id)) {
        result.status = "session_dir_failed";
        result.message = "Failed to create session directory";
        debug_log("ensure_session: reason=session_dir_failed session=%s", session_id.c_str());
        xdebug_core::log_lifecycle_event("design", session_id, "ensure_session.session_dir_failed", false);
        return result;
    }
    debug_log("ensure_session: session_id=%s", session_id.c_str());
    xdebug_core::log_lifecycle_event("design", session_id, "ensure_session.session_dir_ready", true,
                                     {{"session_dir", xdebug_design_session_dir(session_id)}});

    SessionInfo endpoint;
    endpoint.session_id = session_id;
    endpoint.transport = requested_transport;
    endpoint.socket_path = xdebug_design_socket_path(session_id);
    endpoint.file_dir = xdebug_core::file_transport_dir(xdebug_design_session_dir(session_id));
    endpoint.bind_host = transport_options.bind_host.empty()
        ? (endpoint.transport == "tcp" ? "127.0.0.1" : "")
        : transport_options.bind_host;
    endpoint.host = transport_options.host.empty()
        ? (endpoint.bind_host == "0.0.0.0" || endpoint.bind_host == "::" ? current_host_name() : endpoint.bind_host)
        : transport_options.host;
    endpoint.port = endpoint.transport == "tcp" ? transport_options.port : 0;
    endpoint.server_host = current_host_name();
    endpoint.auth_token = endpoint.transport == "tcp" ? generate_auth_token() : "";

    // Spawn server process
    pid_t pid = spawn_server(session_id, canonical_args, endpoint);
    if (pid < 0) {
        result.status = "spawn_failed";
        result.message = "Failed to spawn xdebug_design server";
        xdebug_design_remove_session_dir(session_id);
        debug_log("ensure_session: reason=spawn_failed session=%s", session_id.c_str());
        xdebug_core::log_lifecycle_event("design", session_id, "ensure_session.spawn_failed", false);
        return result;
    }
    debug_log("ensure_session: spawned_server session=%s pid=%d", session_id.c_str(), pid);
    xdebug_core::log_lifecycle_event("design", session_id, "ensure_session.spawned_server", true,
                                     {{"pid", static_cast<int>(pid)}, {"transport", endpoint.transport},
                                      {"socket_path", endpoint.socket_path}, {"host", endpoint.host},
                                      {"port", endpoint.port}});

    // Get socket path
    char sock_path[SOCK_PATH_LEN];
    get_sock_path(sock_path, session_id);
    char dbg_path[SOCK_PATH_LEN];
    get_debug_log_path(dbg_path, session_id);
    debug_log("ensure_session: socket_path=%s debug_log=%s", sock_path, dbg_path);

    WaitForServerResult wait = wait_for_server(session_id, pid);
    if (!wait.ok) {
        // Kill the server process if it didn't start properly
        kill(pid, SIGTERM);
        unlink(sock_path);
        xdebug_design_remove_session_dir(session_id);
        result.status = "startup_failed";
        result.message = "Server did not become ready: " + wait.reason;
        debug_log("ensure_session: reason=%s elapsed_ms=%ld child_exited=%d child_status=%d socket_exists=%d connect_ok=%d ping_ok=%d",
                  wait.reason.c_str(), wait.elapsed_ms, wait.child_exited ? 1 : 0,
                  wait.child_status, wait.socket_exists ? 1 : 0,
                  wait.connect_ok ? 1 : 0, wait.ping_ok ? 1 : 0);
        xdebug_core::log_lifecycle_event("design", session_id, "ensure_session.startup_failed", false,
                                         {{"reason", wait.reason}, {"elapsed_ms", wait.elapsed_ms},
                                          {"child_exited", wait.child_exited}, {"child_status", wait.child_status},
                                          {"socket_exists", wait.socket_exists}, {"connect_ok", wait.connect_ok},
                                          {"ping_ok", wait.ping_ok}});
        return result;
    }

    // Create session info
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
    session.created_at = time(nullptr);
    session.last_active = session.created_at;
    populate_dbdir_metadata(canonical_dbdir, session);

    // Add to registry
    if (!registry_->add(session)) {
        kill(pid, SIGTERM);
        unlink(sock_path);
        xdebug_design_remove_session_dir(session_id);
        result.status = "registry_failed";
        result.message = "Failed to update session registry";
        debug_log("ensure_session: reason=registry_failed session=%s", session_id.c_str());
        xdebug_core::log_lifecycle_event("design", session_id, "ensure_session.registry_failed", false);
        return result;
    }

    result.ok = true;
    result.reused = false;
    result.session_id = session_id;
    result.status = "healthy";
    result.message = "Created healthy session";
    result.info = session;
    debug_log("ensure_session: success session=%s pid=%d socket=%s", session_id.c_str(), pid, sock_path);
    xdebug_core::log_lifecycle_event("design", session_id, "ensure_session.success", true,
                                     {{"pid", static_cast<int>(pid)}, {"socket_path", session.socket_path},
                                      {"dbdir", session.dbdir_path}});
    return result;
}

SessionEnsureResult SessionManager::create_session(const std::vector<std::string>& design_args, const std::string& session_name) {
    return ensure_session(design_args, session_name);
}

SessionEnsureResult SessionManager::create_session(const std::vector<std::string>& design_args,
                                                   const std::string& session_name,
                                                   const SessionTransportOptions& transport) {
    return ensure_session(design_args, session_name, transport);
}

bool SessionManager::kill_session(const std::string& session_id) {
    SessionInfo session;
    if (!registry_->get(session_id, session)) {
        debug_log("kill_session: registry_missing session=%s", session_id.c_str());
        xdebug_core::log_lifecycle_event("design", session_id, "kill_session.registry_missing", false);
        return false;
    }
    debug_log("kill_session: begin session=%s pid=%d socket=%s",
              session.session_id.c_str(), session.server_pid, session.socket_path.c_str());
    xdebug_core::log_lifecycle_event("design", session_id, "kill_session.begin", true,
                                     {{"pid", session.server_pid}, {"socket_path", session.socket_path}});

    if (!send_quit_to_endpoint(session)) {
        if (is_local_session_host(session) && kill(session.server_pid, 0) == 0) {
            kill(session.server_pid, SIGTERM);
        }
        registry_->remove(session_id);
        return true;
    }

    // Give server a brief moment to exit gracefully
    int status;
    usleep(300000);  // 300ms
    if (is_local_session_host(session)) waitpid(session.server_pid, &status, WNOHANG);

    // Force kill if still alive
    if (is_local_session_host(session) && kill(session.server_pid, 0) == 0) {
        kill(session.server_pid, SIGTERM);
    }

    // Remove from registry
    registry_->remove(session_id);
    xdebug_core::log_lifecycle_event("design", session_id, "kill_session.end", true);

    return true;
}

bool SessionManager::kill_all_sessions() {
    std::vector<SessionInfo> sessions = list_sessions();
    xdebug_core::log_lifecycle_event("design", "adhoc", "kill_all.begin", true,
                                     {{"count", sessions.size()}});
    for (const auto& session : sessions) {
        kill_session(session.session_id);
    }
    registry_->clear_all();
    xdebug_core::log_lifecycle_event("design", "adhoc", "kill_all.end", true);
    return true;
}

bool SessionManager::get_session(const std::string& session_id, SessionInfo& info) {
    return registry_->get(session_id, info);
}

bool SessionManager::get_latest_session(SessionInfo& info) {
    return registry_->get_latest(info);
}

bool SessionManager::touch_session(const std::string& session_id) {
    return registry_->touch(session_id, time(nullptr));
}

std::vector<SessionInfo> SessionManager::list_sessions() {
    cleanup();
    std::vector<SessionInfo> sessions;
    registry_->load_all(sessions);
    return sessions;
}

SessionHealth SessionManager::diagnose_session(const std::string& session_id) {
    SessionHealth health;
    health.session_id = session_id;

    SessionInfo session;
    if (!registry_->get(session_id, session)) {
        health.status = SessionHealthStatus::RegistryMissing;
        health.message = "Session is not present in the registry";
        xdebug_core::log_lifecycle_event("design", session_id, "diagnose.registry_missing", false);
        return health;
    }

    health.info = session;

    SessionInfo current;
    if (!current_dbdir_metadata(session, current)) {
        health.status = SessionHealthStatus::DbdirMissing;
        health.message = "Daidir path is missing, is not a directory, or lacks metadata";
        xdebug_core::log_lifecycle_event("design", session_id, "diagnose.dbdir_missing", false,
                                         {{"dbdir", session.dbdir_path}});
        return health;
    }
    if (!dbdir_metadata_matches(session, current)) {
        bool identity_changed = xdebug_core::resource_identity_differs(session.dbdir_dev,
                                                                       session.dbdir_inode,
                                                                       current.dbdir_dev,
                                                                       current.dbdir_inode);
        health.status = SessionHealthStatus::DbdirChanged;
        health.message = "Daidir metadata changed since session was opened";
        xdebug_core::log_lifecycle_event("design", session_id, "diagnose.dbdir_changed", false,
                                         {{"dbdir", session.dbdir_path},
                                          {"old_mtime", session.dbdir_mtime}, {"new_mtime", current.dbdir_mtime},
                                          {"old_size", session.dbdir_size}, {"new_size", current.dbdir_size},
                                          {"old_dev", session.dbdir_dev}, {"new_dev", current.dbdir_dev},
                                          {"old_inode", session.dbdir_inode}, {"new_inode", current.dbdir_inode},
                                          {"identity_changed", identity_changed}});
        return health;
    }
    if (xdebug_core::resource_identity_differs(session.dbdir_dev,
                                               session.dbdir_inode,
                                               current.dbdir_dev,
                                               current.dbdir_inode)) {
        debug_log("diagnose_session: dbdir_identity_changed old_dev=%llu new_dev=%llu old_inode=%llu new_inode=%llu content_match=1",
                  (unsigned long long)session.dbdir_dev,
                  (unsigned long long)current.dbdir_dev,
                  (unsigned long long)session.dbdir_inode,
                  (unsigned long long)current.dbdir_inode);
        xdebug_core::log_lifecycle_event("design", session_id, "diagnose.dbdir_identity_changed", true,
                                         {{"dbdir", session.dbdir_path},
                                          {"old_dev", session.dbdir_dev}, {"new_dev", current.dbdir_dev},
                                          {"old_inode", session.dbdir_inode}, {"new_inode", current.dbdir_inode},
                                          {"content_match", true}, {"identity_changed", true}});
    }

    if (is_local_session_host(session) && kill(session.server_pid, 0) != 0) {
        health.status = SessionHealthStatus::ProcessExited;
        health.message = "Server process is not running";
        xdebug_core::log_lifecycle_event("design", session_id, "diagnose.process_exited", false,
                                         {{"pid", session.server_pid}});
        return health;
    }

    if (!is_tcp_transport(session) && !is_file_transport(session) && access(session.socket_path.c_str(), F_OK) != 0) {
        health.status = SessionHealthStatus::SocketMissing;
        health.message = "Server socket file is missing";
        xdebug_core::log_lifecycle_event("design", session_id, "diagnose.socket_missing", false,
                                         {{"socket_path", session.socket_path}});
        return health;
    }

    if (!is_file_transport(session)) {
    int fd = connect_session_endpoint(session);
    if (fd < 0) {
        health.status = SessionHealthStatus::ConnectFailed;
        health.message = "Server socket exists but cannot be connected";
        xdebug_core::log_lifecycle_event("design", session_id, "diagnose.connect_failed", false,
                                         {{"transport", session.transport}, {"socket_path", session.socket_path},
                                          {"host", session.host}, {"port", session.port}});
        return health;
    }
    close(fd);
    }

    if (!ping_session_endpoint(session)) {
        health.status = SessionHealthStatus::PingFailed;
        health.message = "Server did not respond to PING";
        xdebug_core::log_lifecycle_event("design", session_id, "diagnose.ping_failed", false,
                                         {{"socket_path", session.socket_path}});
        return health;
    }

    health.healthy = true;
    health.status = SessionHealthStatus::Healthy;
    health.message = "Session is healthy";
    xdebug_core::log_lifecycle_event("design", session_id, "diagnose.healthy", true,
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
    debug_log("cleanup: begin");
    xdebug_core::log_lifecycle_event("design", "adhoc", "cleanup.begin", true);
    registry_->cleanup_stale();
    debug_log("cleanup: done");
    xdebug_core::log_lifecycle_event("design", "adhoc", "cleanup.end", true);
}

} // namespace xdebug_design
