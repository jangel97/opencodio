# opencodio

Containerized [OpenCode](https://opencode.ai/) for CI/CD pipelines. Multi-provider, multi-arch OCI image that brings AI coding assistance to GitLab CI, Tekton, and local development.

## Features

- **Multi-provider** — Anthropic, OpenAI, Google AI, Vertex AI, and any OpenAI-compatible endpoint (Ollama, vLLM, TGI, etc.)
- **Multi-arch** — amd64 and arm64
- **Streaming output** — Human-readable CI logs with token accounting
- **Distroless** — Built on Red Hat Hardened Images (~340MB vs ~860MB)

## Execution Modes

| Mode | When to use | How |
|------|-------------|-----|
| **Interactive TUI** | Local development — explore code, iterate on changes | Omit `OPENCODIO_PROMPT`, run with `-it` |
| **Non-streaming** | Scripts, simple automation — run a prompt, get the output | Set `OPENCODIO_PROMPT` (or `-p`), no `OPENCODIO_STREAM` |
| **Streaming** | CI/CD pipelines — human-readable logs with token stats | Set `OPENCODIO_STREAM=1` and `OPENCODIO_PROMPT` |

## Quick Start

### Interactive TUI

Launch the full OpenCode TUI for interactive use. Omit `OPENCODIO_PROMPT` and pass `-it`:

```bash
podman run --rm -it \
  -v "${PWD}:/home/opencodio/workdir" \
  -e ANTHROPIC_API_KEY=sk-ant-... \
  quay.io/jangel97/opencodio:latest
```

### Ad-hoc prompt

Run a single prompt and exit:

```bash
podman run --rm \
  -v "${PWD}:/home/opencodio/workdir" \
  -e ANTHROPIC_API_KEY=sk-ant-... \
  -e OPENCODIO_PROMPT="Explain the architecture of this project" \
  quay.io/jangel97/opencodio:latest
```

You can also pass the prompt via the `-p` flag:

```bash
podman run --rm \
  -v "${PWD}:/home/opencodio/workdir" \
  -e ANTHROPIC_API_KEY=sk-ant-... \
  quay.io/jangel97/opencodio:latest \
  -p "Explain the main function"
```

### Vertex AI (Google Cloud)

```bash
podman run --rm -it \
  -v "${PWD}:/home/opencodio/workdir" \
  -v "${HOME}/.config/gcloud/application_default_credentials.json:/home/opencodio/.config/gcloud/application_default_credentials.json:ro" \
  -e GOOGLE_CLOUD_PROJECT=my-gcp-project \
  -e GOOGLE_CLOUD_LOCATION=global \
  -e OPENCODIO_MODEL=google-vertex-anthropic/claude-sonnet-4-6@default \
  quay.io/jangel97/opencodio:latest
```

### OpenAI-compatible endpoint (Ollama, vLLM, TGI, etc.)

```bash
podman run --rm -it \
  -v "${PWD}:/home/opencodio/workdir" \
  -e OPENCODIO_OPENAI_COMPATIBLE_ENDPOINT=http://192.168.1.138:11434/v1 \
  -e OPENCODIO_CUSTOM_PROVIDER_NAME=ollama \
  -e OPENCODIO_MODEL=ollama/qwen3:14b-16k \
  quay.io/jangel97/opencodio:latest
```

The endpoint URL must include the `/v1` prefix. Models are auto-discovered via the `/v1/models` endpoint.

### Custom config

Pass a raw `opencode.json` config via environment variable:

```bash
podman run --rm -it \
  -v "${PWD}:/home/opencodio/workdir" \
  -e OPENCODE_CONFIG_CONTENT='{"$schema":"https://opencode.ai/config.json","provider":{...}}' \
  quay.io/jangel97/opencodio:latest
```

## Ollama Setup

Ollama defaults all models to a 4,096-token context window, which is too small for agentic tool use (file editing, bash execution). You must create a custom model variant with an extended context window.

### 1. Extend context window

On your Ollama server:

```bash
ollama run qwen3:14b
/set parameter num_ctx 16384
/save qwen3:14b-16k
/show parameters
```

Verify with:

```bash
curl -s http://<ollama-host>:11434/api/show -d '{"name":"qwen3:14b-16k"}' | python3 -c "import sys,json; print(json.load(sys.stdin).get('parameters',''))"
```

You should see `num_ctx 16384` in the output.

### 2. Recommended models

Not all models support tool calling. Models must have native function calling support for OpenCode to execute tools (read files, run commands, edit code).

| Model | Tool Use | Notes |
|-------|----------|-------|
| `qwen3:14b` | Yes | Best balance of quality and speed |
| `qwen3:8b` | Yes | Good for 8GB VRAM |

Tool support is disabled by default for discovered models. Set `OPENCODIO_ENABLE_TOOLS=true` to enable it.

### 3. Run

```bash
podman run --rm -it \
  -v "${PWD}:/home/opencodio/workdir" \
  -e OPENCODIO_OPENAI_COMPATIBLE_ENDPOINT=http://192.168.1.138:11434/v1 \
  -e OPENCODIO_CUSTOM_PROVIDER_NAME=ollama \
  -e OPENCODIO_MODEL=ollama/qwen3:14b-16k \
  -e OPENCODIO_ENABLE_TOOLS=true \
  quay.io/jangel97/opencodio:latest
```

## CI/CD Streaming Mode

Streaming mode (`OPENCODIO_STREAM=1`) pipes OpenCode's JSON event stream through a formatter that produces human-readable CI logs with tool call summaries and token accounting. Ideal for GitLab CI, Tekton, and other pipeline runners.

```bash
podman run --rm \
  -v "${PWD}:/home/opencodio/workdir" \
  -v "${HOME}/.config/gcloud/application_default_credentials.json:/home/opencodio/.config/gcloud/application_default_credentials.json:ro" \
  -e GOOGLE_CLOUD_PROJECT=my-gcp-project \
  -e GOOGLE_CLOUD_LOCATION=global \
  -e OPENCODIO_MODEL=google-vertex-anthropic/claude-sonnet-4-6@default \
  -e OPENCODIO_STREAM=1 \
  -e OPENCODIO_PROMPT="Review the code changes and suggest improvements" \
  quay.io/jangel97/opencodio:latest
```

### GitLab CI example

```yaml
ai-review:
  image: quay.io/jangel97/opencodio:latest
  variables:
    GOOGLE_CLOUD_PROJECT: "my-gcp-project"
    GOOGLE_CLOUD_LOCATION: "global"
    OPENCODIO_MODEL: "google-vertex-anthropic/claude-sonnet-4-6@default"
    OPENCODIO_STREAM: "1"
    OPENCODIO_PROMPT: "Review the latest commit and identify potential issues"
```

## Build

```bash
podman build -t opencodio:latest .
```

The image currently uses a [patched OpenCode binary](https://github.com/anomalyco/opencode/issues/31435) from the [jangel97/opencode](https://github.com/jangel97/opencode) fork that fixes a JSON streaming race condition. The binary lives at `cli/opencode-patched` and is copied into the image at build time.

To build without gcloud SDK (smaller image):

```bash
podman build --build-arg ENABLE_GCLOUD=0 -t opencodio:latest .
```

## Provider Configuration

opencodio auto-detects your provider from available credentials (checked in this order):

| Provider | Credential | Example |
|----------|-----------|---------|
| Anthropic | `ANTHROPIC_API_KEY` | `sk-ant-...` |
| OpenAI | `OPENAI_API_KEY` | `sk-...` |
| Google AI | `GOOGLE_API_KEY` | `AI...` |
| Vertex AI | ADC JSON + `GOOGLE_CLOUD_PROJECT` | Mount ADC, set project and location |
| OpenAI-compatible | `OPENCODIO_OPENAI_COMPATIBLE_ENDPOINT` | `http://host:11434/v1` |
| Raw config | `OPENCODE_CONFIG_CONTENT` | JSON string |

Override auto-detection with `OPENCODIO_PROVIDER` or specify a model directly with `OPENCODIO_MODEL`.

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `OPENCODIO_PROMPT` | Task prompt (required in streaming mode). Without it, launches interactive TUI | — |
| `OPENCODIO_STREAM` | Enable streaming mode (`1`) | disabled |
| `OPENCODIO_MODEL` | Model override (e.g., `ollama/qwen3:14b-16k`) | auto |
| `OPENCODIO_OPENAI_COMPATIBLE_ENDPOINT` | OpenAI-compatible endpoint URL (must include `/v1`) | — |
| `OPENCODIO_PROVIDER` | Force provider detection (e.g., `anthropic`, `vertex`, `custom`) | auto |
| `OPENCODIO_CUSTOM_PROVIDER_NAME` | Provider name registered in OpenCode config for custom endpoints | `custom` |
| `OPENCODIO_API_KEY` | API key for custom endpoints | — |
| `OPENCODIO_ENABLE_TOOLS` | Enable tool support for discovered models (`true`) | `false` |
| `OPENCODIO_WRAP` | Word wrap at N columns | — |
| `OPENCODE_CONFIG_CONTENT` | Raw `opencode.json` content (written to config on startup) | — |
| `GOOGLE_CLOUD_PROJECT` | GCP project ID for Vertex AI | from ADC |
| `GOOGLE_CLOUD_LOCATION` | GCP region for Vertex AI | `global` |
| `GIT_USER_NAME` | Git user name for commits | — |
| `GIT_USER_EMAIL` | Git user email for commits | — |
| `GIT_SSH_SIGNING_KEY` | Path to SSH key for commit signing | — |
