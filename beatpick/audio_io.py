SCRATCH_DIR = None
from settings import VALUES as S
"""Read MP3 metadata boundaries without changing the source file."""
import struct
from pathlib import Path

def mp3_payload(path):
    data=Path(path).read_bytes();end=len(data);tags=[]
    if end>=128 and data[end-128:end-125]==b'TAG':
        tags.append(('ID3v1',128));end-=128
    while True:
        previous=end
        if end>=15 and data[end-9:end]==b'LYRICS200' and data[end-15:end-9].isdigit():
            size=int(data[end-15:end-9]);start=end-15-size
            if start<0 or data[start:start+11]!=b'LYRICSBEGIN':raise ValueError('Invalid Lyrics3 metadata footer')
            tags.append(('Lyrics3v2',end-start));end=start
        elif end>=32 and data[end-32:end-24]==b'APETAGEX':
            version,size,count,flags=struct.unpack('<4I',data[end-24:end-8])
            if version not in (1000,2000) or not 32<=size<=end:raise ValueError('Invalid APE metadata footer')
            start=end-size
            if start>=32 and data[start-32:start-24]==b'APETAGEX':start-=32
            tags.append(('APE',end-start));end=start
        if end==previous:break
    return data[:end],dict(trailing_metadata_bytes=len(data)-end,tags=tags)

def frame_duration(data):
    pos=0
    if data[:3]==b'ID3':
        if any(x>=128 for x in data[6:10]):raise ValueError('Invalid ID3 size')
        size=0
        for x in data[6:10]:size=size*128+x
        pos=10+size+(10 if data[3]==4 and data[5]&16 else 0)
    total=0.;frames=0
    while pos+4<=len(data):
        h=int.from_bytes(data[pos:pos+4],'big')
        if h>>21 != 0x7ff:
            if frames==0 and data[pos]==0:pos+=1;continue
            if not any(data[pos:]):break
            raise ValueError(f'Non-audio data inside MP3 frame sequence at byte {pos}')
        version=(h>>19)&3;layer=(h>>17)&3;bi=(h>>12)&15;si=(h>>10)&3
        if version==1 or layer!=1 or bi in (0,15) or si==3:raise ValueError(f'Invalid MP3 frame at byte {pos}')
        sr=[44100,48000,32000][si]//(1 if version==3 else 2 if version==2 else 4)
        br=([0,32,40,48,56,64,80,96,112,128,160,192,224,256,320][bi] if version==3 else [0,8,16,24,32,40,48,56,64,80,96,112,128,144,160][bi])*1000
        length=(144 if version==3 else 72)*br//sr+((h>>9)&1)
        if pos+length>len(data):raise ValueError('Truncated MP3 audio frame')
        total+=(1152 if version==3 else 576)/sr;frames+=1;pos+=length
    if len(data)-pos>=4:raise ValueError('Unparsed MP3 bytes')
    return dict(frame_seconds=round(total,6),frames=frames,audio_end=pos)


def decode_audio(path, metadata_duration):
    import subprocess
    command=['ffmpeg','-v','error','-i',str(path),'-t',str(S['max_track_seconds']),'-map','0:a:0','-ac','1','-ar','11025','-f','f32le','-']
    result=subprocess.run(command,capture_output=True,check=True)
    raw=result.stdout
    diagnostics={}
    payload=None;metadata=None;frames=None
    if result.stderr:
        if Path(path).suffix.lower()!='.mp3':raise ValueError(result.stderr.decode(errors='replace')[:500])
        payload,metadata=mp3_payload(path)
        if not any(tag[0] in ('APE','Lyrics3v2') for tag in metadata['tags']):raise ValueError(result.stderr.decode(errors='replace')[:500])
        frames=frame_duration(payload)
        import tempfile
        with tempfile.NamedTemporaryFile(suffix='.mp3', dir=SCRATCH_DIR) as temporary:
            temporary.write(payload);temporary.flush()
            clean=subprocess.run(['ffmpeg','-v','error','-i',temporary.name,'-t',str(S['max_track_seconds']),'-map','0:a:0','-ac','1','-ar','11025','-f','f32le','-'],capture_output=True,check=True)
        if clean.stderr:raise ValueError(clean.stderr.decode(errors='replace')[:500])
        # ffmpeg may flush a few extra resampling/padding samples when a trailing
        # tag hides the proper end. All samples before that tiny tail must match.
        if abs(len(clean.stdout)-len(raw))>4410:raise ValueError('Metadata removal changed decoded audio duration')
        prefix=max(0,min(len(clean.stdout),len(raw))-4410)
        if clean.stdout[:prefix] != raw[:prefix]:raise ValueError('Metadata removal changed actual decoded audio; investigate source')
        diagnostics['metadata_only_decoder_warning']=metadata
    decoded=len(raw)/4/11025
    duration=metadata_duration
    if abs(decoded-metadata_duration)>2:
        if Path(path).suffix.lower()!='.mp3':raise ValueError('Unexplained decoded duration mismatch')
        if payload is None:payload,metadata=mp3_payload(path)
        if not any(tag[0]=='APE' for tag in metadata['tags']):raise ValueError('Unexplained decoded duration mismatch')
        if frames is None:frames=frame_duration(payload)
        if abs(frames['frame_seconds']-decoded)>.1:raise ValueError('MPEG frame length does not match decoded duration')
        duration=decoded
        diagnostics['duration_correction']={'reason':'Music/bitrate duration includes a trailing APE metadata block; full contiguous MPEG audio verified','metadata_duration':metadata_duration,'audio_duration':decoded,**metadata,**frames}
    return raw,duration,diagnostics
