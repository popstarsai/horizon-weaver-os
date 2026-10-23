# Validation and incremental roadmap

Recorded for this first increment:

- 18 offline tests passed on Python 3.12.14.
- `systemd-analyze verify` passed for the target, both agent instances and both
  generated timers using systemd 255. The gateway unit was not runtime-validated
  because Docker is unavailable in the development environment.
- Gateway YAML parsed; fallback targets and relative documentation links checked.
- Python compilation and whitespace checks passed.
- Upstream Dockerfile, build script, bootguard, bootc configuration and image
  workflow are unchanged; `README.upstream.md` matches the original README.

These checks validate the first increment's structure and offline behavior.
They do not establish booted-image isolation, live inference, real fallback,
hardware support or a working release artifact.

## Offline checks

```sh
python3 -I usr/libexec/horizon-weaver/supervisor.py --vendor usr/share/horizon-weaver --admin /nonexistent
python3 -m unittest discover -s test -p agent_layer_test.py -v
python3 -m py_compile usr/libexec/horizon-weaver/*.py
git diff --check
```

The suite checks metadata and override precedence, disabled-by-default generation,
restart/timer translation, schema and tool-policy rejection, service-name injection,
MCP negotiation/discovery/denial through a real subprocess, nonzero diagnostic
results, bounded malformed-model handling, model-to-tool policy checks, observed
results changing the next model-fixture plan, atomic report replacement and gateway
HTTP request/redirect behavior. No actual provider is contacted by these tests.
The new `Native agent layer` CI workflow runs those checks separately from the
upstream image publication workflow.

## Required acceptance on Fedora 44 and CentOS Stream 10

1. Build the existing bootc image and run existing container/VM smoke tests.
   Confirm Docker rootful/rootless, Sandboxes, GPU runtimes and bootguard remain
   available. Do not infer this from the Python suite.
2. Confirm both new services are disabled on first boot and the desktop boots
   without gateway configuration or network inference.
3. Validate the static/generated units with `systemd-analyze verify` and inspect
   effective service policy with `systemctl cat` and `systemd-analyze security`.
   Verify separate UIDs, state ownership, write restrictions, Docker-socket denial,
   process limits and loopback-only connectivity on the actual kernel.
4. Choose and record a reviewed LiteLLM image digest. Check Compose expansion,
   container startup as UID 65532, health, master-key authentication and named
   routes using the installed LiteLLM version. Confirm port 4000 is loopback-only.
5. With two local model endpoints, deliberately make the primary unavailable and
   confirm fallback reaches the backup. Test complete failure and bounded retries.
   In an explicitly opted-in test, verify hybrid remote fallback. Confirm the
   local-only alias never selects the remote route.
6. Use a JSON-capable model to run both agents. Simulate a disposable failed
   service and resource pressure; inspect evidence, changing plans and reports.
   Try prompt-injection text in mock observations and confirm no additional
   capabilities are granted. Record the model name and runtime versions.
7. Determine which diagnostics are available to the dynamic user, especially
   `bootc status`. Unavailable observations must produce uncertainty, not success.
   No automatic elevation is allowed.
8. Test gateway outage, malformed model output, wall-clock timeout, restart limits,
   no overlapping runs, stopping the target and removing/disabling an override.
   An interrupted run must not appear as a fresh successful report.
9. Stage an image update and perform a rollback in a disposable VM. Confirm the
   image code/defaults change while expected `/etc` overrides and `/var` reports
   remain. Revalidate definitions against the older schema on rollback.

These gates are pending until results from a booted image and real gateway are
recorded. This environment's offline tests do not substitute for them.

## Next increments

| Increment | Deliverable | Completion criterion |
| --- | --- | --- |
| 0.1 (this change) | Definition contract, supervisor, two advisory agents, bounded runner, read-only MCP, gateway examples | Offline checks; draft review; no claim of image release |
| 0.2 | Pinned gateway image, real-model fixtures, booted-image CI and a fixed-output bootc collector if needed | Fedora/CentOS acceptance above; working local and remote fallback |
| 0.3 | External MCP registry and native Docker sandbox backend | Tested per-agent permissions, isolated server lifecycles and no rootful socket in agents |
| 0.4 | Privileged action broker, explicit user approval and maintenance policy | Typed actions, idempotency, audit/rollback tests; controlled replacement of one noncritical service |
| Release preparation | Horizon Weaver registry identity, signed-image policy and visual branding | Reproducible image/ISO artifacts and verified install/update/rollback path |

Classic systemd services and the upstream update path remain available at every
increment. No later capability is implied by the v0.1 metadata schema.
