"""Horizon Weaver v1 definitions. Standard library only; no executable Markdown."""
# SPDX-License-Identifier: Apache-2.0
import re
import tomllib
from pathlib import Path

VENDOR = Path('/usr/share/horizon-weaver')
ADMIN = Path('/etc/horizon-weaver')
SLUG = re.compile(r'[a-z][a-z0-9-]{0,23}\Z')
TOOLS = {'system.snapshot', 'system.failed_units', 'system.unit_status',
         'system.bootc_status', 'system.update_timer'}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read(path, trusted=False):
    require(not path.is_symlink(), f'{path}: symlinks are not supported')
    if trusted:
        for item in (path, *path.parents):
            st = item.stat()
            require(st.st_uid == 0 and not st.st_mode & 0o022,
                    f'{item}: must be root-owned and not group/world writable')
    require(path.stat().st_size <= 65536, f'{path}: exceeds 64 KiB')
    return path.read_text(encoding='utf-8')


def selected(relative, vendor=VENDOR, admin=ADMIN):
    override = admin / relative
    return override if override.exists() or override.is_symlink() else vendor / relative


def integer(value, low, high, name):
    require(type(value) is int and low <= value <= high, f'invalid {name}')


def strings(value, name):
    require(isinstance(value, list) and value and
            all(isinstance(v, str) and v.strip() for v in value), f'invalid {name}')
    require(len(value) == len(set(value)), f'duplicate {name}')


def settings(vendor=VENDOR, admin=ADMIN, trusted=False):
    cfg = tomllib.loads(read(selected('supervisor.toml', vendor, admin), trusted))
    require(set(cfg) == {'schema_version', 'enabled', 'max_steps', 'runtime_sec',
                         'gateway_url', 'allowed_models'}, 'unknown/missing supervisor fields')
    require(type(cfg['schema_version']) is int and cfg['schema_version'] == 1,
            'unsupported supervisor schema')
    require(type(cfg['enabled']) is bool, 'enabled must be boolean')
    integer(cfg['max_steps'], 1, 16, 'max_steps')
    integer(cfg['runtime_sec'], 30, 900, 'runtime_sec')
    # Keep provider credentials and routing in the gateway, never in Markdown.
    require(cfg['gateway_url'] == 'http://127.0.0.1:4000/v1/chat/completions',
            'v1 supports only the loopback gateway on port 4000')
    strings(cfg['allowed_models'], 'allowed_models')
    require(all(re.fullmatch(r'[a-z][a-z0-9-]{0,63}', m) for m in cfg['allowed_models']),
            'models must be gateway aliases')
    mcp = tomllib.loads(read(selected('mcp.toml', vendor, admin), trusted))
    require(set(mcp) == {'schema_version', 'protocol_version', 'allowed_tools'},
            'unknown/missing MCP fields')
    require(type(mcp['schema_version']) is int and mcp['schema_version'] == 1,
            'unsupported MCP schema')
    require(mcp['protocol_version'] == '2025-11-25', 'unsupported MCP protocol')
    strings(mcp['allowed_tools'], 'MCP allowed_tools')
    require(set(mcp['allowed_tools']) <= TOOLS, 'unknown MCP tool')
    return cfg, mcp


def definition(name, cfg, mcp, vendor=VENDOR, admin=ADMIN, trusted=False):
    require(isinstance(name, str) and SLUG.fullmatch(name), 'invalid agent name')
    text = read(selected(f'agents/{name}.md', vendor, admin), trusted)
    require(text.startswith('```toml\n'), f'{name}: first block must be TOML')
    metadata, separator, body = text[8:].partition('\n```\n')
    require(separator and body.strip(), f'{name}: missing Markdown instructions')
    agent = tomllib.loads(metadata)
    fields = {'schema_version', 'name', 'enabled', 'goals', 'skills', 'allowed_tools',
              'memory', 'isolation', 'restart', 'restart_sec', 'interval_sec',
              'max_steps', 'model'}
    require(set(agent) == fields, f'{name}: unknown/missing definition fields')
    require(type(agent['schema_version']) is int and agent['schema_version'] == 1,
            f'{name}: unsupported schema')
    require(agent['name'] == name, f'{name}: filename/name mismatch')
    require(type(agent['enabled']) is bool, f'{name}: enabled must be boolean')
    for key in ('goals', 'skills', 'allowed_tools'):
        strings(agent[key], key)
    require(set(agent['allowed_tools']) <= set(mcp['allowed_tools']),
            f'{name}: tool not permitted by MCP policy')
    require(agent['memory'] == f'/var/lib/horizon-weaver/{name}',
            f'{name}: memory must use the per-agent StateDirectory')
    require(agent['isolation'] == 'systemd-read-only', f'{name}: unsupported isolation')
    require(agent['restart'] in ('no', 'on-failure'), f'{name}: unsupported restart')
    integer(agent['restart_sec'], 30, 3600, 'restart_sec')
    integer(agent['interval_sec'], 300, 86400, 'interval_sec')
    integer(agent['max_steps'], 1, cfg['max_steps'], 'max_steps')
    require(agent['model'] in cfg['allowed_models'], f'{name}: model not permitted')
    skills = []
    for skill in agent['skills']:
        require(SLUG.fullmatch(skill), f'{name}: invalid skill name')
        skills.append(read(selected(f'skills/{skill}.md', vendor, admin), trusted))
    agent['instructions'] = body.strip() + '\n\n' + '\n\n'.join(skills)
    return agent


def discover(vendor=VENDOR, admin=ADMIN, trusted=False):
    cfg, mcp = settings(vendor, admin, trusted)
    names = sorted({p.stem for root in (vendor, admin) for p in (root / 'agents').glob('*.md')})
    agents = [definition(n, cfg, mcp, vendor, admin, trusted) for n in names]
    return cfg, agents
