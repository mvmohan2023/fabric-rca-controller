"""Exercise real parser code without importing hardware/stress dependencies."""
import argparse
import ast
from contextlib import redirect_stdout, redirect_stderr
import io
from pathlib import Path
import sys
import unittest
from unittest.mock import patch


class ScopedRunnerOptionsTest(unittest.TestCase):
    def parse(self, options):
        source = Path('controller/fault_injection_runner.py').read_text()
        tree = ast.parse(source)
        names = {'parse_args', 'normalize_phase_timing_args'}
        selected = [node for node in tree.body if isinstance(node, ast.FunctionDef)
                    and node.name in names]
        namespace = {'argparse': argparse, 'SCENARIOS': {'normal_baseline_no_churn': {}},
                     'SUITES': {'production_basic': []}, 'DEFAULT_IXIA_INVENTORY': 'ixia.json',
                     'DEFAULT_TOPOLOGY': 'topology.json', 'DEFAULT_UI_SERVER': 'http://localhost:8080'}
        exec(compile(ast.Module(body=selected, type_ignores=[]), source, 'exec'), namespace)
        common = ['--src', 'src', '--dst', 'dst', '--intent-name', 'baseline', '--nodes', 'leaf1']
        with patch.object(sys, 'argv', ['runner'] + common + options), redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            return namespace['parse_args']()

    def test_existing_cli_defaults_unchanged(self):
        args = self.parse(['--scenario', 'normal_baseline_no_churn', '--rca-run-id', 'offline'])
        self.assertFalse(args.collect_scoped_fabric_evidence)

    def test_single_scenario_opt_in(self):
        args = self.parse(['--scenario', 'normal_baseline_no_churn', '--rca-run-id', 'offline',
                           '--collect-scoped-fabric-evidence'])
        self.assertTrue(args.collect_scoped_fabric_evidence)

    def test_suite_option_is_explicitly_rejected(self):
        with self.assertRaises(SystemExit) as error:
            self.parse(['--suite', 'production_basic', '--collect-scoped-fabric-evidence'])
        self.assertEqual(error.exception.code, 2)

    def test_existing_suite_without_option_still_parses(self):
        args = self.parse(['--suite', 'production_basic'])
        self.assertFalse(args.collect_scoped_fabric_evidence)
