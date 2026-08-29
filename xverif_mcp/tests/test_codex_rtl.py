from pathlib import Path
import os
import subprocess


ROOT = Path(__file__).resolve().parents[2]


def test_codex_rtl_injects_xverif_only_for_wrapped_process(tmp_path: Path) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_codex = fake_bin / "codex"
    fake_codex.write_text('#!/usr/bin/env bash\nprintf "%s\\n" "$@"\n', encoding="utf-8")
    fake_codex.chmod(0o755)
    env = dict(os.environ)
    env["PATH"] = f"{fake_bin}:{env.get('PATH', '')}"

    result = subprocess.run(
        [str(ROOT / "tools/codex-rtl"), "-C", "/tmp/rtl-project"],
        check=True,
        text=True,
        capture_output=True,
        env=env,
    )

    args = result.stdout.splitlines()
    assert "mcp_servers.xverif.command=" in args[1]
    assert args[1].endswith("/tools/xverif-mcp-auto'")
    assert args[-2:] == ["-C", "/tmp/rtl-project"]
