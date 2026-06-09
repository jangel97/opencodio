#!/usr/bin/env python3
"""Parse OpenCode --format json output into a human-readable CI log."""

import argparse
import atexit
import json
import re
import sys
import time

parser = argparse.ArgumentParser(description="Parse OpenCode JSON output")
parser.add_argument(
    "--wrap",
    type=int,
    default=0,
    metavar="COLS",
    help="Word-wrap output at COLS columns (0 = no wrapping)",
)
parser.add_argument(
    "--no-color",
    action="store_true",
    help="Disable ANSI color codes in output",
)
parser.add_argument(
    "--log-file",
    type=str,
    default="",
    help="Write plain-text (no ANSI) output to this file",
)
args = parser.parse_args()

if args.no_color:
    THINK_COLOR = TOOL_COLOR = AGENT_COLOR = RED = YELLOW = RESET = ""
else:
    THINK_COLOR = "\033[3;31m"  # italic red
    TOOL_COLOR = "\033[1;90m"  # bold gray
    AGENT_COLOR = ""  # normal
    RED = "\033[31m"
    YELLOW = "\033[33m"
    RESET = "\033[0m"

_ANSI_RE = re.compile(r"\033\[[0-9;]*m")
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")

_total_input_tokens = 0
_total_output_tokens = 0
_total_cache_read = 0
_total_cache_write = 0
_total_cost = 0.0
_last_emitted_total = 0
_last_emitted_time = 0.0
_saw_finish = False


def _safe(text):
    """Strip ANSI escapes, control characters, and CI workflow commands."""
    text = str(text)
    text = _ANSI_RE.sub("", text)
    text = _CONTROL_RE.sub("", text)
    if text.startswith("::"):
        text = f" {text}"
    return text


log_file = open(args.log_file, "w") if args.log_file else None
if log_file:
    atexit.register(log_file.close)


def _log(text):
    """Write plain text to the log file (if configured)."""
    if log_file:
        log_file.write(text)
        log_file.flush()


def _print(text, end="\n"):
    """Print colored text to stdout and plain text to the log file."""
    print(text, end=end, flush=True)
    if log_file:
        plain = _ANSI_RE.sub("", text)
        log_file.write(plain + end)
        log_file.flush()


def _wrap_text(text):
    """Word-wrap text at the configured column width."""
    if not args.wrap or len(text) <= args.wrap:
        return text
    wrapped = ""
    col = 0
    for word in text.split(" "):
        if col + len(word) > args.wrap and col > 0:
            wrapped += "\n"
            col = 0
        if col > 0:
            wrapped += " "
            col += 1
        wrapped += word
        col += len(word)
    return wrapped


def _format_tool(name, params):
    """Return a compact one-line summary for a tool call."""
    if not params:
        return ""
    name_lower = name.lower()
    if name_lower == "bash":
        cmd = params.get("command", "")
        desc = params.get("description", "")
        return f"$ {cmd}" + (f"  # {desc}" if desc else "")
    if name_lower == "read":
        path = params.get("file_path", params.get("filePath", ""))
        parts = [path]
        if "offset" in params:
            parts.append(f"L{params['offset']}")
        if "limit" in params:
            parts.append(f"+{params['limit']}")
        return " ".join(parts)
    if name_lower == "write":
        return params.get("file_path", params.get("filePath", ""))
    if name_lower == "edit":
        path = params.get("file_path", params.get("filePath", ""))
        old = params.get("old_string", params.get("oldString", ""))
        preview = old.split("\n")[0][:60]
        if len(old) > len(preview):
            preview += "..."
        return f"{path}: {preview}"
    if name_lower == "glob":
        pattern = params.get("pattern", "")
        path = params.get("path", ".")
        return f"{pattern} in {path}"
    if name_lower == "grep":
        pattern = params.get("pattern", "")
        path = params.get("path", ".")
        return f"/{pattern}/ in {path}"
    return ", ".join(f"{k}={v}" for k, v in params.items())


def _emit_tokens(tokens, cost=0.0):
    """Print token stats if the total has increased enough."""
    global _total_input_tokens, _total_output_tokens
    global _total_cache_read, _total_cache_write, _total_cost
    global _last_emitted_total, _last_emitted_time

    if not tokens:
        return

    _total_input_tokens += tokens.get("input", tokens.get("input_tokens", 0))
    _total_output_tokens += tokens.get("output", tokens.get("output_tokens", 0))
    _total_cache_read += tokens.get("cache_read", tokens.get("cache_read_input_tokens", 0))
    _total_cache_write += tokens.get("cache_write", tokens.get("cache_creation_input_tokens", 0))
    _total_cost += cost

    total = _total_input_tokens + _total_output_tokens + _total_cache_read + _total_cache_write
    if total - _last_emitted_total >= 5_000 or _last_emitted_total == 0:
        now = time.monotonic()
        rate = 0.0
        if _last_emitted_time > 0:
            dt = now - _last_emitted_time
            dv = total - _last_emitted_total
            if dt > 0:
                rate = dv / dt
        rate_str = f" rate={rate:.0f}/s" if rate > 0 else ""
        cost_str = f" cost=${_total_cost:.4f}" if _total_cost > 0 else ""
        _last_emitted_total = total
        _last_emitted_time = now
        _print(
            f"{TOOL_COLOR}  \U0001f4ca TOKENS in={_total_input_tokens}"
            f" out={_total_output_tokens}"
            f" cache_r={_total_cache_read}"
            f" cache_w={_total_cache_write}"
            f" total={total}{rate_str}{cost_str}{RESET}",
        )


while True:
    line = sys.stdin.readline()
    if not line:
        break
    try:
        msg = json.loads(line)
    except (json.JSONDecodeError, ValueError):
        continue

    msg_type = msg.get("type", "")

    # --- Text output from the model ---
    if msg_type == "text":
        part = msg.get("part", msg)
        text = part.get("text", "")
        if text:
            safe_text = _safe(text)
            wrapped = _wrap_text(safe_text)
            _print(f"{AGENT_COLOR}\U0001f4ac OpenCode: {wrapped}{RESET}")

    # --- Thinking / reasoning ---
    elif msg_type == "thinking":
        part = msg.get("part", msg)
        text = part.get("thinking", part.get("text", ""))
        if text:
            safe_text = _safe(text)
            wrapped = _wrap_text(safe_text)
            _print(f"{THINK_COLOR}\U0001f9e0 Thinking: {wrapped}{RESET}")

    # --- Tool use ---
    elif msg_type == "tool_use":
        part = msg.get("part", msg)
        tool = part.get("tool", part.get("name", "unknown"))
        input_params = part.get("input", part.get("state", {}).get("input", {}))
        summary = _safe(_format_tool(tool, input_params))

        icon = "\U0001f527"
        if summary:
            _print(f"  {TOOL_COLOR}{icon} {tool} {summary}{RESET}")
        else:
            _print(f"  {TOOL_COLOR}{icon} {tool}{RESET}")

    # --- Tool result ---
    elif msg_type == "tool_result":
        pass

    # --- Step boundaries ---
    elif msg_type == "step_start":
        _print(f"\n{TOOL_COLOR}--- step ---{RESET}")

    elif msg_type == "step_finish":
        part = msg.get("part", msg)
        tokens = part.get("tokens", part.get("usage", {}))
        cost = part.get("cost", 0.0)
        _emit_tokens(tokens, cost)
        _saw_finish = True

    # --- System events ---
    elif msg_type == "system":
        subtype = msg.get("subtype", "")
        if subtype == "api_retry":
            attempt = msg.get("attempt", "?")
            max_retries = msg.get("max_retries", "?")
            delay = msg.get("retry_delay_ms", "?")
            error = _safe(msg.get("error", "unknown"))
            _print(
                f"{YELLOW}\U0001f504 Retry {attempt}/{max_retries}{RESET} "
                f"{error} — retrying in {delay}ms",
            )

    # --- Errors ---
    elif msg_type == "error":
        error = msg.get("error", msg)
        if isinstance(error, dict):
            error_name = _safe(error.get("type", error.get("name", "unknown")))
            error_msg = _safe(error.get("message", error.get("data", {}).get("message", "")))
        else:
            error_name = "error"
            error_msg = _safe(str(error))
        _print(f"{RED}❌ Error: {error_name}: {error_msg}{RESET}")

    # --- Result / done ---
    elif msg_type == "result":
        _saw_finish = True
        break

    # --- Message-level events (Claude-style stream format compatibility) ---
    elif msg_type == "stream_event":
        event = msg.get("event", {})
        event_type = event.get("type", "")

        if event_type == "content_block_start":
            block = event.get("content_block", {})
            block_type = block.get("type")
            if block_type == "text":
                print(f"{AGENT_COLOR}\U0001f4ac OpenCode: ", end="", flush=True)
                _log("\U0001f4ac OpenCode: ")
            elif block_type == "thinking":
                print(f"{THINK_COLOR}\U0001f9e0 Thinking: ", end="", flush=True)
                _log("\U0001f9e0 Thinking: ")
            elif block_type in ("tool_use", "server_tool_use"):
                tool_name = block.get("name", "unknown")
                _tool_json_parts = []

        elif event_type == "content_block_delta":
            delta = event.get("delta", {})
            delta_type = delta.get("type")
            if delta_type == "text_delta":
                text = _safe(delta.get("text", ""))
                print(text, end="", flush=True)
                _log(text)
            elif delta_type == "thinking_delta":
                text = _safe(delta.get("thinking", ""))
                print(text, end="", flush=True)
                _log(text)

        elif event_type == "content_block_stop":
            print(RESET, flush=True)
            _log("\n")

        elif event_type == "message_delta":
            usage = event.get("usage", {})
            if usage:
                _emit_tokens(usage)

    # Unknown event types are silently skipped


# Final token summary
if _total_input_tokens > 0 or _total_output_tokens > 0:
    total = _total_input_tokens + _total_output_tokens + _total_cache_read + _total_cache_write
    cost_str = f" cost=${_total_cost:.4f}" if _total_cost > 0 else ""
    _print(
        f"\n{TOOL_COLOR}\U0001f4ca FINAL TOKENS in={_total_input_tokens}"
        f" out={_total_output_tokens}"
        f" cache_r={_total_cache_read}"
        f" cache_w={_total_cache_write}"
        f" total={total}{cost_str}{RESET}",
    )

print()
sys.exit(0 if _saw_finish else 1)
