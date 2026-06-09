# opencodio

Containerized [OpenCode](https://opencode.ai/) for CI/CD pipelines. Multi-provider, multi-arch OCI image that brings AI coding assistance to GitLab CI, Tekton, and local development.

## Features

- **Multi-provider** — Anthropic, OpenAI, Google AI, Vertex AI, Ollama (local models)
- **Multi-arch** — amd64 and arm64
- **Streaming output** — Human-readable CI logs with token accounting
- **Local wrapper** — `cli/opencodio` for interactive use via podman

## Quick Start

### Vertex AI (Google Cloud)

```bash
podman run --rm -it \
  --name opencodio \
  -v "${PWD}:/home/opencodio/workdir" \
  -v "${HOME}/.config/gcloud:/home/opencodio/.config/gcloud" \
  -e GOOGLE_APPLICATION_CREDENTIALS="/home/opencodio/.config/gcloud/application_default_credentials.json" \
  -e GOOGLE_VERTEX_PROJECT="my-gcp-project" \
  -e GOOGLE_VERTEX_LOCATION="global" \
  -e OPENCODIO_MODEL=google-vertex-anthropic/claude-sonnet-4-6@default \
  quay.io/jangel97/opencodio:v0.0.1
```

### OpenAI-compatible endpoint (Ollama, vLLM, TGI, etc.)

```bash
podman run --rm -it \
  --name opencodio \
  -v "${PWD}:/home/opencodio/workdir" \
  -e OPENCODIO_OPENAI_COMPATIBLE_ENDPOINT=http://192.168.1.138:11434/v1 \
  -e OPENCODIO_PROVIDER=ollama \
  -e OPENCODIO_MODEL=ollama/qwen3:14b-16k \
  quay.io/jangel97/opencodio:v0.0.1
```

### Anthropic API

```bash
podman run --rm -it \
  --name opencodio \
  -v "${PWD}:/home/opencodio/workdir" \
  -e ANTHROPIC_API_KEY=sk-ant-... \
  quay.io/jangel97/opencodio:v0.0.1
```


### Ad-hoc prompt

Run a single prompt without entering the TUI:

```bash
podman run --rm -it \
  --name opencodio \
  -v "${PWD}:/home/opencodio/workdir" \
  -v "${HOME}/.config/gcloud:/home/opencodio/.config/gcloud" \
  -e GOOGLE_APPLICATION_CREDENTIALS="/home/opencodio/.config/gcloud/application_default_credentials.json" \
  -e GOOGLE_VERTEX_PROJECT="my-gcp-project" \
  -e GOOGLE_VERTEX_LOCATION="global" \
  -e OPENCODIO_MODEL=google-vertex-anthropic/claude-sonnet-4-6@default \
  quay.io/jangel97/opencodio:v0.0.1 \
  -p "Explain the main function in this project"
```

The `-p` flag sends the prompt directly and exits when done. Without `-p`, opencodio launches the interactive TUI.

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


### 3. Run

```bash
podman run --rm -it \
  --name opencodio \
  -v "${PWD}:/home/opencodio/workdir" \
  -e OPENCODIO_OPENAI_COMPATIBLE_ENDPOINT=http://192.168.1.138:11434/v1 \
  -e OPENCODIO_PROVIDER=ollama \
  -e OPENCODIO_MODEL=ollama/qwen3:14b-16k \
  quay.io/jangel97/opencodio:v0.0.1
```

The entrypoint auto-discovers all models from the `/v1/models` endpoint and registers them with tool support enabled.

## CI/CD Streaming Mode

Streaming mode (`OPENCODIO_STREAM=1`) pipes OpenCode's JSON event stream through a formatter that produces human-readable CI logs with tool call summaries and token accounting. Ideal for GitLab CI, Tekton, and other pipeline runners.

```bash
podman run --rm \
  -v "${PWD}:/home/opencodio/workdir" \
  -v "${HOME}/.config/gcloud:/home/opencodio/.config/gcloud" \
  -e GOOGLE_APPLICATION_CREDENTIALS="/home/opencodio/.config/gcloud/application_default_credentials.json" \
  -e GOOGLE_VERTEX_PROJECT="myproject" \
  -e GOOGLE_VERTEX_LOCATION="global" \
  -e OPENCODIO_MODEL=google-vertex-anthropic/claude-sonnet-4-6@default \
  -e OPENCODIO_STREAM=1 \
  -e OPENCODIO_PROMPT="Review the code changes and suggest improvements" \
  quay.io/jangel97/opencodio:v0.0.1
```

### GitLab CI example

```yaml
ai-review:
  image: quay.io/jangel97/opencodio:v0.0.1
  variables:
    GOOGLE_VERTEX_PROJECT: "my-gcp-project"
    GOOGLE_VERTEX_LOCATION: "global"
    OPENCODIO_MODEL: "google-vertex-anthropic/claude-sonnet-4-6@default"
    OPENCODIO_STREAM: "1"
    OPENCODIO_PROMPT: "Review the latest commit and identify potential issues"
  script:
    - entrypoint.sh
```

## Build

```bash
podman build -t quay.io/jangel97/opencodio:v0.0.1 .
```

The image currently uses a [patched OpenCode binary](https://github.com/anomalyco/opencode/issues/31435) from the [jangel97/opencode](https://github.com/jangel97/opencode) fork that fixes a JSON streaming race condition. The binary lives at `cli/opencode-patched` and is copied into the image at build time.

To build without gcloud SDK (smaller image):

```bash
podman build --build-arg ENABLE_GCLOUD=0 -t quay.io/jangel97/opencodio:v0.0.1 .
```

If preferred you can just use `quay.io/jangel97/opencodio:v0.0.1`.

## Provider Configuration

opencodio auto-detects your provider from available credentials:

| Provider | Credential | Example |
|----------|-----------|---------|
| Anthropic | `ANTHROPIC_API_KEY` | `sk-ant-...` |
| OpenAI | `OPENAI_API_KEY` | `sk-...` |
| Google AI | `GOOGLE_API_KEY` | `AI...` |
| Vertex AI | `GOOGLE_APPLICATION_CREDENTIALS` | Path to ADC JSON |
| Ollama / vLLM / TGI | `OPENCODIO_OPENAI_COMPATIBLE_ENDPOINT` | `http://host:11434/v1` |

Override auto-detection with `OPENCODIO_PROVIDER` or specify a model directly with `OPENCODIO_MODEL`.

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `OPENCODIO_PROMPT` | Task prompt (required in streaming mode) | — |
| `OPENCODIO_STREAM` | Enable streaming mode (`1`) | `""` (disabled) |
| `OPENCODIO_MODEL` | Model override (e.g., `ollama/qwen3:14b-16k`) | auto |
| `OPENCODIO_OPENAI_COMPATIBLE_ENDPOINT` | OpenAI-compatible endpoint URL | — |
| `OPENCODIO_PROVIDER` | Provider name for custom endpoints (e.g., `ollama`, `vllm`) | `custom` |
| `OPENCODIO_API_KEY` | API key for custom endpoints | — |
| `OPENCODIO_WRAP` | Word wrap at N columns | — |
| `DEBUG` | Enable bash debug output | `false` |
