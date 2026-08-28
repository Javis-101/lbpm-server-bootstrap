#!/usr/bin/env bash

validate_install_root() {
  local target="${1:-}"

  [[ -n "$target" ]] || {
    printf 'Install root must not be empty\n' >&2
    return 1
  }
  [[ "$target" == /* ]] || {
    printf 'Install root must be an absolute path: %s\n' "$target" >&2
    return 1
  }
  [[ "$target" != "/" ]] || {
    printf 'Install root must not be /\n' >&2
    return 1
  }
  [[ ! "$target" =~ (^|/)\.\.?(/|$) ]] || {
    printf 'Install root must not contain . or .. path segments: %s\n' "$target" >&2
    return 1
  }
}
