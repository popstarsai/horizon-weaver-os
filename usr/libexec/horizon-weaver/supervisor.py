#!/usr/bin/python3
"""Compile validated agent metadata into systemd timer units and drop-ins."""
# SPDX-License-Identifier: Apache-2.0
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import ADMIN, VENDOR, discover


def generate(output, cfg, agents):
    # Validation of the entire set happens before any units are written.
    if not cfg['enabled']:
        return
    for agent in agents:
        if not agent['enabled']:
            continue
        name = agent['name']
        service = f'horizon-weaver-agent@{name}.service'
        timer = f'horizon-weaver-agent-{name}.timer'
        dropin = output / f'{service}.d'
        dropin.mkdir(parents=True, exist_ok=True)
        (dropin / '50-definition.conf').write_text(
            '# Generated from the agent Markdown; edit /etc/horizon-weaver instead.\n'
            f'[Service]\nRestart={agent["restart"]}\nRestartSec={agent["restart_sec"]}\n'
            f'RuntimeMaxSec={cfg["runtime_sec"]}\n', encoding='utf-8')
        (output / timer).write_text(
            f'[Unit]\nDescription=Schedule Horizon Weaver {name}\nPartOf=horizon-weaver.target\n'
            '[Timer]\nOnActiveSec=30\n'
            f'OnUnitInactiveSec={agent["interval_sec"]}\nRandomizedDelaySec=30\n'
            f'Unit={service}\n', encoding='utf-8')
        wants = output / 'horizon-weaver.target.wants'
        wants.mkdir(exist_ok=True)
        (wants / timer).symlink_to(f'../{timer}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--vendor', type=Path, default=VENDOR)
    parser.add_argument('--admin', type=Path, default=ADMIN)
    parser.add_argument('--generate', type=Path)
    parser.add_argument('--trusted', action='store_true')
    args = parser.parse_args()
    cfg, agents = discover(args.vendor, args.admin, args.trusted)
    if args.generate:
        generate(args.generate, cfg, agents)
    else:
        for agent in agents:
            state = 'enabled' if cfg['enabled'] and agent['enabled'] else 'disabled'
            print(f'{agent["name"]}: {state}, {agent["model"]}, {agent["isolation"]}')


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError) as error:
        print(f'Horizon Weaver: {error}', file=sys.stderr)
        sys.exit(78)
