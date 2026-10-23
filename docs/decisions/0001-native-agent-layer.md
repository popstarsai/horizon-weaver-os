# ADR 0001 — Native agent layer, first increment

Status: implemented experimental proposal; booted-image acceptance pending.

Baseline: `popstarsai/horizon-weaver-os` commit
`7ba08a9bb1553851028ee20e12e848369bfdff4b`, derived from AgenticLinux.

## Decisions and differences from upstream

| Decision | Reason and consequence | Upstream comparison |
| --- | --- | --- |
| Keep bootc, bootguard, GPU packages and Docker/Sandboxes | Preserve image delivery, rollback, hardware support and existing isolation; no model participates in boot health | Existing implementation remains authoritative |
| Image defaults in `/usr/share`, full root-owned overrides in `/etc`, state in `/var` | Defaults track the image; site policy and memory persist; explicitly distinguish image rollback from data rollback | Upstream installs agent programs; the fork adds an OS definition/configuration/state contract |
| Fenced TOML plus Markdown | Standard-library parser, readable prose, explicit typed fields; no YAML dependency, executable Markdown, includes or templating | Agents gain an inspectable native identity beyond an installed CLI |
| Explicit schema and strict validation | Reject unsupported policy instead of pretending to enforce it; all definitions validated before generation | New validation belongs to the native layer only |
| Reusable Markdown skills by slug | Skills can be versioned and overridden like definitions; skills provide guidance, not new permissions | Existing installed agents and their own skill mechanisms remain independent |
| systemd generator, template and timers | Reuse process supervision, resource controls and restarts instead of adding a persistent root orchestrator | Native agents coexist with classic services |
| Bounded standard-library agent loop | Small inspectable adapter demonstrates planning and adaptation across providers; JSON actions reduce SDK coupling | Upstream CLIs are still available; no new general agent framework replaces them |
| One bundled MCP stdio server, pinned protocol | Establish interoperable discovery/calls without network listeners or external-server trust decisions | Adds standardized native system observations |
| Fixed read-only tools with two allowlist checks | Model output cannot become arbitrary command execution; diagnostic failures remain evidence gaps | No extension of upstream agent/root privileges |
| Per-agent systemd sandbox, not Docker launch in v0.1 | Enables low-overhead diagnostics and private memory; unsupported isolation choices are rejected | Docker Engine, rootless Docker and Sandboxes remain intact for existing workflows |
| LiteLLM behind a loopback gateway | Stable model aliases, central provider settings and fallback configuration; local runtimes keep GPU ownership | Complements llmman rather than removing it |
| Local fallback by default; explicit hybrid alias | Prevent an unavailable local model from silently exporting diagnostic context to a provider | Remote routing becomes an administrator policy choice for native agents |
| Gateway credentials through systemd credentials; provider keys only in gateway | No keys in Markdown, source or model prompts; simple example shares a gateway key and needs scoped keys for multi-user use | New credentials are separate from existing CLI login state |
| No remediation/update mutation tools | Complete advisory loop can be evaluated before introducing privileged decisions | bootc updates and systemd controls remain human/classic-service operated |
| Disabled services and global switch | Installing the image does not start inference requests or make the desktop depend on models | Existing upstream first-boot behavior stays intact |
| Latest bounded JSON report | Persistent short memory and inspectable actions without an unbounded log store or vector database | New agent state is ordinary `/var` data, not a new OS storage layer |
| Separate tests and preserved upstream README | Agent work can be reviewed quickly while retaining original build/install guidance | Upstream boot/image tests stay independent |
| Retain image names and visual branding for this increment | Avoid coupling release assets, registry migration and OS identity changes to runtime semantics | README explicitly identifies Horizon Weaver and labels upstream downloads |

## Boundaries

This is not an AGI kernel, an autonomous privileged updater, an MCP conformance
suite, or a completed distribution release. The host runtime is still Linux and
systemd. The native semantics are a versioned userspace contract.

The built-in diagnostics are deliberately narrow. `bootc status` visibility may
be limited under the sandbox, and no privilege expansion is hidden in a tool.
An action broker or fixed-output collector requires separate review and tests.
Adding external MCP servers requires protocol-version compatibility, capability
filtering, process isolation and explicit configuration. A Docker launcher needs
a separate policy that does not pass a rootful Docker socket to the model.

Models may produce incorrect plans or premature conclusions; bounded execution
and permissions limit effects but do not establish diagnostic correctness. The
tests exercise control flow with a deterministic model fixture. Real-model
evaluation and booted-image tests are recorded as outstanding release gates.

## Source references

These are primary implementation references, not claims that the experimental
integration has passed a release test:

- [bootc filesystem semantics](https://bootc.dev/bootc/bootc-filesystem.7.html):
  immutable image content and persistent configuration/state.
- [systemd generators](https://www.freedesktop.org/software/systemd/man/latest/systemd.generator.html)
  and [execution controls](https://www.freedesktop.org/software/systemd/man/latest/systemd.exec.html).
- MCP **2025-11-25** [lifecycle](https://modelcontextprotocol.io/specification/2025-11-25/basic/lifecycle),
  [transports](https://modelcontextprotocol.io/specification/2025-11-25/basic/transports),
  and [tools](https://modelcontextprotocol.io/specification/2025-11-25/server/tools).
  This version is explicitly selected for compatibility, not described as latest.
- [LiteLLM configuration](https://docs.litellm.ai/docs/proxy/configs) and
  [routing](https://docs.litellm.ai/docs/routing): named model groups, environment
  credentials, retries and fallback routes.
- [AgenticLinux](https://github.com/ericcurtin/agenticlinux) and the retained
  [upstream guide](../../README.upstream.md).
