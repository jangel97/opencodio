#!/usr/bin/env python3
"""opencodio entrypoint — provider detection, config generation, and process management."""

import json
import os
import signal
import subprocess
import sys
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen

HOME = os.environ.get("HOME", "/home/opencodio")


def log(msg, file=sys.stderr):
    print(msg, file=file, flush=True)


def check_adc():
    adc_path = os.environ.get(
        "GOOGLE_APPLICATION_CREDENTIALS",
        os.path.join(HOME, ".config/gcloud/application_default_credentials.json"),
    )
    return os.path.isfile(adc_path)


def detect_provider():
    forced = os.environ.get("OPENCODIO_PROVIDER")
    if forced:
        return forced

    if os.environ.get("ANTHROPIC_API_KEY"):
        return "anthropic"
    if os.environ.get("OPENAI_API_KEY"):
        return "openai"
    if os.environ.get("GOOGLE_API_KEY"):
        return "google"
    if check_adc():
        return "vertex"
    if os.environ.get("OPENCODIO_OPENAI_COMPATIBLE_ENDPOINT"):
        return "custom"
    if os.environ.get("OPENCODE_CONFIG_CONTENT"):
        return "config"

    log("ERROR: No provider credentials found")
    log("Set one of:")
    log("  ANTHROPIC_API_KEY    — Anthropic")
    log("  OPENAI_API_KEY       — OpenAI")
    log("  GOOGLE_API_KEY       — Google AI")
    log("  OPENCODIO_OPENAI_COMPATIBLE_ENDPOINT — Any OpenAI-compatible endpoint (Ollama, vLLM, TGI, etc.)")
    log("  GOOGLE_APPLICATION_CREDENTIALS — Vertex AI (ADC)")
    log("  OPENCODE_CONFIG_CONTENT — Raw opencode.json content")
    log("Or set OPENCODIO_PROVIDER to force a specific provider.")
    sys.exit(1)


def configure_git():
    name = os.environ.get("GIT_USER_NAME")
    email = os.environ.get("GIT_USER_EMAIL")
    signing_key = os.environ.get("GIT_SSH_SIGNING_KEY")

    if name:
        subprocess.run(["git", "config", "--global", "user.name", name], check=False)
    if email:
        subprocess.run(["git", "config", "--global", "user.email", email], check=False)
    if signing_key and os.path.isfile(signing_key):
        os.chmod(signing_key, 0o600)
        subprocess.run(["git", "config", "--global", "gpg.format", "ssh"], check=False)
        subprocess.run(["git", "config", "--global", "user.signingkey", signing_key], check=False)
        subprocess.run(["git", "config", "--global", "commit.gpgsign", "true"], check=False)


def generate_agents_md():
    config_dir = Path(HOME) / ".config" / "opencode"
    config_dir.mkdir(parents=True, exist_ok=True)
    agents_md = config_dir / "AGENTS.md"

    context_dir = config_dir / "context.d"
    fragments = sorted(context_dir.glob("*.md")) if context_dir.is_dir() else []

    with open(agents_md, "w") as f:
        for fragment in fragments:
            f.write(fragment.read_text())
            f.write("\n")


def write_config_content():
    """Write OPENCODE_CONFIG_CONTENT to opencode.json."""
    content = os.environ.get("OPENCODE_CONFIG_CONTENT")
    if not content:
        return

    config_path = Path(HOME) / ".config" / "opencode" / "opencode.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    with open(config_path, "w") as f:
        f.write(content)


def discover_models(endpoint_url, api_key=None):
    """Discover models via the OpenAI-compatible /v1/models endpoint.

    endpoint_url must include the /v1 prefix (e.g. http://host:11434/v1).
    """
    headers = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    try:
        url = endpoint_url.rstrip("/") + "/models"
        req = Request(url, headers=headers)
        with urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read())
            models = data.get("data", [])
            enable_tools = os.environ.get("OPENCODIO_ENABLE_TOOLS", "false") == "true"
            return {
                m["id"]: {"tools": enable_tools}
                for m in models
                if isinstance(m, dict) and "id" in m
            }
    except (URLError, json.JSONDecodeError, KeyError, OSError):
        return {}


def configure_vertex_env():
    """Map opencodio env vars to what OpenCode's built-in vertex provider expects."""
    adc_path = os.environ.get(
        "GOOGLE_APPLICATION_CREDENTIALS",
        os.path.join(HOME, ".config/gcloud/application_default_credentials.json"),
    )

    project = (
        os.environ.get("GOOGLE_CLOUD_PROJECT")
        or os.environ.get("GOOGLE_VERTEX_PROJECT")
    )
    if not project:
        try:
            with open(adc_path) as f:
                adc = json.load(f)
                project = adc.get("quota_project_id") or adc.get("project_id")
        except (OSError, json.JSONDecodeError):
            pass

    if not project:
        log("ERROR: Could not determine GCP project. Set GOOGLE_CLOUD_PROJECT.")
        sys.exit(1)

    location = (
        os.environ.get("GOOGLE_CLOUD_LOCATION")
        or os.environ.get("CLOUD_ML_REGION")
        or "us-east5"
    )

    os.environ.setdefault("GOOGLE_CLOUD_PROJECT", project)
    os.environ.setdefault("GOOGLE_CLOUD_LOCATION", location)

    log(f"Vertex AI: project={project}, location={location}")


def register_openai_compatible_provider():
    endpoint_url = os.environ.get("OPENCODIO_OPENAI_COMPATIBLE_ENDPOINT")
    if not endpoint_url:
        return

    provider_name = os.environ.get("OPENCODIO_CUSTOM_PROVIDER_NAME", "custom")
    api_key = os.environ.get("OPENCODIO_API_KEY")

    models = discover_models(endpoint_url, api_key)
    if not models:
        log(f"WARNING: Could not discover models from {endpoint_url}. Is the server running?")

    options = {"baseURL": endpoint_url}
    if api_key:
        options["apiKey"] = api_key

    config = {
        "$schema": "https://opencode.ai/config.json",
        "provider": {
            provider_name: {
                "npm": "@ai-sdk/openai-compatible",
                "options": options,
                "models": models,
            }
        },
    }

    config_path = Path(HOME) / ".config" / "opencode" / "opencode.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    with open(config_path, "w") as f:
        json.dump(config, f, indent=2)


def parse_args(argv):
    prompt = os.environ.get("OPENCODIO_PROMPT", "")
    extra_args = []
    i = 0
    while i < len(argv):
        if argv[i] == "-p" and i + 1 < len(argv):
            prompt = argv[i + 1]
            i += 2
        else:
            extra_args.append(argv[i])
            i += 1
    return prompt, extra_args


def run_non_streaming(prompt, model_args, extra_args):
    if prompt:
        os.execvp("opencode", ["opencode", "run"] + model_args + extra_args + [prompt])
    else:
        os.execvp("opencode", ["opencode"] + model_args + extra_args)


def run_streaming(prompt, model_args, extra_args):
    os.environ["OPENCODE_EXPERIMENTAL"] = "true"

    if not prompt:
        log('ERROR: Streaming mode requires a prompt. Set OPENCODIO_PROMPT or pass -p "prompt"')
        sys.exit(1)

    stream_args = []
    wrap = os.environ.get("OPENCODIO_WRAP")
    if wrap:
        stream_args += ["--wrap", wrap]
    if os.environ.get("NO_COLOR") == "1":
        stream_args.append("--no-color")

    opencode_cmd = ["opencode", "run", "--format", "json"] + model_args + extra_args + [prompt]
    stream_cmd = ["python3", "-u", "/usr/local/bin/stream-opencode.py"] + stream_args

    opencode_proc = subprocess.Popen(
        opencode_cmd,
        stdout=subprocess.PIPE,
        stderr=sys.stderr,
    )

    stream_proc = subprocess.Popen(
        stream_cmd,
        stdin=opencode_proc.stdout,
    )

    # Release our reference so opencode gets SIGPIPE if stream exits early
    if opencode_proc.stdout:
        opencode_proc.stdout.close()

    def cleanup(signum, _frame):
        for p in (opencode_proc, stream_proc):
            if p.poll() is None:
                try:
                    p.kill()
                except OSError:
                    pass
        sys.exit(128 + signum)

    signal.signal(signal.SIGTERM, cleanup)
    signal.signal(signal.SIGINT, cleanup)

    stream_rc = stream_proc.wait()
    opencode_rc = opencode_proc.wait()

    if stream_rc != 0:
        sys.exit(stream_rc)
    if opencode_rc != 0:
        sys.exit(opencode_rc)


def main():
    provider = detect_provider()
    print(f"=== Provider: {provider} ===", flush=True)

    if provider == "vertex":
        adc_path = os.environ.get(
            "GOOGLE_APPLICATION_CREDENTIALS",
            os.path.join(HOME, ".config/gcloud/application_default_credentials.json"),
        )
        if not os.path.isfile(adc_path):
            log(f"ERROR: ADC credentials not found at {adc_path}")
            log("Mount your credentials or set GOOGLE_APPLICATION_CREDENTIALS.")
            sys.exit(1)

    if provider == "config":
        write_config_content()
    elif provider == "custom":
        register_openai_compatible_provider()
    elif provider == "vertex":
        configure_vertex_env()

    configure_git()

    workdir = os.path.join(HOME, "workdir")
    if os.path.isdir(workdir):
        os.chdir(workdir)

    generate_agents_md()

    prompt, extra_args = parse_args(sys.argv[1:])

    model_args = []
    model = os.environ.get("OPENCODIO_MODEL")
    if model:
        model_args = ["-m", model]

    if os.environ.get("OPENCODIO_STREAM") == "1":
        run_streaming(prompt, model_args, extra_args)
    else:
        run_non_streaming(prompt, model_args, extra_args)


if __name__ == "__main__":
    main()
