#!/usr/bin/python3
"""Small read-only MCP stdio server, pinned to protocol 2025-11-25."""
# SPDX-License-Identifier: Apache-2.0
import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import ADMIN, VENDOR, definition, require, settings

VERSION = '2025-11-25'
LIMIT = 65536
DESCRIPTIONS = {
    'system.snapshot': 'Read uptime, memory information and / and /var capacity. No arguments.',
    'system.failed_units': 'List failed systemd services. No arguments.',
    'system.unit_status': 'Read selected status properties of one named .service unit.',
    'system.bootc_status': 'Read local bootc deployment status; does not check a remote registry.',
    'system.update_timer': 'Read state of the existing bootc automatic-update timer.',
}


def tool_schema(name):
    schema = {'type': 'object', 'properties': {}, 'additionalProperties': False}
    if name == 'system.unit_status':
        schema['properties'] = {'unit': {'type': 'string', 'maxLength': 128,
                                        'pattern': r'^[a-zA-Z0-9][a-zA-Z0-9_.@:-]*\.service$'}}
        schema['required'] = ['unit']
    return {'name': name, 'description': DESCRIPTIONS[name], 'inputSchema': schema,
            'annotations': {'readOnlyHint': True, 'destructiveHint': False,
                            'openWorldHint': False}}


def command(argv):
    try:
        result = subprocess.run(argv, stdin=subprocess.DEVNULL, capture_output=True,
                                timeout=8, env={'PATH': '/usr/bin:/bin', 'LANG': 'C',
                                                'SYSTEMD_PAGER': 'cat', 'SYSTEMD_COLORS': '0'})
        return {'exit_code': result.returncode,
                'stdout': result.stdout[:8192].decode('utf-8', errors='replace'),
                'stderr': result.stderr[:2048].decode('utf-8', errors='replace'),
                'truncated': len(result.stdout) > 8192 or len(result.stderr) > 2048}
    except (OSError, subprocess.TimeoutExpired) as error:
        return {'error': str(error)}


def execute(name, arguments):
    require(isinstance(arguments, dict), 'arguments must be an object')
    if name == 'system.unit_status':
        require(set(arguments) == {'unit'}, 'unit is the only accepted argument')
        unit = arguments['unit']
        require(isinstance(unit, str) and len(unit) <= 128 and
                re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_.@:-]*\.service', unit), 'invalid service name')
        return command(['/usr/bin/systemctl', '--no-pager', 'show', unit,
                        '--property=Id,LoadState,ActiveState,SubState,Result,ExecMainStatus'])
    require(not arguments, 'this tool accepts no arguments')
    if name == 'system.snapshot':
        disks = {}
        for path in ('/', '/var'):
            st = os.statvfs(path)
            disks[path] = {'total_bytes': st.f_blocks * st.f_frsize,
                           'available_bytes': st.f_bavail * st.f_frsize}
        return {'scope': 'kernel and filesystems visible inside the agent systemd sandbox',
                'uptime_seconds': float(Path('/proc/uptime').read_text().split()[0]),
                'meminfo': Path('/proc/meminfo').read_text()[:8192], 'filesystems': disks}
    if name == 'system.failed_units':
        return command(['/usr/bin/systemctl', '--no-pager', '--plain', '--no-legend',
                        '--failed', '--type=service'])
    if name == 'system.bootc_status':
        return command(['/usr/bin/bootc', 'status', '--json'])
    if name == 'system.update_timer':
        return command(['/usr/bin/systemctl', '--no-pager', 'show', 'bootc-fetch-apply-updates.timer',
                        '--property=Id,LoadState,ActiveState,SubState,UnitFileState,NextElapseUSecRealtime'])
    raise ValueError('unknown tool')


class Server:
    def __init__(self, allowed):
        require(set(allowed) <= set(DESCRIPTIONS), 'unknown policy tool')
        self.allowed = set(allowed)
        self.initialized = False
        self.ready = False

    def handle(self, request):
        ident = request.get('id') if isinstance(request, dict) else None
        try:
            require(isinstance(request, dict) and request.get('jsonrpc') == '2.0'
                    and isinstance(request.get('method'), str), 'invalid request')
            method, params = request['method'], request.get('params', {})
            require(isinstance(params, dict), 'params must be an object')
            if method == 'notifications/initialized' and 'id' not in request:
                self.ready = self.initialized
                return None
            if 'id' not in request:
                return None
            if method == 'initialize':
                self.initialized = True
                result = {'protocolVersion': VERSION, 'capabilities': {'tools': {}},
                          'serverInfo': {'name': 'horizon-weaver-system', 'version': '0.1.0'}}
            elif method == 'ping':
                result = {}
            elif not self.ready:
                raise ValueError('initialize and notifications/initialized required')
            elif method == 'tools/list':
                require(not params.get('cursor'), 'this server has no further pages')
                result = {'tools': [tool_schema(n) for n in sorted(self.allowed)]}
            elif method == 'tools/call':
                name = params.get('name')
                require(isinstance(name, str) and name in self.allowed, 'tool denied by policy')
                try:
                    value = execute(name, params.get('arguments', {}))
                    failed = 'error' in value or value.get('exit_code', 0) != 0
                    result = {'content': [{'type': 'text', 'text': json.dumps(value)}], 'isError': failed}
                except (OSError, ValueError) as error:
                    result = {'content': [{'type': 'text', 'text': str(error)}], 'isError': True}
            else:
                return {'jsonrpc': '2.0', 'id': ident,
                        'error': {'code': -32601, 'message': 'method not supported'}}
            return {'jsonrpc': '2.0', 'id': ident, 'result': result}
        except ValueError as error:
            return {'jsonrpc': '2.0', 'id': ident,
                    'error': {'code': -32602, 'message': str(error)}}


def serve(server):
    while True:
        line = sys.stdin.buffer.readline(LIMIT + 1)
        if not line:
            return
        if len(line) > LIMIT:
            raise ValueError('MCP message exceeds 64 KiB')
        try:
            response = server.handle(json.loads(line))
        except (json.JSONDecodeError, UnicodeDecodeError):
            response = {'jsonrpc': '2.0', 'id': None,
                        'error': {'code': -32700, 'message': 'invalid JSON'}}
        if response is not None:
            print(json.dumps(response), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('agent')
    parser.add_argument('--vendor', type=Path, default=VENDOR)
    parser.add_argument('--admin', type=Path, default=ADMIN)
    parser.add_argument('--trusted', action='store_true')
    args = parser.parse_args()
    try:
        cfg, policy = settings(args.vendor, args.admin, args.trusted)
        agent = definition(args.agent, cfg, policy, args.vendor, args.admin, args.trusted)
        require(cfg['enabled'] and agent['enabled'], 'agent is disabled')
        serve(Server(agent['allowed_tools']))
    except (OSError, ValueError) as error:
        print(f'Horizon Weaver MCP: {error}', file=sys.stderr)
        sys.exit(78)
