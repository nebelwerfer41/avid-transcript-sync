from pathlib import Path
import json, tempfile, threading, time, uuid, platform
from flask import Flask, request, jsonify, send_from_directory
from alignment_core import analyze
from collections import deque
JOBS={}
LOCK=threading.Lock()
class Cancelled(Exception):pass

def same_origin():
    return request.headers.get('Origin') in (None,'http://127.0.0.1:8765','http://localhost:8765')

ROOT=Path(__file__).resolve().parent
app=Flask(__name__,static_folder=None)
# Large transcript JSON fields; media uploads are spooled to disk by Werkzeug.
app.config['MAX_FORM_MEMORY_SIZE']=64*1024*1024
app.config['MAX_CONTENT_LENGTH']=None
@app.get('/')
def home():return send_from_directory(ROOT,'index.html')
@app.get('/<path:name>')
def static(name):
    if name not in ['app.js','engine.mjs','style.css','alignment.mjs']:return ('Not found',404)
    return send_from_directory(ROOT,name)
@app.get('/alignment/health')
def health():return jsonify(ok=True)
@app.post('/alignment/job')
def new_job():
    if not same_origin():return ('Forbidden',403)
    with LOCK:
        for k in list(JOBS):
            if JOBS[k]['state'] in ('done','error','cancelled') and time.time()-JOBS[k]['created']>3600:del JOBS[k]
        if any(j['state'] in ('upload','running') for j in JOBS.values()):return jsonify(error='Analisi già in corso'),409
        key=uuid.uuid4().hex
        JOBS[key]=dict(state='upload',created=time.time(),events=deque(maxlen=200),cancel=threading.Event(),seq=0)
    return jsonify(job=key)

@app.get('/alignment/job/<key>')
def job_status(key):
    with LOCK:
        j=JOBS.get(key)
        if not j:return ('Not found',404)
        return jsonify(state=j['state'],events=list(j['events']),elapsed=time.time()-j['created'])

@app.post('/alignment/job/<key>/cancel')
def cancel_job(key):
    if not same_origin():return ('Forbidden',403)
    with LOCK:
        j=JOBS.get(key)
        if not j:return ('Not found',404)
        j['cancel'].set()
        if j['state']=='upload':j['state']='cancelled'
    return jsonify(ok=True)

@app.post('/alignment/run')
def run():
    # Only same-origin localhost UI; prevent drive-by remote sites from invoking local compute.
    if request.headers.get('Origin') not in (None,'http://127.0.0.1:8765','http://localhost:8765'):return ('Forbidden',403)
    key=request.args.get('job')
    with LOCK:
        job=JOBS.get(key) if key else None
        if key and (not job or job['state']!='upload'):return jsonify(error='Job non valido o annullato'),409
        if job:job['state']='running'
    def progress(message,done=None,total=None):
        if job and job['cancel'].is_set():raise Cancelled()
        event=dict(message=message,done=done,total=total)
        if job:
            with LOCK:
                job['seq']+=1
                event['seq']=job['seq'];job['events'].append(event)
        # Avoid flooding terminal with every acoustic window.
        if done is None or done==0 or done==total or time.monotonic()-getattr(progress,'last',0)>2:
            print('[alignment]',message, '' if done is None else f'{done:.1f}/{total:.1f}',flush=True)
            progress.last=time.monotonic()
    try:
        progress('Ricezione e lettura dei file')
        p=json.loads(request.form['project']);mode=request.form.get('mode','both')
        with tempfile.TemporaryDirectory() as d:
            refs={};queries=[]
            for i,f in enumerate(request.files.getlist('audio')):
                path=Path(d)/f'q{i}';f.save(path);queries.append((f.filename,path))
            for key,f in request.files.items():
                if key.startswith('ref_') and f.filename:
                    ci=int(key[4:]);path=Path(d)/f'r{ci}';f.save(path);refs[ci]=path
            progress(f'File ricevuti: {len(queries)} clip, {len(refs)} riferimenti')
            model=None
            model_name=request.form.get('model','small')
            if mode=='both':
                from faster_whisper import WhisperModel
                progress('Whisper: download o caricamento modello '+model_name)
                if request.form.get('device')=='mps' and platform.machine()=='arm64':
                    try:
                        model=WhisperModel(request.form.get('model','small'),device='mps',compute_type='float32')
                    except Exception as e:progress('MPS non disponibile: fallback CPU ('+str(e)+')')
                if model is None:
                    model=WhisperModel(request.form.get('model','small'),device='cpu',compute_type='int8')
                progress('Modello pronto')
            result=analyze(p,queries,refs,model,progress,model_name)
            if job:
                with LOCK:job['state']='done'
            return jsonify(result)
    except Cancelled:
        if job:
            with LOCK:job['state']='cancelled'
        return jsonify(error='Analisi annullata'),409
    except Exception as e:
        print('[alignment] ERROR',repr(e),flush=True)
        if job:
            with LOCK:job['state']='error'
        return jsonify(error=str(e)),getattr(e,'code',400)
if __name__=='__main__':app.run(host='127.0.0.1',port=8765,debug=False)
