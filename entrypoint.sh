#!/bin/bash
set -euo pipefail

DEBUG="${DEBUG:-false}"

if [ "$DEBUG" = "true" ]; then
  set -x
fi

###################
#### Functions ####
###################

check_adc() {
  local adc_path="${GOOGLE_APPLICATION_CREDENTIALS:-${HOME}/.config/gcloud/application_default_credentials.json}"
  if [ ! -f "$adc_path" ]; then
    return 1
  fi
  if command -v gcloud >/dev/null 2>&1 && \
     gcloud auth application-default print-access-token --quiet >/dev/null 2>&1; then
    return 0
  fi
  [ -f "$adc_path" ]
}

detect_provider() {
  if [ -n "${OPENCODIO_PROVIDER:-}" ]; then
    echo "${OPENCODIO_PROVIDER}"
    return
  fi

  if [ -n "${ANTHROPIC_API_KEY:-}" ]; then echo "anthropic"; return; fi
  if [ -n "${OPENAI_API_KEY:-}" ]; then echo "openai"; return; fi
  if [ -n "${GOOGLE_API_KEY:-}" ]; then echo "google"; return; fi
  if check_adc; then echo "vertex"; return; fi
  if [ -n "${OLLAMA_HOST:-}" ]; then echo "ollama"; return; fi
  if [ -n "${OPENCODE_CONFIG_CONTENT:-}" ]; then echo "config"; return; fi

  echo "ERROR: No provider credentials found" >&2
  echo "Set one of:" >&2
  echo "  ANTHROPIC_API_KEY    — Anthropic" >&2
  echo "  OPENAI_API_KEY       — OpenAI" >&2
  echo "  GOOGLE_API_KEY       — Google AI" >&2
  echo "  OLLAMA_HOST          — Ollama (local models)" >&2
  echo "  GOOGLE_APPLICATION_CREDENTIALS — Vertex AI (ADC)" >&2
  echo "Or set OPENCODIO_PROVIDER to force a specific provider." >&2
  exit 1
}

##############
#### Main ####
##############

# Detect provider
PROVIDER=$(detect_provider)
echo "=== Provider: ${PROVIDER} ==="

# Auth — only needed for Vertex AI
if [ "$PROVIDER" = "vertex" ]; then
  ADC_PATH="${GOOGLE_APPLICATION_CREDENTIALS:-${HOME}/.config/gcloud/application_default_credentials.json}"
  if [ ! -f "$ADC_PATH" ]; then
    echo "ERROR: ADC credentials not found at ${ADC_PATH}" >&2
    echo "Mount your credentials or set GOOGLE_APPLICATION_CREDENTIALS." >&2
    exit 1
  fi
fi

# Configure git identity
if [ -n "${GIT_USER_NAME:-}" ]; then
  git config --global user.name "$GIT_USER_NAME"
fi
if [ -n "${GIT_USER_EMAIL:-}" ]; then
  git config --global user.email "$GIT_USER_EMAIL"
fi

# Configure git commit signing
if [ -n "${GIT_SSH_SIGNING_KEY:-}" ]; then
  chmod 600 "$GIT_SSH_SIGNING_KEY"
  git config --global gpg.format ssh
  git config --global user.signingkey "$GIT_SSH_SIGNING_KEY"
  git config --global commit.gpgsign true
fi

# Change to workdir if it exists (for mounted volumes)
if [ -d "$HOME/workdir" ]; then
  cd "$HOME/workdir"
fi

# Generate AGENTS.md from context.d fragments
mkdir -p "${HOME}/.config/opencode"
AGENTS_MD="${HOME}/.config/opencode/AGENTS.md"
: >"$AGENTS_MD"
shopt -s nullglob
for c in ~/.config/opencode/context.d/*.md; do
  cat "$c" >> "$AGENTS_MD" && echo "" >> "$AGENTS_MD"
done
shopt -u nullglob

# Register Ollama provider when OLLAMA_HOST is set
if [ -n "${OLLAMA_HOST:-}" ]; then
  OLLAMA_MODELS=$(curl -s --connect-timeout 5 "${OLLAMA_HOST}/api/tags" 2>/dev/null \
    | python3 -c "import sys,json; models=json.load(sys.stdin).get('models',[]); print(','.join(['\"'+m['name']+'\":{\"tools\":true}' for m in models]))" 2>/dev/null) || OLLAMA_MODELS=""

  if [ -z "$OLLAMA_MODELS" ]; then
    echo "WARNING: Could not discover models from ${OLLAMA_HOST}. Is the Ollama server running?" >&2
  fi

  OPENCODE_CFG="${HOME}/.config/opencode/opencode.json"
  cat > "$OPENCODE_CFG" <<EOCFG
{
  "\$schema": "https://opencode.ai/config.json",
  "provider": {
    "ollama": {
      "npm": "@ai-sdk/openai-compatible",
      "options": {
        "baseURL": "${OLLAMA_HOST}/v1"
      },
      "models": {${OLLAMA_MODELS}}
    }
  }
}
EOCFG
fi

# Parse -p flag for ad-hoc prompts
EXTRA_ARGS=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    -p)
      OPENCODIO_PROMPT="${2:-${OPENCODIO_PROMPT:-}}"
      shift 2
      ;;
    *)
      EXTRA_ARGS+=("$1")
      shift
      ;;
  esac
done
set -- "${EXTRA_ARGS[@]}"

# Build model argument
MODEL_ARGS=()
if [ -n "${OPENCODIO_MODEL:-}" ]; then
  MODEL_ARGS+=(-m "${OPENCODIO_MODEL}")
fi

# --- Non-streaming mode: transparent passthrough ---
if [ "${OPENCODIO_STREAM:-}" != "1" ]; then
  if [ -n "${OPENCODIO_PROMPT:-}" ]; then
    exec opencode run "${MODEL_ARGS[@]}" "$@" "${OPENCODIO_PROMPT}"
  else
    exec opencode "${MODEL_ARGS[@]}" "$@"
  fi
fi

# --- Streaming mode (requires a prompt) ---
export OPENCODE_EXPERIMENTAL=true

if [ -z "${OPENCODIO_PROMPT:-}" ]; then
  echo "ERROR: Streaming mode requires a prompt. Set OPENCODIO_PROMPT or pass -p \"prompt\"" >&2
  exit 1
fi

stream_args=()
[ -n "${OPENCODIO_WRAP:-}" ]  && stream_args+=(--wrap "$OPENCODIO_WRAP")
[ "${NO_COLOR:-}" = "1" ]     && stream_args+=(--no-color)

FIFO_DIR=$(mktemp -d)
FIFO="$FIFO_DIR/stream.fifo"
mkfifo "$FIFO"

opencode run \
    --format json \
    "${MODEL_ARGS[@]}" \
    "$@" "${OPENCODIO_PROMPT}" > "$FIFO" &
opencode_pid=$!

python3 -u /usr/local/bin/stream-opencode.py "${stream_args[@]}" < "$FIFO" &
stream_pid=$!

_on_signal() {
  kill "$opencode_pid" "$stream_pid" 2>/dev/null || true
}

cleanup() {
  rm -rf "$FIFO_DIR"
}

trap '_on_signal; cleanup' TERM INT EXIT

wait "$stream_pid" 2>/dev/null && stream_rc=0 || stream_rc=$?

kill "$opencode_pid" 2>/dev/null || true
wait "$opencode_pid" 2>/dev/null && opencode_rc=0 || opencode_rc=$?

# 143 = SIGTERM (expected when we kill opencode after stream ends)
if [ "$stream_rc" -ne 0 ]; then exit "$stream_rc"; fi
if [ "$opencode_rc" -ne 0 ] && [ "$opencode_rc" -ne 143 ]; then exit "$opencode_rc"; fi

exit 0
