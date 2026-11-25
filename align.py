from pathlib import Path
import json, tempfile
from flask import Flask, request, jsonify, send_from_directory
from alignment_core import analyze
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
@app.post('/alignment/run')
def run():
    # Only same-origin localhost UI; prevent drive-by remote sites from invoking local compute.
    if request.headers.get('Origin') not in (None,'http://127.0.0.1:8765','http://localhost:8765'):return ('Forbidden',403)
    try:
        p=json.loads(request.form['project']);mode=request.form.get('mode','both')
        with tempfile.TemporaryDirectory() as d:
            refs={};queries=[]
            for i,f in enumerate(request.files.getlist('audio')):
                path=Path(d)/f'q{i}';f.save(path);queries.append((f.filename,path))
            for key,f in request.files.items():
                if key.startswith('ref_') and f.filename:
                    ci=int(key[4:]);path=Path(d)/f'r{ci}';f.save(path);refs[ci]=path
            model=None
            if mode=='both':
                from faster_whisper import WhisperModel
                model=WhisperModel(request.form.get('model','small'),device='cpu',compute_type='int8')
            return jsonify(analyze(p,queries,refs,model))
    except Exception as e:return jsonify(error=str(e)),getattr(e,'code',400)
if __name__=='__main__':app.run(host='127.0.0.1',port=8765,debug=False)
