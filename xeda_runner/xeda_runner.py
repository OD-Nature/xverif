#!/usr/bin/env python3
"""xeda-runner — 带环境快照缓存的阻塞式 allowlist command runner.

纯 Python 标准库，零 pip 依赖。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Optional

# ---------------------------------------------------------------------------
# config
# ---------------------------------------------------------------------------


def find_config() -> str:
    """Find config file in current directory."""
    path = os.path.join(os.getcwd(), ".xeda-runner.json")
    if os.path.isfile(path):
        return path
    return ".xeda-runner.json"


def load_config(path: str) -> dict[str, Any]:
    with open(path, "r") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# env snapshot
# ---------------------------------------------------------------------------


def env0_path(cfg: dict[str, Any], workdir: str) -> Path:
    return Path(workdir) / cfg["env_snapshot"]


def load_env0(path: str) -> dict[str, str]:
    data = Path(path).read_bytes()
    env: dict[str, str] = {}
    for item in data.split(b"\0"):
        if not item:
            continue
        if b"=" not in item:
            continue
        key, value = item.split(b"=", 1)
        env[key.decode()] = value.decode(errors="surrogateescape")
    return env


def _shebang(shell: str) -> str:
    return {"tcsh": "#!/bin/tcsh -f",
            "bash": "#!/bin/bash --login",
            "zsh": "#!/usr/bin/env zsh"}[shell]


def _shell_cmd(shell: str) -> str:
    return {"tcsh": "tcsh", "bash": "bash", "zsh": "zsh"}[shell]


def generate_init_script(cfg: dict[str, Any]) -> str:
    """Generate a shell script from init_steps + auto postamble."""
    shell = cfg["shell"]
    workdir = cfg["workdir"]
    snapshot = env0_path(cfg, workdir)
    checks = cfg.get("checks", [])

    lines: list[str] = [_shebang(shell), ""]

    # user-defined init steps
    for step in cfg.get("init_steps", []):
        lines.append(step)

    # auto postamble: checks
    if checks:
        lines.append("")
        lines.append('echo "[xeda-runner] checks"')
        for tool in checks:
            lines.append(f"which {tool}")

    # auto postamble: env dump + timestamp
    lines.append("")
    lines.append(f"/usr/bin/env -0 > {snapshot}")
    timestamp_file = Path(workdir) / ".xeda_runner" / "timestamp"
    lines.append(f"date +%s > {timestamp_file}")
    lines.append("exit 0")

    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# init
# ---------------------------------------------------------------------------


def cmd_init(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    workdir = cfg["workdir"]
    shell = cfg["shell"]

    snapshot = env0_path(cfg, workdir)
    if snapshot.exists() and not args.refresh:
        print(f"[xeda-runner] env snapshot already exists: {snapshot}",
              file=sys.stderr)
        print("[xeda-runner] use --refresh to re-initialize", file=sys.stderr)
        return 0

    snapshot.parent.mkdir(parents=True, exist_ok=True)
    init_log = snapshot.parent / "init.log"
    timestamp_file = snapshot.parent / "timestamp"

    script = generate_init_script(cfg)

    with tempfile.NamedTemporaryFile("w", suffix=f".{shell}", delete=False) as f:
        f.write(script)
        script_path = f.name

    # If custom config path was used, the script's relative paths (cd workdir)
    # must work from wherever we are — the script runs from the current dir.
    cwd = os.getcwd()

    try:
        with open(init_log, "w") as log:
            log.write(f"# xeda-runner init log — {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            log.write(f"# shell: {shell}\n")
            log.write(f"# workdir: {workdir}\n")
            log.write(f"# script:\n{script}\n")
            log.write(f"{'='*60}\n\n")

            result = subprocess.run(
                [_shell_cmd(shell), script_path],
                cwd=cwd,
                stdout=log,
                stderr=subprocess.STDOUT,
            )

        if result.returncode != 0:
            print(f"[xeda-runner] init failed (exit {result.returncode})",
                  file=sys.stderr)
            print(f"[xeda-runner] see log: {init_log}", file=sys.stderr)
            return result.returncode

        # write summary.json
        summary: dict[str, Any] = {
            "shell": shell,
            "workdir": workdir,
            "snapshot": str(snapshot),
            "timestamp": int(time.time()),
            "checks": {},
        }
        if snapshot.exists():
            summary["snapshot_size"] = snapshot.stat().st_size
        summary_path = snapshot.parent / "summary.json"
        summary_path.write_text(json.dumps(summary, indent=2))

        print(f"[xeda-runner] init complete — {snapshot}", file=sys.stderr)
        return 0
    finally:
        os.unlink(script_path)


# ---------------------------------------------------------------------------
# env-info
# ---------------------------------------------------------------------------


def cmd_env_info(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    workdir = cfg["workdir"]
    snapshot = env0_path(cfg, workdir)
    summary_path = snapshot.parent / "summary.json"

    info: dict[str, Any] = {
        "shell": cfg["shell"],
        "workdir": workdir,
        "snapshot": str(snapshot),
        "initialized": snapshot.exists(),
    }

    if summary_path.exists():
        info.update(json.loads(summary_path.read_text()))

    if snapshot.exists():
        info["snapshot_size"] = snapshot.stat().st_size

    print(json.dumps(info, indent=2))
    return 0


# ---------------------------------------------------------------------------
# list-actions
# ---------------------------------------------------------------------------


def cmd_list_actions(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    actions = list(cfg.get("actions", {}).keys())
    print(json.dumps({"actions": actions}, indent=2))
    return 0


# ---------------------------------------------------------------------------
# describe-action
# ---------------------------------------------------------------------------


def cmd_describe_action(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    actions = cfg.get("actions", {})
    if args.action not in actions:
        print(f"[xeda-runner] action not found: {args.action}", file=sys.stderr)
        return 2

    action_cfg = dict(actions[args.action])
    action_cfg.pop("command", None)
    action_cfg.pop("fixed_args", None)
    print(json.dumps({"action": args.action, **action_cfg}, indent=2))
    return 0


# ---------------------------------------------------------------------------
# option parsing & validation
# ---------------------------------------------------------------------------


def parse_options(option_list: list[str] | None) -> dict[str, str]:
    opts: dict[str, str] = {}
    for item in option_list or []:
        if "=" not in item:
            raise ValueError(
                f"invalid option format, expected KEY=VALUE: {item}")
        k, v = item.split("=", 1)
        opts[k] = v
    return opts


def validate_value(name: str, value: str, spec: dict[str, Any]) -> None:
    if "values" in spec:
        if value not in spec["values"]:
            raise ValueError(
                f"invalid value for {name}: {value}, "
                f"allowed={spec['values']}")
    if "pattern" in spec:
        if not re.fullmatch(spec["pattern"], value):
            raise ValueError(
                f"invalid value for {name}: {value}, "
                f"pattern={spec['pattern']}")


# ---------------------------------------------------------------------------
# argv builder
# ---------------------------------------------------------------------------


def build_argv(action_cfg: dict[str, Any], target: str | None,
               options: dict[str, str]) -> list[str]:
    argv: list[str] = [action_cfg["command"]]
    argv.extend(action_cfg.get("fixed_args", []))

    # target
    target_cfg = action_cfg.get("target", {"required": False})
    if target_cfg.get("required") and not target:
        raise ValueError("target is required")
    if target:
        allowed = target_cfg.get("allowed")
        if allowed and target not in allowed:
            raise ValueError(
                f"target not allowed: {target}, allowed={allowed}")
        argv.append(target)

    # options
    option_specs = action_cfg.get("options", {})
    for name, value in options.items():
        if name not in option_specs:
            raise ValueError(f"option not allowed: {name}")
        spec = option_specs[name]
        validate_value(name, value, spec)
        emit = spec["emit"]

        if emit == "make_var":
            argv.append(f"{name}={value}")
        elif emit == "separate":
            argv.extend([spec["key"], value])
        elif emit == "equals":
            argv.append(f"{spec['key']}={value}")
        elif emit == "flag":
            if value not in ("1", "true", "True", "yes", "on"):
                continue
            argv.append(spec["key"])
        elif emit == "positional":
            argv.append(value)
        else:
            raise ValueError(f"unsupported emit type: {emit}")

    return argv


# ---------------------------------------------------------------------------
# run
# ---------------------------------------------------------------------------


def cmd_run(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    workdir = cfg["workdir"]
    snapshot = env0_path(cfg, workdir)

    if not snapshot.exists():
        print(
            f"[xeda-runner] env snapshot not found: {snapshot}\n"
            f"[xeda-runner] run: xeda-runner init",
            file=sys.stderr,
        )
        return 2

    actions = cfg.get("actions", {})
    if args.action not in actions:
        print(f"[xeda-runner] action not found: {args.action}",
              file=sys.stderr)
        return 2

    action_cfg = actions[args.action]
    options = parse_options(args.option)
    argv = build_argv(action_cfg, args.target, options)

    if args.dry_run:
        print(f"[xeda-runner] DRY-RUN cwd={workdir}", file=sys.stderr)
        print(f"[xeda-runner] DRY-RUN argv={argv}", file=sys.stderr)
        return 0

    env = load_env0(str(snapshot))

    if not args.quiet:
        print(f"[xeda-runner] action={args.action} "
              f"target={args.target or ''}",
              file=sys.stderr)
        print(f"[xeda-runner] cwd={workdir}", file=sys.stderr)
        print(f"[xeda-runner] argv={' '.join(argv)}", file=sys.stderr)

    result = subprocess.run(argv, cwd=workdir, env=env)
    return result.returncode


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    default_config = find_config()

    parser = argparse.ArgumentParser(
        prog="xeda-runner",
        description="带环境快照缓存的阻塞式 allowlist command runner",
    )
    parser.add_argument("--config", default=default_config,
                        help=f"配置文件路径 (默认: {default_config})")
    sub = parser.add_subparsers(dest="cmd")

    # init
    p_init = sub.add_parser("init", help="初始化环境快照")
    p_init.add_argument("--refresh", action="store_true",
                        help="强制重新初始化")

    # env-info
    sub.add_parser("env-info", help="查看环境快照状态")

    # list-actions
    sub.add_parser("list-actions", help="列出可用 action")

    # describe-action
    p_desc = sub.add_parser("describe-action", help="查看 action 详情")
    p_desc.add_argument("--action", required=True, help="action 名称")

    # run
    p_run = sub.add_parser("run", help="阻塞执行 action")
    p_run.add_argument("--action", required=True, help="action 名称")
    p_run.add_argument("--target", help="target 值")
    p_run.add_argument("--option", action="append", default=[],
                       help="option KEY=VALUE (可多次使用)")
    p_run.add_argument("--quiet", action="store_true",
                       help="抑制 runner header 输出")
    p_run.add_argument("--dry-run", action="store_true",
                       help="仅打印 argv，不执行")

    args = parser.parse_args(argv)

    if not args.cmd:
        parser.print_help()
        return 0

    try:
        if args.cmd == "init":
            return cmd_init(args)
        elif args.cmd == "env-info":
            return cmd_env_info(args)
        elif args.cmd == "list-actions":
            return cmd_list_actions(args)
        elif args.cmd == "describe-action":
            return cmd_describe_action(args)
        elif args.cmd == "run":
            return cmd_run(args)
        else:
            parser.print_help()
            return 2
    except Exception as e:
        print(f"[xeda-runner] error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
