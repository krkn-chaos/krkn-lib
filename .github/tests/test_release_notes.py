import json
import os
from pathlib import Path
import subprocess
import tempfile
import textwrap
import unittest


WORKFLOW = Path(__file__).resolve().parents[1] / 'workflows' / 'release.yml'


def step_script(name, context):
    step = WORKFLOW.read_text().split(f'      - name: {name}\n', 1)[1].split('\n      - name:', 1)[0]
    script = textwrap.dedent(step.split('        run: |\n', 1)[1])
    for expr, value in context.items():
        script = script.replace(expr, value)
    return script


class ReleaseNotesTest(unittest.TestCase):
    def test_notes_and_tag_are_treated_as_data(self):
        notes = 'Change $(printf NOTES_EXECUTED >&2) & more\nEOF\nAFTER=value'
        tag = 'v1$(printf${IFS}TAG_EXECUTED>&2)'
        script = step_script('replace placeholders in template', {
            '${{ env.NOTES }}': notes, '${{ github.ref_name }}': tag,
        })
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / '.github').mkdir()
            (root / '.github' / 'release-template.md').write_text('Version: {VERSION}\n{CHANGES}\n')
            (root / 'generated-release-notes.md').write_text(notes)
            env = {**os.environ, 'RUNNER_TEMP': directory, 'GITHUB_REF_NAME': tag}
            result = subprocess.run(['bash', '-e', '-o', 'pipefail', '-c', script],
                                    cwd=root, env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertNotIn('NOTES_EXECUTED', result.stderr)
            self.assertNotIn('TAG_EXECUTED', result.stderr)
            self.assertEqual((root / 'release-notes.md').read_text(), f'Version: {tag}\n{notes}\n')

    def test_generated_notes_are_written_to_a_file(self):
        notes = 'First line\nEOF\nUNRELATED_VARIABLE=value'
        script = step_script('generate release notes from template', {
            '${{ github.ref_name }}': 'v1', '${{ env.PREVIOUS_TAG }}': 'v0',
        })
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            gh = root / 'gh'
            gh.write_text('#!/bin/sh\nprintf "%s\\n" "$TEST_GH_RESPONSE"\n')
            gh.chmod(0o755)
            env = {**os.environ, 'PATH': f'{directory}:{os.environ["PATH"]}',
                   'RUNNER_TEMP': directory, 'GITHUB_ENV': str(root / 'github-env'),
                   'GITHUB_REF_NAME': 'v1', 'PREVIOUS_TAG': 'v0',
                   'TEST_GH_RESPONSE': json.dumps({'body': notes})}
            result = subprocess.run(['bash', '-e', '-o', 'pipefail', '-c', script],
                                    cwd=root, env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((root / 'generated-release-notes.md').exists())
            self.assertEqual((root / 'generated-release-notes.md').read_text().rstrip('\n'), notes)
            self.assertFalse((root / 'github-env').exists())


if __name__ == '__main__':
    unittest.main()
