import beatpick
import unittest
from unittest.mock import patch
from pathlib import Path
import tempfile
import json
import yaml
from beatpick import cli


class ConfigurationTests(unittest.TestCase):
    def tearDown(self):
        cli.audio_io.SCRATCH_DIR = None

    def test_version_without_command(self):
        from importlib.metadata import version
        from io import StringIO
        with patch('sys.argv', ['beatpick', '--version']), patch('sys.stdout', new_callable=StringIO) as output:
            with self.assertRaises(SystemExit) as result:
                cli.main()
            self.assertEqual(result.exception.code, 0)
            self.assertEqual(output.getvalue().strip(), 'beatpick ' + version('beatpick'))

    def test_nested_filter(self):
        rule = {'all': [{'field': 'genre', 'equals': 'Trance'}, {'not': {'field': 'album', 'contains': 'Live'}}]}
        self.assertTrue(cli.matches(rule, dict(genre='TRANCE', album='Neon Horizon')))
        self.assertFalse(cli.matches(rule, dict(genre='Trance', album='Live at Moonbase')))

    def test_unknown_operator(self):
        with self.assertRaises(ValueError):
            cli.matches({'field': 'genre', 'typo': 'Trance'}, {})

    def test_run_stages_without_apply_and_cli_overrides_config(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            config = root / 'config.yaml'
            config.write_text(yaml.safe_dump(dict(state_dir='data', library=dict(media_root=str(root), select={'field': 'genre', 'equals': 'Trance'}), write_bpm=True)))
            rows = [dict(path=str(root / 'song.mp3'), genre='Trance')]
            with patch('sys.argv', ['beatpick', 'run', '--config', str(config), '--no-write-bpm']), patch.object(cli.subprocess, 'check_output', return_value=json.dumps(rows)), patch.object(cli.refresh, 'main'), patch.object(cli.metadata, 'plan', return_value={'rows': []}) as plan, patch.object(cli.metadata, 'apply') as apply:
                cli.main()
                plan.assert_called_once_with(root.resolve() / 'data', False, True, 'beatpick-duplicate')
                apply.assert_not_called()
                self.assertTrue((root / 'data/metadata-plan.json').exists())

    def test_selection_required_before_music_access(self):
        with tempfile.TemporaryDirectory() as temp, patch('sys.argv', ['beatpick', 'run', '--state-dir', temp]), patch.object(cli.subprocess, 'check_output') as music:
            with self.assertRaises(SystemExit):
                cli.main()
            music.assert_not_called()
