"""Fake host commands for the deploy kit's build-environment script.

Each records `name|arguments|working directory` in $TEST_LOG. The fake
systemd-run applies the unit's UMask= like systemd, drops its other options,
and runs the unit's command directly, so the build's real shell command runs
against the test's fake interpreter whatever the caller's umask is.
"""

TOOLS = {
    "id": 'printf "%s\\n" "${TEST_UID:-0}"',
    "install": '[ "$*" = "-d -o news -g news -m 0755 $8" ] || exit 64\nmkdir -m 0755 "$8"',
    "systemd-run": 'while [ "${1#--}" != "$1" ]; do\n'
                   '    case "$1" in --property=UMask=*) umask "${1#--property=UMask=}" ;; esac\n'
                   '    shift\n'
                   'done\n'
                   '[ "$TEST_FAIL" != unit ] || exit 1\nexec "$@"',
    "chown": ":",
}


def install_host_tools(directory):
    for name, body in TOOLS.items():
        path = directory / name
        path.write_text(
            '#!/bin/sh\nprintf "%s|%s|%s\\n" "' + name + '" "$*" "$PWD" >> "$TEST_LOG"\n' + body + "\n"
        )
        path.chmod(0o755)
