import os
from pathlib import Path
import re
import subprocess
import tempfile
import textwrap
import unittest


WORKFLOW = Path(__file__).resolve().parents[1] / 'workflows' / 'build.yaml'


def step(name):
    return WORKFLOW.read_text().split(f'      - name: {name}\n', 1)[1].split('\n      - name:', 1)[0]


def runs_for(name, event, secret_exists=True):
    condition = re.search(r'^        if: (.+)$', step(name), re.MULTILINE)
    if not condition:
        return True
    parts = [p.strip() for p in condition.group(1).split('&&')]
    result = True
    for part in parts:
        if part == "github.event_name == 'push'":
            result = result and event == 'push'
        elif part == "needs.check-secret.outputs.my-key-exists == 'true'":
            result = result and secret_exists
        else:
            raise AssertionError(f'Unexpected condition: {part}')
    return result


class BuildSecurityTest(unittest.TestCase):
    def test_aws_secret_checks_and_tests_do_not_run_for_prs(self):
        for name in ['Check for Secret availability', 'Run AWS specific tests with coverage']:
            with self.subTest(step=name):
                self.assertFalse(runs_for(name, 'pull_request'))
                self.assertTrue(runs_for(name, 'push'))
        self.assertFalse(runs_for('Run AWS specific tests with coverage', 'push', False))

    def test_version_ref_is_data(self):
        tag = 'v1$(printf${IFS}VERSION_EXECUTED>&2)'
        source = step('Fetch version number')
        script = textwrap.dedent(source.split('        run: |\n', 1)[1])
        script = script.replace('${{ github.ref_name }}', tag)
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'env'
            result = subprocess.run(['bash', '-e', '-o', 'pipefail', '-c', script],
                                    env={**os.environ, 'GITHUB_REF_NAME': tag, 'GITHUB_ENV': str(output)},
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertNotIn('VERSION_EXECUTED', result.stderr)
            self.assertEqual(output.read_text(), f'NEXT_VERSION={tag[1:]}\n')

    def test_version_replacement_is_data(self):
        version = '1$(printf${IFS}VERSION_EXECUTED>&2)'
        source = step('Update version number')
        script = textwrap.dedent(source.split('        run: |\n', 1)[1])
        script = script.replace('${{ env.NEXT_VERSION }}', version)
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / 'pyproject.toml'
            config.write_text('version = "0.0.0"\n')
            result = subprocess.run(['bash', '-e', '-o', 'pipefail', '-c', script],
                                    cwd=directory, env={**os.environ, 'NEXT_VERSION': version},
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertNotIn('VERSION_EXECUTED', result.stderr)
            self.assertEqual(config.read_text(), f'version = "{version}"\n')


if __name__ == '__main__':
    unittest.main()
