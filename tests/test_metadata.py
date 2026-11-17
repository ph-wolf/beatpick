import beatpick
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
import recordings
import metadata as m
from refresh import METHOD_VERSION, identity, write_json

class MetadataTests(unittest.TestCase):
    def fixture(self, root):
        audio=root/'audio';audio.write_bytes(b'fixture')
        common=dict(artist='Artist',album='Neon Horizon Test',path=str(audio),duration=40.,passes=True)
        rows=[dict(common,persistent_id='AAAAAAAAAAAAAAAA',title='Song',bpm=180.,target_percent=60.),
              dict(common,persistent_id='BBBBBBBBBBBBBBBB',title='Other spelling',bpm=170.54,target_percent=80.),
              dict(common,persistent_id='CCCCCCCCCCCCCCCC',title='Song (Remix)',bpm=175.,target_percent=90.)]
        for row in rows:
            row['analysis_file_signature']=identity(row)
        write_json(root/'pending.json',dict(method=METHOD_VERSION,rows=rows,errors=[]))
        live={r['persistent_id']:dict(r,bpm=0,comment='My comment') for r in rows}
        return rows,live

    def test_marker_preserves_comments_and_is_idempotent(self):
        for original in ('', 'Existing text', 'Existing text\n', 'First\r\nSecond\n'):
            marked=m.comment_value(original,True)
            self.assertEqual(marked.count(m.MARKER),1)
            self.assertEqual(m.comment_value(marked,True),marked)
        self.assertEqual(m.comment_value('Hello\nbeatpick-duplicate\nOther',False),'Hello\nOther')
        self.assertEqual(m.comment_value('About beatpick-duplicate here',False),'About beatpick-duplicate here')

    def test_audio_across_names_remix_and_no_name_only_dedup(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);rows,_=self.fixture(root)
            raw=np.random.default_rng(4).normal(size=160000).astype('<f4').tobytes()
            with patch.object(recordings.subprocess,'check_output',return_value=raw):
                groups,evidence=recordings.group_recordings(rows,root,identity)
            self.assertEqual(len(evidence),1)
            self.assertEqual(sorted(map(len,groups)),[1,2])
            self.assertEqual({r['persistent_id'] for r in m.select_winners(groups)}, {'BBBBBBBBBBBBBBBB','CCCCCCCCCCCCCCCC'})
            # Equal names are not enough: independent audio remains separate.
            self.assertFalse(recordings.compare_audio(np.frombuffer(raw,dtype='<f4'),np.random.default_rng(5).normal(size=160000))['same'])
            rows[0]['target_percent']=80.
            self.assertEqual(m.select_winners([[rows[1],rows[0]]])[0]['persistent_id'],'AAAAAAAAAAAAAAAA')

    def test_plan_apply_commit_and_stale_plan(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);rows,live=self.fixture(root)
            with patch.object(m,'group_recordings',return_value=([[rows[0],rows[1]],[rows[2]]],[])),patch.object(m,'music',return_value=live) as bridge:
                data=m.plan(root)
                self.assertEqual(bridge.call_args.args[0],'inspect')
            self.assertEqual(data['duplicate_ids'],['AAAAAAAAAAAAAAAA'])
            self.assertEqual(data['rows'][1]['after']['bpm'],171)
            self.assertFalse((root/'committed.json').exists())
            def apply_bridge(mode,requests,state):
                self.assertEqual(mode,'apply')
                self.assertTrue(list(root.glob('metadata-backup-*.json')))
                return {r['persistent_id']:dict(r['before'],**r['after']) for r in requests}
            with patch.object(m,'music',side_effect=apply_bridge):
                self.assertEqual(m.apply(root)['status'],'verified')
            committed=json.loads((root/'committed.json').read_text())
            self.assertEqual(committed['managed_comment_ids'],['AAAAAAAAAAAAAAAA'])
            (root/'pending.json').write_text('{}')
            with patch.object(m,'music') as bridge:
                with self.assertRaises((ValueError,KeyError)):m.apply(root)
                bridge.assert_not_called()

    def test_changed_audio_and_failed_readback_do_not_commit(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);rows,live=self.fixture(root)
            with patch.object(m,'group_recordings',return_value=([[r] for r in rows],[])),patch.object(m,'music',return_value=live):
                m.plan(root)
                with self.assertRaisesRegex(ValueError,'Metadata verification'):m.apply(root)
            self.assertFalse((root/'committed.json').exists())
            Path(rows[0]['path']).write_bytes(b'changed')
            with patch.object(m,'music') as bridge:
                with self.assertRaisesRegex(ValueError,'Audio changed since preview'):m.apply(root)
                bridge.assert_not_called()

    def test_former_loser_marker_removed_and_failed_plan_invalidated(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);rows,live=self.fixture(root)
            write_json(root/'committed.json',dict(rows=rows,managed_comment_ids=['AAAAAAAAAAAAAAAA']))
            live['AAAAAAAAAAAAAAAA']['comment']='My comment\nbeatpick-duplicate'
            rows[0]['passes']=False
            write_json(root/'pending.json',dict(method=METHOD_VERSION,rows=rows,errors=[]))
            with patch.object(m,'group_recordings',return_value=([[rows[1]],[rows[2]]],[])),patch.object(m,'music',return_value=live):
                data=m.plan(root)
            self.assertEqual(data['rows'][0]['after']['comment'],'My comment\n')
            with patch.object(m,'group_recordings',side_effect=ValueError('decode failure')):
                with self.assertRaises(ValueError):m.plan(root)
            self.assertFalse((root/'metadata-plan.json').exists())

if __name__=='__main__':unittest.main()

class ConfigurableMarkerTests(unittest.TestCase):
    def test_custom_marker_owns_only_its_line(self):
        original = 'First\r\nexample-marker\r\nOther example-marker text\n'
        self.assertEqual(m.comment_value(original, False, 'example-marker'), 'First\r\nOther example-marker text\n')
        marked = m.comment_value('Note', True, 'example-marker')
        self.assertEqual(marked, 'Note\nexample-marker')
        self.assertEqual(m.comment_value(marked, True, 'example-marker'), marked)
        self.assertEqual(m.comment_value('beatpick-duplicate', False, 'example-marker'), 'beatpick-duplicate')

    def test_invalid_marker(self):
        for marker in ('', '  ', None, 'a\nb', 'a\rb'):
            with self.subTest(marker=marker), self.assertRaises(ValueError):
                m.validate_marker(marker)

    def test_disabled_duplicates_preserve_managed_ids(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            rows,live=MetadataTests().fixture(root)
            write_json(root/'committed.json',dict(rows=rows,managed_comment_ids=['AAAAAAAAAAAAAAAA']))
            with patch.object(m,'music',return_value=live), patch.object(m,'group_recordings') as groups:
                data=m.plan(root, False, False)
                groups.assert_not_called()
            self.assertTrue(all(r['before']['comment']==r['after']['comment'] for r in data['rows']))
            with patch.object(m,'music',return_value=live):
                m.apply(root)
            self.assertEqual(json.loads((root/'committed.json').read_text())['managed_comment_ids'], ['AAAAAAAAAAAAAAAA'])

    def test_marker_change_requires_migration(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            rows,live=MetadataTests().fixture(root)
            write_json(root/'committed.json',dict(rows=rows,managed_comment_ids=['AAAAAAAAAAAAAAAA'],duplicate_marker='old-example'))
            with patch.object(m,'group_recordings',return_value=([[r] for r in rows],[])), self.assertRaisesRegex(ValueError,'marker changed'):
                m.plan(root, marker='new-example')
