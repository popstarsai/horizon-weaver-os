# Native agent layer v0.1

This increment is a runnable, opt-in experiment. A short Python loop delegates
planning to a configured model; systemd supervises the process. A complete
example lives in [system-health.md](../usr/share/horizon-weaver/agents/system-health.md).
The [decision record](decisions/0001-native-agent-layer.md) explains each major
choice and its difference from upstream.

## Definition contract

Each `.md` file starts with exactly one fenced `toml` block followed by Markdown
instructions. TOML is parsed with Python's standard library; Markdown is never
executed as code. The file basename must match `name`, a lowercase slug of at
most 24 characters. Unknown or missing metadata fields fail validation.

| Field | Enforced meaning |
| --- | --- |
| `schema_version` | Integer `1`; unknown versions are rejected |
| `name` | Stable identity, filename, systemd instance and state-directory suffix |
| `enabled` | Boolean opt-in per agent; global supervisor enable is also required |
| `goals` | Nonempty list supplied to the model |
| `skills` | Nonempty list of Markdown skill names; loaded and validated before launch |
| `allowed_tools` | Nonempty subset of the global MCP policy and compiled diagnostic catalog |
| `memory` | Exactly `/var/lib/horizon-weaver/<name>` |
| `isolation` | Only `systemd-read-only` is implemented |
| `restart` | `no` or `on-failure`; translated into systemd restart policy |
| `restart_sec` | Integer 30–3600 seconds |
| `interval_sec` | Integer 300–86400 seconds between inactive periods |
| `max_steps` | Integer 1–supervisor ceiling; hard maximum 16 model turns |
| `model` | An allowed gateway alias, never a provider URL or API key |

Defaults live under `/usr/share/horizon-weaver`. A same-named file in
`/etc/horizon-weaver` replaces the **whole** default; there is no implicit merge.
This applies to agents, skills, `supervisor.toml` and `mcp.toml`. Copy an agent
and set `enabled = false` to disable it. Deleting an override restores the
vendor default. Symlink overrides are rejected; `/dev/null` masking is not
implemented. Missing skills and forbidden tools fail closed, including in a
disabled definition, so invalid policy is visible before activation.

Deployed files and their parent directories must be root-owned and not writable
by group or others. The development validator omits those ownership checks
unless `--trusted` is specified. The systemd generator and deployed runner always
enable them. Agent processes cannot edit their definitions or skills.

## Supervisor and isolation

The generator runs on boot and `systemctl daemon-reload`. It validates all
definitions before writing any units to systemd's normal generator directory.
One malformed definition prevents generation for the entire set. The generator
does not launch models or tools and makes no network requests.

For each enabled agent it creates a timer and a drop-in for
`horizon-weaver-agent@<name>.service`. The static
[template](../usr/lib/systemd/system/horizon-weaver-agent@.service) supplies:

- A separate dynamic UID and private `StateDirectory` for each agent.
- A read-only filesystem view except its state directory and private temporary
  files; protected home directories, devices, kernel and control groups.
- Empty capabilities, no privilege escalation, no Docker socket or `/sysroot`.
- Loopback-only IP policy and a fixed gateway URL. No provider key is passed to
  the runner or MCP subprocess; only the gateway access credential is loaded.
- 256 MiB memory, 25% CPU quota, 32 tasks, a configurable wall-clock ceiling,
  and at most three rapid failure starts per ten minutes.

systemd starts timers when `horizon-weaver.target` is started. A timer runs after
30–60 seconds and subsequently after the service becomes inactive plus its
interval and jitter. A service instance cannot overlap itself. Runtime failures
use the declared restart policy; configuration exit status 78 is not restarted.
Exhausting the turn budget records an incomplete report and waits for the next
timer rather than entering a retry storm.

This sandbox is for the bundled, read-only runtime, not a promise of containment
for arbitrary hostile executables. Some enforcement depends on kernel/systemd
support, including cgroup IP filtering. Verify those properties on the booted
target. Docker Sandboxes remain available for upstream CLI agents. A native
Docker sandbox launcher is a future increment, not an accepted `isolation` value.

## MCP diagnostics

The runner launches the bundled server over stdio in its own sandbox. The
implemented protocol revision is **2025-11-25**: `initialize`,
`notifications/initialized`, `ping`, `tools/list`, `tools/call` and orderly EOF
shutdown. This is a deliberately limited compatibility implementation, not
latest/draft MCP support or a general MCP gateway. No HTTP transport, external
server registry, sampling, roots, prompts, resources or tasks are advertised.

| Tool | Observation | Inputs |
| --- | --- | --- |
| `system.snapshot` | Uptime, `/proc/meminfo`, filesystem capacity | None |
| `system.failed_units` | Failed systemd services | None |
| `system.unit_status` | Selected status properties | Validated `.service` name |
| `system.bootc_status` | Local bootc deployment state | None |
| `system.update_timer` | Existing bootc update timer state | None |

The global [mcp.toml](../usr/share/horizon-weaver/mcp.toml) can restrict the
compiled catalog. Each agent selects a subset; discovery exposes only that
subset. The runner checks every decision and the server independently checks
every invocation. Commands use fixed argument vectors, no shell, bounded output
and timeouts. Extra arguments and service-name injection are rejected.
`readOnlyHint` is descriptive; actual enforcement is in code and OS permissions.

Tools observe the host through the service sandbox. `bootc status --json` may
be unavailable to the dynamic user or blocked by hidden deployment storage;
that yields an error observation and an `unknown` assessment, not privilege
escalation or a fabricated healthy state. Full bootc visibility needs a separately
reviewed, fixed-output collector in a later increment. Systemd properties can
similarly be unavailable on a particular image. No journal membership is granted.

## Adaptive execution and memory

Every run loads goals, skills and the current allowed tool catalog, then gives
the model the previous report as untrusted, potentially stale context. The model
returns a strict JSON action containing a short visible plan and either one
tool call or a final report. This small action contract works over chat completions;
it does not require provider-specific native tool-calling APIs.
The runner requires at least one actual MCP result before accepting a completed
report. An error result can support an uncertainty report; this check does not
establish that the model's conclusions are correct.

The runner executes an allowed MCP call and returns the observation to the model.
The next plan and tool selection depend on that observation. For example, failed
units can lead to individual status inspection; no failed units can lead to a
short report. The update advisor can defer for resource pressure or failed
services, discuss an already staged deployment, and notice existing update
automation. These are model-selected branches, not hard-coded diagnostic scripts.
The model must support the JSON action contract; malformed responses consume
the finite budget and receive a corrective observation. Model competence still
requires evaluation with the selected local or remote model.

`latest.json` stores the status, report, action plans and tool observations for
the most recent run, atomically replaced with mode 0600. Its size is bounded by
turn and message limits; this is not an append-only audit history. A `running`
record replaces the previous success before inference, so a killed run leaves
an identifiable incomplete state. Start-up failures before memory is opened
are visible in the system journal. A later run receives the previous record,
truncated to 16,000 characters. Do not treat reports as a privileged instruction
channel or a record of changes actually performed.

## Inference gateway

The gateway is an operator-configured LiteLLM container. Models run in existing
llmman or other local/provider runtimes. No model runtime is replaced. Only the
gateway needs remote network access and provider credentials.

The [Compose example](../usr/share/horizon-weaver/gateway/compose.yaml) uses host
networking so it can reach local inference servers, binds LiteLLM to
`127.0.0.1:4000`, runs as UID 65532 with a read-only filesystem, and has no Docker
socket. Its root-owned systemd wrapper operates Docker solely to manage this
container. It is distinct from the unprivileged native-agent services.

An operator must choose a reviewed LiteLLM image by digest and verify its CLI
and configuration compatibility. There is no default floating image tag. The
first increment does not vendor/pin a tested LiteLLM release or pre-pull it into
bootc. This is an integration/configuration example until that image has passed
the live gateway acceptance checks. The deployment may need a network pull.

The default config routes `horizon-local` to a local primary and, on failure,
`horizon-local-backup`. Point both endpoints at actual local model servers;
example ports and names are not claims about llmman defaults. Set both models
to obey the JSON action contract. Retries and request timeouts are bounded.

[config.remote-example.yaml](../usr/share/horizon-weaver/gateway/config.remote-example.yaml)
adds `horizon-hybrid` (local with remote fallback) and `horizon-remote`. To opt in,
install it as the active config, set the remote environment values, add the
chosen alias to `allowed_models`, and change the chosen agent's `model`.
This sends that agent's prompts, observations and previous report to the remote
provider and can incur provider charges. `horizon-local` retains local-only
fallback even in this alternative config. The two YAML files are alternatives,
not automatically merged. Never point a backend at the gateway itself.

The shipped simple single-machine example uses LiteLLM's master key as the
gateway credential. It is not a per-agent authorization boundary. Multi-user
deployments need scoped virtual keys, route budgets and a separate administrative
surface before enabling remote spending. Do not expose port 4000 publicly.

## First setup on a booted image

First build and boot an image from this branch through the existing bootc build
path. The preserved upstream download links do not contain this layer. Run
these steps as the administrator on that booted image, after starting local
inference endpoints. They intentionally do not switch or reboot an existing OS.

```sh
sudo install -d -m0755 /etc/horizon-weaver/agents /etc/horizon-weaver/skills
sudo install -d -m0755 /etc/horizon-weaver/gateway
sudo install -d -m0700 /etc/horizon-weaver/credentials
sudo install -m0644 /usr/share/horizon-weaver/supervisor.toml /etc/horizon-weaver/supervisor.toml
sudo install -m0644 /usr/share/horizon-weaver/gateway/config.yaml /etc/horizon-weaver/gateway/config.yaml
sudo install -m0600 /usr/share/horizon-weaver/gateway/gateway.env.example /etc/horizon-weaver/gateway/gateway.env
sudoedit /etc/horizon-weaver/gateway/gateway.env
```

Replace the image digest, local models/endpoints and master key. Use a randomly
generated key with the `sk-` prefix, not the placeholder. Preserve secrets outside
version control. The remote fields are unused by the local-only config.

```sh
sudo sh -c 'umask 077; touch /etc/horizon-weaver/credentials/gateway-key'
sudoedit /etc/horizon-weaver/credentials/gateway-key
sudo chmod 0600 /etc/horizon-weaver/credentials/gateway-key
sudo systemctl enable --now horizon-weaver-gateway.service
sudo journalctl -u horizon-weaver-gateway.service -n 50 --no-pager
```

Put the same master-key value, with no variable name, into `gateway-key`. Confirm
that the gateway starts, can answer `horizon-local`, and reaches the configured
backup when the primary is unavailable. An `active` Compose wrapper alone does
not prove inference readiness. Then edit `supervisor.toml` to set `enabled = true`:

```sh
sudoedit /etc/horizon-weaver/supervisor.toml
sudo /usr/bin/python3 -I /usr/libexec/horizon-weaver/supervisor.py --trusted
sudo systemctl daemon-reload
sudo systemctl enable --now horizon-weaver.target
systemctl list-timers 'horizon-weaver-agent-*'
sudo systemctl start horizon-weaver-agent@system-health.service
sudo journalctl -u horizon-weaver-agent@system-health.service -n 50 --no-pager
sudo cat /var/lib/horizon-weaver/system-health/latest.json
```

The layer has two opt-in gates: supervisor `enabled = true` and the target's
activation. Agent defaults have `enabled = true` so this enables both examples;
copy and disable either definition beforehand to select only one.

## Editing, stopping and coexistence

For changes, stop the target first, edit root-owned overrides, validate, reload
systemd, then start the target. This stops existing agent services and timers via
`PartOf=` and avoids leaving an old timer running after removing a definition.

```sh
sudo systemctl stop horizon-weaver.target
# Edit files under /etc/horizon-weaver, then:
sudo /usr/bin/python3 -I /usr/libexec/horizon-weaver/supervisor.py --trusted
sudo systemctl daemon-reload
sudo systemctl start horizon-weaver.target
```

To disable across reboot, set supervisor `enabled = false`, run
`sudo systemctl disable --now horizon-weaver.target`, then daemon-reload.
Stop/disable `horizon-weaver-gateway.service` separately when no clients need it.
Definitions, reports and upstream services remain available.

Classic services remain authoritative. An agent can observe a failed service and
propose a restart; a human uses ordinary `systemctl` commands to act. Selective
replacement of a service is a future opt-in migration with explicit ownership,
rollback and a privileged action broker. Nothing in this version disables
bootc's update timer, bootguard, Docker or desktop services.

## Image updates and rollback

The existing Dockerfile copies `usr/` into the image; no separate installer
rewrites the running filesystem. Agent code and vendor defaults therefore update
with bootc and revert with image rollback. `/etc` overrides and `/var` memory
follow upstream persistence, and state is not rolled back transactionally with
the image. Unknown schemas stop agents instead of silently migrating data.
Revalidate overrides after an update or rollback. Keep upstream VM smoke tests
and bootguard checks as release gates independent of model availability.
