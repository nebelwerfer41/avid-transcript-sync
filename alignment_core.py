"""Experimental local alignment. No media leaves this machine."""
import os, re, subprocess, tempfile, unicodedata, difflib, json, hashlib
from pathlib import Path
import numpy as np
from scipy import signal
RATE=8000; HOP=400
CACHE=Path.home()/ 'Library' / 'Caches' / 'AvidTranscriptSync'
def quiet(*args): pass
def cache_key(path, kind):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    return CACHE/(kind+'-'+h.hexdigest())
def cached_features(path, progress):
    progress('Calcolo impronta file per cache')
    key=cache_key(path,'features-v1').with_suffix('.npy')
    if key.exists():
        try:
            value=np.load(key,allow_pickle=False);progress('Impronta recuperata dalla cache');return value
        except (OSError,ValueError):pass
    progress('Decodifica audio FFmpeg')
    x=audio(path)
    progress('Estrazione impronta acustica')
    value=features(x)
    try:
        CACHE.mkdir(parents=True,exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=CACHE,delete=False) as f:
            np.save(f,value);tmp=f.name
        os.replace(tmp,key)
    except OSError:pass
    return value


def audio(path):
    return np.frombuffer(subprocess.check_output(['ffmpeg','-nostdin','-v','error','-i',str(path),'-vn','-ac','1','-ar',str(RATE),'-f','f32le','-']),dtype='<f4')

def features(x):
    if len(x)<800:return np.empty((0,12),np.float32)
    _,_,z=signal.stft(x,fs=RATE,nperseg=800,noverlap=400,boundary=None,padded=False)
    p=np.abs(z)**2; edges=np.geomspace(100,3900,13)
    b=np.stack([np.log1p(1e5*p[int(a/10):max(int(a/10)+1,int(c/10))].mean(axis=0)) for a,c in zip(edges,edges[1:])],axis=1)
    return np.diff(b,axis=0,prepend=b[:1]).astype('float32')

def locate(query, ref):
    n=len(query)
    if n<100 or len(ref)<n:return None
    q=query-query.mean(axis=0); qnorm=np.sqrt((q*q).sum());
    if qnorm<1e-5:return None
    num=sum(signal.fftconvolve(ref[:,i],q[::-1,i],mode='valid') for i in range(q.shape[1]))
    def rolling(a):
        s=np.concatenate(([0.],np.cumsum(a,dtype=np.float64)));return s[n:]-s[:-n]
    var=sum(np.maximum(0,rolling(ref[:,i]**2)-rolling(ref[:,i])**2/n) for i in range(q.shape[1]))
    corr=num/np.maximum(1e-8,qnorm*np.sqrt(var)); k=int(np.argmax(corr)); best=float(corr[k]); mask=corr.copy();mask[max(0,k-40):k+41]=-1; second=float(mask.max())
    return k*HOP/RATE,best,second

def tokens(s):
    return re.findall(r"[a-z0-9]+",''.join(c for c in unicodedata.normalize('NFKD',s.lower()) if not unicodedata.combining(c)))

def transcript(clip):
    out=[]; ids=[]
    for i,c in enumerate(clip['cues']):
        t=tokens(re.sub(r'\[[^]]*\]','',c['text']));out.extend(t);ids.extend([i]*len(t))
    return out,ids

def match_words(words,clips):
    # Match 30-45 second batches independently; rare trigrams nominate local windows.
    results=[]
    for ci,c in enumerate(clips):
        target,ids=transcript(c); index={}
        for i in range(len(target)-2):index.setdefault(tuple(target[i:i+3]),[]).append(i)
        heard=[]; positions=[]
        for w in words:
            for t in tokens(w['word']):heard.append(t);positions.append(w)
        votes={}
        for i in range(len(heard)-2):
            hits=index.get(tuple(heard[i:i+3]),[])
            if len(hits)>20:continue
            for j in hits:
                bucket=round((j-i)/20)*20;votes[bucket]=votes.get(bucket,0)+1
        for center,count in sorted(votes.items(),key=lambda x:-x[1])[:5]:
            if count<2:continue
            lo=max(0,center-35);hi=min(len(target),center+len(heard)+35)
            sm=difflib.SequenceMatcher(None,heard,target[lo:hi],autojunk=False)
            pairs=[(i+k,j+k+lo) for i,j,n in sm.get_matching_blocks() for k in range(n)]
            score=len(pairs)/max(1,len(heard));
            if len(pairs)<8:continue
            results.append((score,ci,pairs,positions,ids,target))
    return sorted(results,key=lambda x:-x[0])

def recognize(path, model, progress=quiet, model_name='small'):
    key=cache_key(path,'words-v1-'+model_name).with_suffix('.json')
    if key.exists():
        try:
            value=json.loads(key.read_text());progress('Trascrizione recuperata dalla cache',1,1);return value
        except (OSError,ValueError):pass
    progress('Whisper: decodifica e rilevamento voce')
    segs,info=model.transcribe(str(path),language='it',word_timestamps=True,beam_size=5,vad_filter=True,condition_on_previous_text=False)
    words=[]
    for s in segs:
        words.extend(dict(word=w.word,start=w.start,end=w.end,probability=w.probability) for w in (s.words or []))
        progress('Whisper: trascrizione',s.end,info.duration)
    try:
        CACHE.mkdir(parents=True,exist_ok=True)
        with tempfile.NamedTemporaryFile(mode='w',dir=CACHE,delete=False) as f:
            json.dump(words,f);tmp=f.name
        os.replace(tmp,key)
    except OSError:pass
    return words

def analyze(project, queries, refs, model=None, progress=quiet, model_name='small'):
    clips=project['clips']; references={}; report=[]; proposals=[]
    for n,(i,p) in enumerate(refs.items(),1):
        progress(f'Riferimento {n}/{len(refs)} (cassetta {i+1})')
        references[i]=cached_features(p,progress)
    for n,(name,path) in enumerate(queries,1):
        progress(f'Clip {n}/{len(queries)}: {name}')
        f=cached_features(path,progress) if references else None; matches=[]; size=240; stride=200
        windows=range(0,max(0,len(f)-size+1),stride) if references else range(0)
        for k,start in enumerate(windows,1):
            progress('Confronto acustico',k-1,len(windows))
            candidates=[]
            for ci,r in references.items():
                hit=locate(f[start:start+size],r)
                if hit:candidates.append((*hit,ci))
            candidates.sort(key=lambda v:-v[1]);
            if not candidates:continue
            t,s,second,ci=candidates[0]; runner=max(second,candidates[1][1] if len(candidates)>1 else -1)
            if s>=.48 and s-runner>=.07:matches.append(dict(audioStart=start*.05,audioEnd=(start+size)*.05,clip=ci,videoStart=t,score=round(s,3)))
        entry=dict(file=name,matches=matches,textMatches=[]);report.append(entry)
        if model is None:continue
        words=recognize(path,model,progress,model_name)
        for start in range(0,len(words),80):
            progress('Allineamento testo',start,len(words))
            batch=words[start:start+80]; ranked=match_words(batch,clips)
            if not ranked:continue
            score,ci,pairs,pos,ids,target=ranked[0]
            if score<.55:continue
            first,last=ids[pairs[0][1]],ids[pairs[-1][1]]
            entry['textMatches'].append(dict(clip=ci,first=first,last=last,score=round(score,3),audioStart=batch[0]['start'],audioEnd=batch[-1]['end']))
            # Reject ambiguous alternatives in different regions.
            if any(s>=score-.08 and (j!=ci or abs(ii[pp[0][1]]-first)>10) for s,j,pp,_,ii,_ in ranked[1:]):continue
            groups={}
            for a,b in pairs:groups.setdefault(ids[b],[]).append((pos[a],b))
            for cue,items in groups.items():
                original=clips[ci]['cues'][cue]
                if original.get('locked') or original.get('anchor') is not None:continue
                indices=[k for k,xid in enumerate(ids) if xid==cue]; matched={b for _,b in items}
                if not indices or indices[0] not in matched or indices[-1] not in matched or len(matched)/len(indices)<.65:continue
                a=min(w['start'] for w,_ in items); b=max(w['end'] for w,_ in items)
                maps=[m for m in matches if m['clip']==ci and m['audioStart']<=a and m['audioEnd']>=b]
                if not maps:continue
                m=max(maps,key=lambda m:m['score']);offset=m['videoStart']-m['audioStart'];
                proposals.append(dict(clip=ci,cue=cue,text=original['text'],oldIn=original['in'],oldOut=original['out'],start=a+offset,end=b+offset,score=round(min(score,m['score']),3),file=name))
    progress('Risultati pronti',1,1)
    return dict(report=report,proposals=proposals)

