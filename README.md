# Horizon Weaver OS

An experimental agentic Linux distribution derived from
[AgenticLinux](https://github.com/ericcurtin/agenticlinux), under Apache-2.0.
Horizon Weaver adds native agent definitions and lifecycles to the upstream
immutable bootc desktop. **This is an experimental first increment, not a
production autonomous system administrator.**

The upstream base already supplies Claude, Codex, OpenCode, OpenClaw, Goose,
llmman, Docker Engine and Docker Sandboxes, GPU runtimes, bootc image updates,
rollback and bootguard. Those implementations remain in place. The new layer
turns an agent into a named OS workload with declared goals, reusable skills,
tool permissions, persistent memory and a systemd-managed lifecycle.

## First increment

| Capability | Implemented here |
| --- | --- |
| Native definitions | Markdown with a validated TOML metadata block; administrator overrides |
| Supervisor | Small systemd generator; service template; per-agent timers and restart policy |
| Adaptive execution | Bounded model → MCP tool → observation → revised plan loop |
| MCP tools | Bundled stdio server with five read-only system diagnostics; policy enforced in client and server |
| Inference | OpenAI-compatible loopback gateway interface; operator-configured LiteLLM Compose and local/remote routing examples |
| Examples | System-health agent and adaptive bootc update advisor |
| Memory | Private per-agent report and latest-run audit under `/var/lib/horizon-weaver` |
| Default state | Disabled until an administrator configures a gateway and enables the layer |

Gateway deployment, real-provider fallback and booted Fedora/CentOS validation
are still required before claiming an operational image release. There is no
automatic remediation, reboot, update application, Docker-backed native-agent
launcher, or arbitrary external MCP-server support in this increment.

## Layout and complete examples

| Installed location | Purpose |
| --- | --- |
| `/usr/share/horizon-weaver/agents/*.md` | Image-versioned agent defaults |
| `/usr/share/horizon-weaver/skills/*.md` | Reusable skills |
| `/etc/horizon-weaver/` | Root-owned overrides, gateway configuration and credentials |
| `/usr/libexec/horizon-weaver/` | Standard-library validator, supervisor, runner and MCP server |
| `/usr/lib/systemd/` | Agent service template, target, generator and opt-in presets |
| `/run/systemd/generator/` | Generated timers and restart-policy drop-ins |
| `/var/lib/horizon-weaver/<name>/` | Private persistent agent state |

Start with the complete [system-health agent](usr/share/horizon-weaver/agents/system-health.md),
[supervisor configuration](usr/share/horizon-weaver/supervisor.toml),
[service template](usr/lib/systemd/system/horizon-weaver-agent@.service) and
[update advisor](usr/share/horizon-weaver/agents/update-advisor.md).

Read [setup and operation](docs/native-agent-layer.md),
[the design decisions](docs/decisions/0001-native-agent-layer.md), and
[validation and next increments](docs/validation.md).

## Validate from a checkout

Python 3.11 or newer; no third-party Python dependencies, credentials or model
downloads are needed for these offline checks:

```sh
python3 -I usr/libexec/horizon-weaver/supervisor.py \
  --vendor usr/share/horizon-weaver --admin /nonexistent
python3 -m unittest discover -s test -p agent_layer_test.py -v
```

On a booted image containing this layer, configure the gateway and opt in using
the [setup guide](docs/native-agent-layer.md#first-setup-on-a-booted-image).
Do not copy binaries into an immutable running `/usr`; rebuild the image through
the existing [Dockerfile](Dockerfile).

## Upstream base and releases

The original [upstream guide](README.upstream.md) is preserved verbatim and
covers Fedora 44 / CentOS Stream 10 variants, installation, Docker isolation,
GPU support, image builds, atomic updates and rollback. **Its published images,
downloads and installation commands refer to AgenticLinux, not a released
Horizon Weaver image.** This increment retains upstream image names, desktop
branding and release workflow. A separately validated Horizon Weaver release
must choose its own registry/image identity before distribution.

The existing `usr/` image overlay installs the layer. Python is declared
explicitly in [packages.txt](packages.txt). The new services are not enabled by
the build, and native agents are not dependencies of bootguard or the desktop.
No runtime package installation or model download is added to boot.

bootc still updates the image atomically; `/etc` overrides and `/var` state follow
the existing persistence model. **Image rollback does not undo agent memory or
other data in `/var`.** Existing systemd services, Docker Sandboxes, GPU drivers
and llmman remain available independently of the native layer.

## License and attribution

[LICENSE](LICENSE) retains upstream Apache-2.0 unchanged. Horizon Weaver additions
use Apache-2.0 as well; see [NOTICE](NOTICE). Third-party applications and runtime
images retain their own licenses. Horizon Weaver is a derivative project and
does not imply endorsement by upstream maintainers.
