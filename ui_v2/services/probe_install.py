from __future__ import annotations

import os
import shlex
import shutil
import subprocess


def _terminal_commands(command: str) -> list[list[str]]:
    return [
        ["x-terminal-emulator", "-e", "bash", "-lc", command],
        ["gnome-terminal", "--", "bash", "-lc", command],
        ["konsole", "-e", "bash", "-lc", command],
        ["xfce4-terminal", "--command", f"bash -lc {shlex.quote(command)}"],
        ["kitty", "bash", "-lc", command],
        ["alacritty", "-e", "bash", "-lc", command],
    ]


def launch_probe_terminal_script(script_path: str) -> str:
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    command = (
        f"cd {shlex.quote(repo_root)} && "
        f"{shlex.quote(script_path)}; "
        "printf '\\nPress Enter to close...'; read -r _"
    )
    for argv in _terminal_commands(command):
        if shutil.which(argv[0]) is None:
            continue
        subprocess.Popen(argv, cwd=repo_root)
        return ""
    return "No supported terminal emulator was found. Run the probe setup scripts from a shell instead."
