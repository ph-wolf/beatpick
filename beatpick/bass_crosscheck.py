from settings import VALUES as S
"""Auditable fusion of direct onset estimates and bass-energy periodicity.

No tempo multiplication, no title filters, no minimum continuous beat run.
All unconfirmed and contradictory windows remain in the duration denominator.
"""
from pathlib import Path
import argparse
import json
import statistics

METHOD_VERSION='window-v2-bass-crosscheck-165-185-v6'

def in_range(bpm):return bpm is not None and S['bpm_min']-.5<=bpm<=S['bpm_max']

def bass_consensus(bands):
    peaks=[band[0] for band in bands if band and band[0]['strength']>=.2]
    clusters=[]
    for peak in peaks:
        cluster=[p for p in peaks if abs(p['bpm']-peak['bpm'])<=2.0]
        if len(cluster)>=2:
            clusters.append(cluster)
    if not clusters:return None
    cluster=max(clusters,key=lambda c:(len(c),sum(p['strength'] for p in c)))
    return {'bpm':statistics.median(p['bpm'] for p in cluster),
            'strength':statistics.median(p['strength'] for p in cluster),'bands':len(cluster)}

def classify(row):
    if row.get('skipped'):return dict(row,passes=False,method=METHOD_VERSION)
    duration=row.get('analysis_duration',row['duration'])
    segments=[];seconds=0;bpm_values=[];conflict_seconds=0
    for w in row['original']['segments']:
        seconds_in_window=w['end']-w['start']
        bass=bass_consensus(w['energy_peaks'])
        onset=statistics.median(w['votes']) if w['votes'] else None
        yes=False;reason='unconfirmed'
        if w['status']=='Target range':
            if bass and not in_range(bass['bpm']):
                reason='conflicting_bass_tempo';conflict_seconds+=seconds_in_window
            else:
                yes=True;reason='v2_confirmed'
        elif bass and in_range(bass['bpm']):
            if onset is not None and in_range(onset) and abs(onset-bass['bpm'])<=3:
                yes=True;reason='bass_and_onset_recovery'
            elif onset is None and bass['strength']>=.4:
                yes=True;reason='strong_bass_recovery'
            else:
                reason='conflicting_or_missing_onset'
        if yes:
            seconds+=seconds_in_window
            bpm_values.append(float(onset if onset is not None and in_range(onset) else bass['bpm']))
        segments.append({'start':w['start'],'end':w['end'],'confirmed':yes,'reason':reason,
            'onset_bpm':onset,'bass':bass})
    percent=seconds/duration*100
    return dict(row,method=METHOD_VERSION,passes=percent>=S['coverage_percent'],target_percent=round(percent,3),
        bpm=round(statistics.median(bpm_values),2) if bpm_values else None,
        conflict_percent=round(conflict_seconds/duration*100,3),review_segments=segments)


import numpy as np
from scipy import signal

def peak_evidence(env,rate,left,right):
    a=env[int(left*rate):int(right*rate)].copy()
    if len(a)<rate*4:return []
    a-=a.mean()
    power=np.dot(a,a)
    if power<1e-15:return []
    ac=signal.correlate(a,a,method='fft')[len(a)-1:]
    peaks,_=signal.find_peaks(ac)
    candidates=[]
    for k in peaks:
        if not 90<=60*rate/k<=220:continue
        denominator=ac[k-1]-2*ac[k]+ac[k+1]
        offset=.5*(ac[k-1]-ac[k+1])/denominator if abs(denominator)>1e-20 else 0
        candidates.append({'bpm':round(float(60*rate/(k+offset)),3),'strength':round(float(ac[k]/ac[0]),4)})
    return sorted(candidates,key=lambda c:c['strength'],reverse=True)[:10]

def measure(original, energies, rate, duration, decoded):
    original['method']='window-v2-restored-165-185-v5'
    for window in original['segments']:
        center=(window['start']+window['end'])/2
        left,right=max(0,center-S['context_seconds']/2),min(decoded,center+S['context_seconds']/2)
        window['energy_peaks']=[peak_evidence(e,rate,left,right) for e in energies]
    fused=classify({'duration':duration,'original':original})
    return {key:fused[key] for key in ('method','passes','bpm','target_percent','conflict_percent','original','review_segments')}
