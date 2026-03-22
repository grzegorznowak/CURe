#!/usr/bin/env sh
set -eu

RELEASES_BASE_URL="https://github.com/grzegorznowak/CURe/releases"

usage() {
  cat <<'EOF'
Install the standalone CURe binary from GitHub Releases.

Usage:
  install-cure.sh [--version <tag>] [--bin-dir <dir>]

Options:
  --version <tag>  Install a specific release tag such as v0.1.4.
  --bin-dir <dir>  Install into this directory instead of ~/.local/bin.
  -h, --help       Show this help text.

Environment:
  CURE_INSTALL_BASE_URL  Override the release download base URL for testing.
EOF
}

die() {
  printf '%s\n' "error: $*" >&2
  exit 1
}

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || die "missing required command: $1"
}

resolve_latest_version() {
  need_cmd curl
  tag="$(curl -fsSL https://api.github.com/repos/grzegorznowak/CURe/releases/latest | sed -n 's/.*"tag_name":[[:space:]]*"\([^"]*\)".*/\1/p' | head -n 1)"
  [ -n "$tag" ] || die "failed to resolve the latest CURe release tag"
  printf '%s\n' "$tag"
}

detect_target() {
  os="$(uname -s 2>/dev/null || printf unknown)"
  arch="$(uname -m 2>/dev/null || printf unknown)"
  case "$os:$arch" in
    Linux:x86_64|Linux:amd64)
      printf '%s\n' "linux-x86_64"
      ;;
    Darwin:x86_64)
      printf '%s\n' "macos-x86_64"
      ;;
    Darwin:arm64|Darwin:aarch64)
      printf '%s\n' "macos-arm64"
      ;;
    *)
      die "unsupported platform $os/$arch; use 'uv tool install cureview' on this platform"
      ;;
  esac
}

verify_sha256() {
  file_path="$1"
  sums_path="$2"
  asset_name="$(basename "$file_path")"
  selected_sums_path="$TMP_ROOT/selected.sha256"
  awk -v asset="$asset_name" '
    $2 == asset {
      print
      found = 1
    }
    END {
      if (!found) {
        exit 1
      }
    }
  ' "$sums_path" >"$selected_sums_path" || die "checksum entry for $asset_name not found in $(basename "$sums_path")"
  if command -v sha256sum >/dev/null 2>&1; then
    (cd "$(dirname "$file_path")" && sha256sum -c "$selected_sums_path")
    return
  fi
  if command -v shasum >/dev/null 2>&1; then
    expected="$(awk 'NR==1 { print $1 }' "$selected_sums_path")"
    actual="$(shasum -a 256 "$file_path" | awk '{ print $1 }')"
    [ "$expected" = "$actual" ] || die "checksum verification failed for $(basename "$file_path")"
    return
  fi
  printf '%s\n' "warning: neither sha256sum nor shasum is available; skipping checksum verification" >&2
}

install_binary() {
  archive_path="$1"
  bin_dir="$2"
  tmp_root="$3"

  extract_dir="$tmp_root/extract"
  mkdir -p "$extract_dir" "$bin_dir"
  tar -xzf "$archive_path" -C "$extract_dir"
  [ -f "$extract_dir/cure" ] || die "release archive did not contain the expected cure binary"
  cp "$extract_dir/cure" "$bin_dir/cure"
  chmod 0755 "$bin_dir/cure"
}

VERSION=""
BIN_DIR="${HOME}/.local/bin"
BASE_URL="${CURE_INSTALL_BASE_URL:-}"

while [ $# -gt 0 ]; do
  case "$1" in
    --version)
      [ $# -ge 2 ] || die "--version requires a value"
      VERSION="$2"
      shift 2
      ;;
    --bin-dir)
      [ $# -ge 2 ] || die "--bin-dir requires a value"
      BIN_DIR="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      die "unknown argument: $1"
      ;;
  esac
done

need_cmd curl
need_cmd tar
TARGET_ID="$(detect_target)"
if [ -n "$BASE_URL" ] && [ -z "$VERSION" ]; then
  die "CURE_INSTALL_BASE_URL requires --version so the asset name is deterministic"
fi
if [ -z "$VERSION" ]; then
  VERSION="$(resolve_latest_version)"
fi
if [ -z "$BASE_URL" ]; then
  BASE_URL="$RELEASES_BASE_URL/download/$VERSION"
fi

ASSET_NAME="cureview-$VERSION-$TARGET_ID.tar.gz"
SUMS_NAME="SHA256SUMS"
TMP_ROOT="$(mktemp -d)"
trap 'rm -rf "$TMP_ROOT"' EXIT HUP INT TERM

ARCHIVE_PATH="$TMP_ROOT/$ASSET_NAME"
SUMS_PATH="$TMP_ROOT/$SUMS_NAME"
curl -fsSL "$BASE_URL/$ASSET_NAME" -o "$ARCHIVE_PATH"
curl -fsSL "$BASE_URL/$SUMS_NAME" -o "$SUMS_PATH"
verify_sha256 "$ARCHIVE_PATH" "$SUMS_PATH"
install_binary "$ARCHIVE_PATH" "$BIN_DIR" "$TMP_ROOT"

printf '%s\n' "Installed cure to $BIN_DIR/cure"
case ":${PATH:-}:" in
  *:"$BIN_DIR":*)
    ;;
  *)
    printf '%s\n' "Add $BIN_DIR to PATH if you want to run cure without an absolute path."
    ;;
esac
