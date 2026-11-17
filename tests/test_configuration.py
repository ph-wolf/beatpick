import beatpick
import argparse
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import yaml
from beatpick import cli
import configuration


def args(**changes):
    values=dict(config=None,no_config=False,select=None,all=False,command='run',json=False)
    return argparse.Namespace(**(values | changes))


class FirstRunTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name).resolve()
        self.work=self.root/'work';self.work.mkdir()
        self.audio=self.root/'audio';self.audio.mkdir()
        self.home_patch=patch.object(Path,'home',return_value=self.root)
        self.cwd_patch=patch.object(Path,'cwd',return_value=self.work)
        self.home_patch.start();self.cwd_patch.start()

    def tearDown(self):
        self.home_patch.stop();self.cwd_patch.stop()
        cli.audio_io.SCRATCH_DIR=None
        self.temp.cleanup()

    def test_discovery_precedence_and_no_overwrite(self):
        personal=self.root/'.beatpick/config.yaml';personal.parent.mkdir();personal.write_text('write_bpm: true\n')
        self.assertEqual(configuration.locate(args()),personal)
        local=self.work/'config.yaml';local.write_text('write_bpm: false\n')
        self.assertEqual(configuration.locate(args()),local)
        explicit=self.root/'custom.yaml'
        self.assertEqual(configuration.locate(args(config=explicit)),explicit)
        self.assertIsNone(configuration.locate(args(no_config=True)))
        self.assertEqual(personal.read_text(),'write_bpm: true\n')

    def test_noninteractive_and_json_never_prompt(self):
        for setting in (args(),args(json=True),args(command='apply')):
            with patch.object(configuration.sys.stdin,'isatty',return_value=False), patch('builtins.input') as prompt:
                with self.assertRaisesRegex(ValueError,'No configuration found'):
                    configuration.locate(setting)
                prompt.assert_not_called()
        with patch.object(configuration.sys.stdin,'isatty',return_value=True),patch('builtins.input') as prompt:
            with self.assertRaises(ValueError):configuration.locate(args(json=True))
            prompt.assert_not_called()
        self.assertFalse((self.root/'.beatpick').exists())

    def test_cli_selection_needs_no_setup(self):
        self.assertIsNone(configuration.locate(args(select='{field: genre, equals: Trance}')))
        self.assertIsNone(configuration.locate(args(all=True)))
        self.assertFalse((self.root/'.beatpick').exists())

    def test_first_run_continues_analysis_without_apply(self):
        answers=[str(self.audio),'genre','Trance','','','','','no']
        rows=[dict(path=str(self.audio/'track.mp3'),genre='Trance')]
        with patch('sys.argv',['beatpick','run']),patch.object(configuration.sys.stdin,'isatty',return_value=True),patch('builtins.input',side_effect=answers),patch.object(cli.subprocess,'check_output',return_value=json.dumps(rows)),patch.object(cli.refresh,'main') as analysis,patch.object(cli.metadata,'plan',return_value={'rows':[]}),patch.object(cli.metadata,'apply') as apply:
            cli.main()
            analysis.assert_called_once()
            apply.assert_not_called()
        dest=self.root/'.beatpick/config.yaml';config=yaml.safe_load(dest.read_text())
        self.assertEqual(config['library']['select'],{'field':'genre','equals':'Trance'})
        self.assertEqual(config['analysis']['bpm_min'],165)
        self.assertFalse(config['write_bpm']);self.assertFalse(config['duplicates']['enabled'])
        self.assertEqual(dest.stat().st_mode & 0o777,0o600)
        self.assertTrue((self.root/'.beatpick/data/metadata-plan.json').exists())

    def test_all_is_persisted_and_can_be_reused(self):
        dest=self.root/'.beatpick/config.yaml'
        with patch('builtins.input',side_effect=[str(self.audio),'all','','','','','']):
            configuration.first_run(dest)
        data=yaml.safe_load(dest.read_text())
        self.assertTrue(data['library']['all']);self.assertNotIn('select',data['library'])
        with patch('sys.argv',['beatpick','run']),patch.object(cli.subprocess,'check_output',return_value=json.dumps([dict(path=str(self.audio/'track.mp3'))])),patch.object(cli.refresh,'main') as analysis,patch.object(cli.metadata,'plan',return_value={'rows':[]}):
            cli.main();analysis.assert_called_once()

    def test_cancellation_leaves_no_config(self):
        dest=self.root/'.beatpick/config.yaml'
        with patch('builtins.input',side_effect=EOFError):
            with self.assertRaises(EOFError):configuration.first_run(dest)
        self.assertFalse(dest.exists())

    def test_racing_configuration_is_not_overwritten(self):
        dest=self.root/'.beatpick/config.yaml';dest.parent.mkdir();dest.write_text('existing: true\n')
        with patch('builtins.input',side_effect=[str(self.audio),'all','','','','','']):
            with self.assertRaisesRegex(ValueError,'not overwritten'):configuration.first_run(dest)
        self.assertEqual(dest.read_text(),'existing: true\n')

    def test_invalid_inputs_are_retried_before_saving(self):
        dest=self.root/'.beatpick/config.yaml'
        inputs=[str(self.root/'missing'),str(self.audio),'wrong','album','','Neon Horizon','NaN','165','100','185','0','50','perhaps','no','no']
        with patch('builtins.input',side_effect=inputs):configuration.first_run(dest)
        config=yaml.safe_load(dest.read_text())
        self.assertEqual(config['library']['select']['contains'],'Neon Horizon')
        self.assertEqual(config['analysis']['coverage_percent'],50)

    def test_incomplete_cli_only_call_creates_no_state(self):
        with patch('sys.argv',['beatpick','run','--no-config']),patch.object(cli.subprocess,'check_output') as music:
            with self.assertRaises(SystemExit):cli.main()
            music.assert_not_called()
        self.assertFalse((self.work/'data').exists())
        self.assertFalse((self.root/'.beatpick').exists())
