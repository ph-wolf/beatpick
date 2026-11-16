import beatpick
from pathlib import Path
import struct
import tempfile
import unittest
from audio_io import mp3_payload,frame_duration

class MetadataBoundaries(unittest.TestCase):
    def test_only_recognized_trailing_metadata_is_removed(self):
        audio=(bytes.fromhex('fffb9000')+bytes(413))*5
        body=b'LYRICSBEGININD0000210'
        lyrics=body+f'{len(body):06d}'.encode()+b'LYRICS200'
        apebody=b'example metadata'
        footer=b'APETAGEX'+struct.pack('<4I',2000,len(apebody)+32,0,0)+bytes(8)
        payload=audio+apebody+footer+lyrics+b'TAG'+bytes(125)
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'audio.mp3';p.write_bytes(payload)
            cleaned,metadata=mp3_payload(p)
            self.assertEqual(cleaned,audio)
            self.assertEqual(p.read_bytes(),payload)
            self.assertEqual({t[0] for t in metadata['tags']},{'ID3v1','APE','Lyrics3v2'})
            self.assertEqual(frame_duration(cleaned)['frames'],5)

    def test_invalid_audio_inside_frames_is_not_silently_trimmed(self):
        frame=bytes.fromhex('fffb9000')+bytes(413)
        with self.assertRaisesRegex(ValueError,'Non-audio data inside'):
            frame_duration(frame+b'bad audio'+frame)

    def test_truncated_audio_frame_is_an_error(self):
        with self.assertRaisesRegex(ValueError,'Truncated'):
            frame_duration(bytes.fromhex('fffb9000')+bytes(20))

if __name__=='__main__':unittest.main()
