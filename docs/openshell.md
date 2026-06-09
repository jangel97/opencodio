# OpenShell Integration

[NVIDIA OpenShell](https://github.com/NVIDIA/OpenShell) provides sandboxed execution for AI agents with policy-enforced network egress, filesystem access, and binary controls. Use it to run opencodio with security guardrails — especially useful when giving the agent access to production clusters or sensitive repositories.

## Quick Start

Install OpenShell:

```bash
curl -LsSf https://raw.githubusercontent.com/NVIDIA/OpenShell/main/install.sh | sh
```

Run opencodio inside an OpenShell sandbox:

```bash
openshell sandbox create \
  --from quay.io/jangel97/opencodio:v0.0.1 \
  --policy ./policy.yaml \
  -- entrypoint.sh
```

## Example Policies

### Kubernetes read-only debugging

Allow the agent to inspect a cluster but not modify anything. Only kubectl and git can reach the network.

```yaml
version: 1

filesystem_policy:
  read_only: [/usr, /lib, /etc]
  read_write: [/home/opencodio/workdir, /tmp]
  include_workdir: true

landlock:
  compatibility: best_effort

process:
  run_as_user: opencodio
  run_as_group: opencodio

network_policies:
  vertex-ai:
    name: "Vertex AI inference"
    endpoints:
      - host: "*.googleapis.com"
        port: 443
        protocol: rest
        enforcement: enforce
        rules:
          - allow:
              method: POST
              path: "/**"
    binaries:
      - path: /usr/local/bin/opencode

  k8s-api:
    name: "Kubernetes API (read-only)"
    endpoints:
      - host: "*.k8s.io"
        port: 443
        protocol: rest
        enforcement: enforce
        rules:
          - allow:
              method: GET
              path: "/**"
          - deny:
              method: DELETE
              path: "/**"
          - deny:
              method: POST
              path: "/**"
          - deny:
              method: PUT
              path: "/**"
          - deny:
              method: PATCH
              path: "/**"
    binaries:
      - path: /usr/local/bin/kubectl
```

### CI code review (no cluster access)

Lock the agent down to only reach the LLM provider. No kubectl, no outbound network for anything else.

```yaml
version: 1

filesystem_policy:
  read_only: [/usr, /lib, /etc]
  read_write: [/home/opencodio/workdir, /tmp]
  include_workdir: true

landlock:
  compatibility: best_effort

process:
  run_as_user: opencodio
  run_as_group: opencodio

network_policies:
  vertex-ai:
    name: "Vertex AI inference"
    endpoints:
      - host: "*.googleapis.com"
        port: 443
        protocol: rest
        enforcement: enforce
        rules:
          - allow:
              method: POST
              path: "/**"
    binaries:
      - path: /usr/local/bin/opencode
```

### Ollama (local model, no internet)

Block all external egress — only allow the agent to reach a local Ollama server.

```yaml
version: 1

filesystem_policy:
  read_only: [/usr, /lib, /etc]
  read_write: [/home/opencodio/workdir, /tmp]
  include_workdir: true

landlock:
  compatibility: best_effort

process:
  run_as_user: opencodio
  run_as_group: opencodio

network_policies:
  ollama:
    name: "Local Ollama server"
    endpoints:
      - host: "192.168.1.138"
        port: 11434
        protocol: rest
        enforcement: enforce
        rules:
          - allow:
              method: POST
              path: "/**"
          - allow:
              method: GET
              path: "/**"
    binaries:
      - path: /usr/local/bin/opencode
```

## Dynamic Policy Updates

OpenShell supports hot-reloading network policies on running sandboxes. Grant temporary access without restarting:

```bash
# Grant GitHub API access to the gh binary
openshell policy update my-sandbox \
  --add-endpoint api.github.com:443:read-only:rest:enforce \
  --binary /usr/bin/gh \
  --wait

# Revoke by resetting to the original policy
openshell policy set my-sandbox --policy ./policy.yaml --wait
```

## Why Use OpenShell with opencodio

Running an AI agent with kubectl access to production clusters is powerful but risky. OpenShell adds defense in depth:

- **Network egress control** — the agent can only reach endpoints you whitelist
- **Binary restrictions** — only approved executables can make network calls
- **Filesystem isolation** — kernel-level (Landlock) enforcement of read/write boundaries
- **Audit mode** — log policy violations without blocking, useful for policy development

Without OpenShell, the container has no restrictions on what the agent can do once it has kubectl credentials. With OpenShell, you control the blast radius.
