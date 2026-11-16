import beatpick
"""Behavioral checks for recovery, conflicting fundamentals and uncertainty."""
import unittest
import tempfile
import json
from pathlib import Path
from unittest.mock import patch
import refresh
from bass_crosscheck import classify, bass_consensus

def window(start, votes, tempos, status='Uncertain', strength=.7):
    return dict(start=start,end=start+4,votes=votes,bpm=votes[0] if votes else None,
        status=status,energy_peaks=[[dict(bpm=bpm,strength=strength)] for bpm in tempos])

def track(windows):
    return dict(title='Arbitrary title',duration=len(windows)*4,
        original=dict(segments=windows))

class Crosscheck(unittest.TestCase):
    def test_recovers_missing_estimators_with_actual_fast_impulses(self):
        result=classify(track([window(0,[169.8,170.1],[170.0,170.3,169.9])]))
        self.assertTrue(result['passes'])
        self.assertEqual(result['target_percent'],100)

    def test_rejects_fast_subdivision_when_bass_fundamental_is_slower(self):
        result=classify(track([window(0,[168]*9,[126,126,126],status='Target range')]))
        self.assertFalse(result['passes'])
        self.assertEqual(result['conflict_percent'],100)

    def test_does_not_double_or_four_thirds_a_valid_slower_onset_estimate(self):
        for slow,fast in [(85,170),(126,168)]:
            with self.subTest(slow=slow):
                self.assertFalse(classify(track([window(0,[slow]*9,[fast]*3)]))['passes'])

    def test_no_onset_requires_stronger_bass_support(self):
        self.assertFalse(classify(track([window(0,[],[170]*3,strength=.3)]))['passes'])
        self.assertTrue(classify(track([window(0,[],[170]*3,strength=.6)]))['passes'])

    def test_lower_rounded_boundary_and_strict_upper_boundary(self):
        for bpm,expected in [(164.49,False),(164.5,True),(185,True),(185.01,False)]:
            with self.subTest(bpm=bpm):
                self.assertEqual(classify(track([window(0,[bpm],[bpm]*3)]))['passes'],expected)

    def test_uncertain_and_silent_time_stays_in_denominator(self):
        good=window(0,[170],[170]*3)
        silent=window(4,[],[],strength=0)
        self.assertTrue(classify(track([good,silent]))['passes'])
        silent2=window(8,[],[],strength=0)
        self.assertFalse(classify(track([good,silent,silent2]))['passes'])

    def test_no_title_dependent_decisions(self):
        a=track([window(0,[170],[170]*3)])
        b=dict(a,title='Synthetic Example')
        self.assertEqual(classify(a)['passes'],classify(b)['passes'])

    def test_single_band_and_inconsistent_bands_are_not_consensus(self):
        self.assertIsNone(bass_consensus([[dict(bpm=170,strength=.9)],[],[]]))
        self.assertIsNone(bass_consensus([[dict(bpm=b,strength=.9)] for b in (126,145,170)]))

    def test_individual_review_survives_cache_but_changed_file_requires_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);audio=root/'audio.mp3';audio.write_bytes(b'fixture')
            inv=root/'inventory.tsv';inv.write_text(f'1\tAAAAAAAAAAAAAAAA\tSong\tArtist\tNeon Horizon Test\t40\t{audio}\n')
            state=root/'state'
            args=['refresh','--state-dir',str(state),'--input-tsv',str(inv)]
            result=dict(passes=True,bpm=170.,target_percent=70.,method=refresh.METHOD_VERSION)
            with patch('sys.argv',args),patch.object(refresh,'analyze_audio',return_value=result):
                refresh.main()
                pending=json.loads((state/'pending.json').read_text())
                row=pending['rows'][0]
                review=dict(persistent_id=row['persistent_id'],file_signature=refresh.identity(row),method=refresh.METHOD_VERSION)
                row['passes']=False;pending['selection_reviews']=[review]
                refresh.write_json(state/'pending.json',pending)
                refresh.write_json(state/'committed.json',pending)
                refresh.main()
                checked=json.loads((state/'pending.json').read_text())
                self.assertFalse(checked['rows'][0]['passes'])
                self.assertTrue(checked['rows'][0]['automatic_passes'])
                audio.write_bytes(b'changed fixture')
                with self.assertRaisesRegex(RuntimeError,'analysis errors'):
                    refresh.main()
                self.assertFalse((state/'proposed.md').exists())

if __name__=='__main__':unittest.main()
