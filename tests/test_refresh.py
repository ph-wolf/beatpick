import beatpick
import importlib.util
from pathlib import Path
import tempfile
import unittest
import wave
import json
import sys
from unittest.mock import patch
import numpy as np
spec=importlib.util.spec_from_file_location('refresh',Path(beatpick.__file__).parent / 'refresh.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

class AudioCriteria(unittest.TestCase):
    def sample(self,bpm,active=1,dropout=False):
        sr=11025;duration=120;y=np.zeros(sr*duration,dtype=np.float32)
        # Percussive low-frequency kicks; no beat multiplication in source.
        for index,t in enumerate(np.arange(0,duration*active,60/bpm)):
            if dropout and index%8==7:continue
            i=int(t*sr);a=np.arange(int(.13*sr))/sr
            kick=np.sin(2*np.pi*(95*a-80*a*a))*np.exp(-a*32)
            n=min(len(kick),len(y)-i);y[i:i+n]+=kick[:n]
        return y,sr,duration

    def check_audio(self,bpm,active=1,dropout=False):
        y,sr,duration=self.sample(bpm,active,dropout)
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'test.wav'
            with wave.open(str(p),'wb') as f:
                f.setnchannels(1);f.setsampwidth(2);f.setframerate(sr);f.writeframes((y*20000).astype('<i2').tobytes())
            return m.analyze_audio(str(p),duration)

    def test_target_range(self):
        for bpm in (165,180,184):
            with self.subTest(bpm=bpm):
                r=self.check_audio(bpm)
                self.assertTrue(r['passes'],r)
                self.assertLess(abs(r['bpm']-bpm),2)

    def test_slower_and_half_tempo_do_not_pass(self):
        for bpm in (85,126,186,200):
            with self.subTest(bpm=bpm):
                r=self.check_audio(bpm)
                self.assertFalse(r['passes'],r)

    def test_playtime_denominator(self):
        self.assertFalse(self.check_audio(170,.4)['passes'])
        r=self.check_audio(170,.7)
        self.assertTrue(r['passes'],r)
        self.assertLessEqual(r['target_percent'],80)

    def test_inclusive_upper_boundary_and_faster_time_not_counted(self):
        # Direct envelopes avoid sample-grid ambiguity at exactly 185 BPM.
        rate=370
        e=np.zeros(120*rate)
        e[::120]=1
        result=m.measure_envelopes([e,e,e],rate,120,120)
        self.assertTrue(result['passes'])
        self.assertEqual(result['bpm'],185.)
        # 200-BPM sections remain in the denominator, not the target numerator.
        mixed=np.zeros(120*rate)
        mixed[:48*rate:120]=1
        mixed[48*rate::111]=1
        result=m.measure_envelopes([mixed,mixed,mixed],rate,120,120)
        self.assertFalse(result['passes'])
        self.assertLess(result['target_percent'],50)

    def test_missing_individual_kicks_do_not_split_tempo(self):
        r=self.check_audio(170,dropout=True)
        self.assertTrue(r['passes'],r)
        self.assertGreaterEqual(r['target_percent'],80)

    def test_exact_twelve_minutes_is_not_skipped(self):
        with patch('audio_io.decode_audio',side_effect=RuntimeError('audio accessed')):
            with self.assertRaisesRegex(RuntimeError,'audio accessed'):
                m.analyze_audio('/nonexistent',720)

    def test_over_twelve_minutes_skipped_before_file_access(self):
        self.assertIn('skipped',m.analyze_audio('/nonexistent',720.01))

class IncrementalWorkflow(unittest.TestCase):
    def test_persistent_cache_without_markdown(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); audio=root/'audio.mp3';audio.write_bytes(b'fixture')
            inv=root/'inventory.tsv'
            inv.write_text(f"1\tAAAAAAAAAAAAAAAA\tSong\tArtist\tNeon Horizon Test\t40\t{audio}\n")
            args=['refresh','--state-dir',str(root/'state'),'--input-tsv',str(inv)]
            measured=dict(passes=True,target_percent=70.,bpm=170.,method=m.METHOD_VERSION)
            with patch.object(sys,'argv',args),patch.object(m,'analyze_audio',return_value=measured) as analyze:
                m.main();self.assertEqual(analyze.call_count,1)
            state=root/'state'
            self.assertFalse((state/'proposed.md').exists())
            self.assertFalse((state/'committed.json').exists())
            with patch.object(sys,'argv',args),patch.object(m,'analyze_audio') as analyze:
                m.main();analyze.assert_not_called()
            self.assertEqual(json.loads((state/'delta.json').read_text())['counts']['cached'],1)

if __name__=='__main__':unittest.main()
