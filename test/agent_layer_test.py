#!/usr/bin/env python3
"""Offline boundary and integration tests; no model, root, Docker or bootc needed."""
# SPDX-License-Identifier: Apache-2.0
import copy
import json
import os
import shutil
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / 'usr/libexec/horizon-weaver'
sys.path.insert(0, str(RUNTIME))
import agent
import config
import mcp
import supervisor


class Definitions(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.vendor = self.root / 'vendor'
        self.admin = self.root / 'admin'
        shutil.copytree(ROOT / 'usr/share/horizon-weaver', self.vendor)
        self.admin.mkdir()

    def load(self):
        return config.discover(self.vendor, self.admin)

    def enable(self):
        path = self.vendor / 'supervisor.toml'
        path.write_text(path.read_text().replace('enabled = false', 'enabled = true'))

    def test_examples_and_skills_validate_disabled_by_default(self):
        cfg, agents = self.load()
        self.assertFalse(cfg['enabled'])
        self.assertEqual({a['name'] for a in agents}, {'system-health', 'update-advisor'})
        self.assertIn('Evidence first', agents[0]['instructions'])

    def test_disabled_supervisor_generates_nothing(self):
        output = self.root / 'out'
        output.mkdir()
        supervisor.generate(output, *self.load())
        self.assertEqual(list(output.iterdir()), [])

    def test_admin_override_disables_one_and_generator_maps_restart(self):
        self.enable()
        (self.admin / 'agents').mkdir()
        source = self.vendor / 'agents/update-advisor.md'
        (self.admin / 'agents/update-advisor.md').write_text(source.read_text().replace('enabled = true', 'enabled = false'))
        output = self.root / 'out'
        output.mkdir()
        supervisor.generate(output, *self.load())
        self.assertTrue((output / 'horizon-weaver.target.wants/horizon-weaver-agent-system-health.timer').exists())
        self.assertFalse((output / 'horizon-weaver-agent-update-advisor.timer').exists())
        text = (output / 'horizon-weaver-agent@system-health.service.d/50-definition.conf').read_text()
        self.assertIn('Restart=on-failure\nRestartSec=60\nRuntimeMaxSec=300', text)

    def test_reject_injected_or_unsupported_metadata(self):
        path = self.vendor / 'agents/system-health.md'
        original = path.read_text()
        changes = [
            ('systemd-read-only', 'docker-privileged'),
            ('/var/lib/horizon-weaver/system-health', '/etc'),
            ('skills = ["evidence-first", "service-triage"]', 'skills = ["../secrets"]'),
            ('"system.snapshot"', '"shell.exec"'),
            ('restart = "on-failure"', 'restart = "always"'),
            ('model = "horizon-local"', 'model = "remote-secret-route"'),
            ('max_steps = 6', 'max_steps = 100'),
            ('schema_version = 1', 'schema_version = true'),
        ]
        for before, after in changes:
            with self.subTest(after=after):
                path.write_text(original.replace(before, after))
                with self.assertRaises(ValueError):
                    self.load()
        path.write_text(original)

    def test_symlink_override_and_bad_filename_fail_closed(self):
        (self.admin / 'agents').mkdir()
        (self.admin / 'agents/system-health.md').symlink_to(self.vendor / 'agents/system-health.md')
        with self.assertRaises(ValueError):
            self.load()
        (self.admin / 'agents/system-health.md').unlink()
        (self.admin / 'agents/bad name.md').write_text('bad')
        with self.assertRaises(ValueError):
            self.load()

    def test_policy_removal_cannot_be_overridden_by_markdown(self):
        path = self.vendor / 'mcp.toml'
        path.write_text(path.read_text().replace('"system.snapshot", ', ''))
        with self.assertRaisesRegex(ValueError, 'not permitted'):
            self.load()

    def test_real_stdio_discovery_call_and_denial(self):
        self.enable()
        client = agent.MCP([sys.executable, '-I', str(RUNTIME / 'mcp.py'), 'system-health',
                            '--vendor', str(self.vendor), '--admin', str(self.admin)])
        self.addCleanup(client.close)
        client.initialize()
        names = {tool['name'] for tool in client.call('tools/list')['tools']}
        self.assertEqual(names, {'system.snapshot', 'system.failed_units', 'system.unit_status'})
        result = client.call('tools/call', {'name': 'system.snapshot', 'arguments': {}})
        self.assertFalse(result['isError'])
        self.assertIn('uptime_seconds', json.loads(result['content'][0]['text']))
        with self.assertRaisesRegex(ValueError, 'rejected'):
            client.call('tools/call', {'name': 'system.bootc_status', 'arguments': {}})
        invalid = client.call('tools/call', {'name': 'system.unit_status', 'arguments': {'unit': '; reboot'}})
        self.assertTrue(invalid['isError'])

    def test_adaptive_loop_with_real_mcp_and_observation_driven_model_fixture(self):
        self.enable()
        cfg, agents = self.load()
        health = next(a for a in agents if a['name'] == 'system-health')
        client = agent.MCP([sys.executable, '-I', str(RUNTIME / 'mcp.py'), 'system-health',
                            '--vendor', str(self.vendor), '--admin', str(self.admin)])
        self.addCleanup(client.close)
        def complete(messages):
            if len(messages) == 2:
                return json.dumps({'plan': ['Read current resources', 'Adapt diagnosis'], 'action': 'tool',
                                   'tool': 'system.snapshot', 'arguments': {}})
            self.assertIn('uptime_seconds', messages[-1]['content'])
            return json.dumps({'plan': ['Current observation obtained', 'Report limited findings'],
                               'action': 'finish', 'report': 'Snapshot received; no changes performed.'})
        result = agent.loop(health, client, complete)
        self.assertEqual(result['status'], 'complete')
        self.assertEqual(len(result['events']), 2)
        self.assertNotEqual(result['events'][0]['decision']['plan'], result['events'][1]['decision']['plan'])


class Protocol(unittest.TestCase):
    def test_negotiation_and_unsupported_methods(self):
        server = mcp.Server(['system.snapshot'])
        def call(method, params=None):
            return server.handle({'jsonrpc': '2.0', 'id': 1, 'method': method, 'params': params or {}})
        self.assertIn('error', call('tools/list'))
        self.assertEqual(call('initialize', {'protocolVersion': 'future'})['result']['protocolVersion'], mcp.VERSION)
        self.assertIn('error', call('tools/list'))
        self.assertIsNone(server.handle({'jsonrpc': '2.0', 'method': 'notifications/initialized'}))
        self.assertIn('tools', call('tools/list')['result'])
        self.assertEqual(call('arbitrary/method')['error']['code'], -32601)

    def test_server_denies_before_tool_execution(self):
        server = mcp.Server(['system.snapshot'])
        server.ready = True
        with patch.object(mcp, 'execute') as execute:
            response = server.handle({'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call',
                                      'params': {'name': 'system.bootc_status'}})
            self.assertIn('error', response)
            execute.assert_not_called()

    def test_arguments_cannot_be_commands(self):
        with patch.object(mcp, 'command') as run:
            for value in ['--help', 'docker.service;reboot', '../a.service', 'a.service\nExecStart=/bin/sh']:
                with self.assertRaises(ValueError):
                    mcp.execute('system.unit_status', {'unit': value})
            with self.assertRaises(ValueError):
                mcp.execute('system.snapshot', {'command': 'reboot'})
            run.assert_not_called()
        with patch.object(mcp, 'command', return_value={}) as run:
            mcp.execute('system.unit_status', {'unit': 'sshd.service'})
            self.assertIn('sshd.service', run.call_args.args[0])

    def test_nonzero_tool_result_is_error(self):
        server = mcp.Server(['system.bootc_status'])
        server.ready = True
        with patch.object(mcp, 'command', return_value={'exit_code': 1, 'stderr': 'permission denied'}):
            response = server.handle({'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call',
                                      'params': {'name': 'system.bootc_status', 'arguments': {}}})
        self.assertTrue(response['result']['isError'])


class FakeMCP:
    def __init__(self):
        self.calls = []
    def initialize(self):
        pass
    def call(self, method, params=None):
        self.calls.append((method, params))
        return {'tools': [mcp.tool_schema('system.snapshot')]} if method == 'tools/list' else {'isError': False}


class Runtime(unittest.TestCase):
    def setUp(self):
        self.definition = {'name': 'test', 'goals': ['test'], 'instructions': 'test',
                           'allowed_tools': ['system.snapshot'], 'max_steps': 2}

    def test_disallowed_model_tool_never_reaches_mcp(self):
        client = FakeMCP()
        invalid = json.dumps({'plan': ['Run a command'], 'action': 'tool', 'tool': 'shell.exec', 'arguments': {}})
        result = agent.loop(self.definition, client, lambda _: invalid)
        self.assertEqual(result['status'], 'budget-exhausted')
        self.assertEqual([method for method, _ in client.calls], ['tools/list'])
        self.assertIn('denied', result['events'][0]['observation']['error'])

    def test_malformed_model_responses_are_bounded_and_recoverable(self):
        responses = iter(['not json',
                          json.dumps({'plan': ['Observe'], 'action': 'tool', 'tool': 'system.snapshot', 'arguments': {}}),
                          json.dumps({'plan': ['Report uncertainty'], 'action': 'finish', 'report': 'Unknown.'})])
        result = agent.loop({**self.definition, 'max_steps': 3}, FakeMCP(), lambda _: next(responses))
        self.assertEqual(result['status'], 'complete')
        result = agent.loop(self.definition, FakeMCP(), lambda _: 'not json')
        self.assertEqual(result['status'], 'budget-exhausted')
        self.assertEqual(len(result['events']), 2)

    def test_cannot_complete_without_observing_a_tool(self):
        finish = json.dumps({'plan': ['Report'], 'action': 'finish', 'report': 'Healthy.'})
        result = agent.loop(self.definition, FakeMCP(), lambda _: finish)
        self.assertEqual(result['status'], 'budget-exhausted')
        self.assertIn('Observe', result['events'][0]['observation']['error'])

    def test_policy_mismatch_stops_before_inference(self):
        definition = copy.deepcopy(self.definition)
        definition['allowed_tools'].append('system.bootc_status')
        with patch('builtins.print'), self.assertRaisesRegex(ValueError, 'disagree'):
            agent.loop(definition, FakeMCP(), lambda _: self.fail('should not infer'))

    def test_report_replacement_and_private_mode(self):
        with tempfile.TemporaryDirectory() as directory:
            memory = Path(directory)
            agent.save(memory, {'status': 'complete', 'report': 'old'})
            agent.save(memory, {'status': 'running', 'report': 'new'})
            self.assertEqual(json.loads((memory / 'latest.json').read_text())['status'], 'running')
            self.assertEqual((memory / 'latest.json').stat().st_mode & 0o777, 0o600)
            self.assertEqual(len(list(memory.iterdir())), 1)

    def test_http_gateway_alias_and_no_redirect_credentials(self):
        seen = []
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass
            def do_POST(self):
                seen.append((self.path, json.loads(self.rfile.read(int(self.headers['Content-Length'])))))
                if self.path == '/redirect':
                    self.send_response(302)
                    self.send_header('Location', '/stolen')
                    self.end_headers()
                else:
                    self.send_response(200)
                    self.end_headers()
                    self.wfile.write(json.dumps({'choices': [{'message': {'content': 'result'}}]}).encode())
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            base = f'http://127.0.0.1:{server.server_port}'
            self.assertEqual(agent.infer(base + '/v1/chat/completions', 'fake-test-key', 'horizon-local', []), 'result')
            self.assertEqual(seen[0][1]['model'], 'horizon-local')
            with self.assertRaisesRegex(ValueError, 'redirects'):
                agent.infer(base + '/redirect', 'fake-test-key', 'horizon-local', [])
            self.assertEqual(len(seen), 2)
        finally:
            server.shutdown()
            server.server_close()
            thread.join()


if __name__ == '__main__':
    unittest.main()
