import ast
import json
import tempfile
import unittest
from pathlib import Path


class HTTPError(Exception):
    def __init__(self, status_code, detail):
        self.status_code = status_code


class EngineeringEndpointTest(unittest.TestCase):
    def endpoint(self, root):
        # Exercise the endpoint body independently of optional FastAPI installation.
        source = Path('controller/rca_ui_server.py').read_text()
        tree = ast.parse(source)
        function = next(n for n in tree.body if isinstance(n, ast.FunctionDef)
                        and n.name == 'get_engineering_case')
        function.decorator_list = []
        namespace = {'ARTIFACTS_DIR': root, 'HTTPException': HTTPError,
                     'Any': object, 'load_json_file': lambda p: json.loads(p.read_text())}
        exec(compile(ast.Module(body=[function], type_ignores=[]), source, 'exec'), namespace)
        return namespace['get_engineering_case']

    def test_reads_sidecar_without_changing_legacy_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            folder = root / 'baseline'
            folder.mkdir()
            legacy = folder / 'rca_ui_report.json'
            legacy.write_text('{"legacy": true}')
            sidecar = folder / 'engineering_rca_report.json'
            sidecar.write_text('{"engineering_assessment": {"source_coverage": "gaps_present"}}')
            before = legacy.read_bytes(), sidecar.read_bytes()
            result = self.endpoint(root)('baseline')
            self.assertEqual(result['engineering_assessment']['source_coverage'], 'gaps_present')
            self.assertEqual(before, (legacy.read_bytes(), sidecar.read_bytes()))

    def test_missing_invalid_and_traversal(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            get = self.endpoint(root)
            for run in ('missing', '../outside'):
                with self.assertRaises(HTTPError) as error:
                    get(run)
                self.assertEqual(error.exception.status_code, 404)
            folder = root / 'invalid'
            folder.mkdir()
            (folder / 'engineering_rca_report.json').write_text('[]')
            with self.assertRaises(HTTPError) as error:
                get('invalid')
            self.assertEqual(error.exception.status_code, 500)
