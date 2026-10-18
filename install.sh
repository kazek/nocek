#!/bin/sh
# Install Nocek, or update it, on macOS or Linux:
#
#   curl -LsSf https://raw.githubusercontent.com/kazek/nocek/main/install.sh | sh
#
# Installs uv if it is missing (it brings the Python Nocek needs), then Nocek with the
# build of PyTorch that suits this computer, puts Nocek in the system's menu and starts it.
# For testing: NOCEK_PACKAGE installs something else in Nocek's place, such as a wheel;
# NOCEK_NO_START leaves Nocek unstarted.
set -eu

package="${NOCEK_PACKAGE:-nocek}"

say() {
  printf '\n\033[1m%s\033[0m\n' "$*"
}

# Where uv's installer puts it; a terminal opened before then does not know of it yet.
installed="${UV_INSTALL_DIR:-${XDG_BIN_HOME:-$HOME/.local/bin}}/uv"
if command -v uv >/dev/null 2>&1; then
  uv=$(command -v uv)
elif [ -x "$installed" ]; then
  uv=$installed
else
  say "Installing uv, which installs Nocek and the Python it needs"
  curl -LsSf https://astral.sh/uv/install.sh | sh
  uv=$installed
  if [ ! -x "$uv" ]; then
    echo "uv was installed, but not where expected; open a new terminal and run this again." >&2
    exit 1
  fi
fi

say "Installing Nocek (the first time this downloads about 1 GB)"
"$uv" tool install --upgrade --python 3.13 --torch-backend auto "$package"
# Lets new terminals find `nocek`.
"$uv" tool update-shell >/dev/null 2>&1 || true

nocek="$("$uv" tool dir --bin)/nocek"
"$nocek" shortcut

if [ -z "${NOCEK_NO_START:-}" ]; then
  say "Starting Nocek; it opens in your browser"
  nohup "$nocek" >/dev/null 2>&1 &
fi

say "Done. Start Nocek from your applications menu from now on."
echo "If an older Nocek was running, quit it (Quit, top right) and start it again."
