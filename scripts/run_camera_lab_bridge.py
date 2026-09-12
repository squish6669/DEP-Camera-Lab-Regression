import argparse,csv,json,subprocess,sys
from pathlib import Path

EXTS={'.jpg','.jpeg','.png','.bmp','.tif','.tiff'}

def read_json_response(proc,image_name):
    """Read one protocol response while tolerating library startup/log chatter on stdout.

    CameraLabRapidOcr's contract is JSONL, but the OCR dependency can emit diagnostic
    lines to stdout during model initialization/first use. Those lines are not protocol
    responses and must not be mistaken for the image result. We therefore accept only a
    JSON object containing the bridge's Ok field, preserving strict request/response
    ordering without weakening OCR or identity logic.
    """
    skipped=[]
    while True:
        line=proc.stdout.readline()
        if not line:
            err=proc.stderr.read()
            extra=('; non-JSON stdout: '+repr(skipped[-5:])) if skipped else ''
            raise RuntimeError(f'CameraLabRapidOcr terminated before responding for {image_name}: {err}{extra}')
        text=line.strip().lstrip('\ufeff')
        if not text:
            continue
        try:
            value=json.loads(text)
        except json.JSONDecodeError:
            skipped.append(text)
            continue
        if isinstance(value,dict) and 'Ok' in value:
            if skipped:
                print(f'[bridge diagnostic] ignored {len(skipped)} non-protocol stdout line(s) before {image_name}',file=sys.stderr)
            return value
        skipped.append(text)

def main():
    ap=argparse.ArgumentParser(description='Run the production CameraLabRapidOcr JSONL bridge and emit regression-compatible OCR CSVs.')
    ap.add_argument('--exe',required=True)
    ap.add_argument('--images',required=True)
    ap.add_argument('--out-dir',required=True)
    ap.add_argument('--max-side-len',type=int,default=2048)
    a=ap.parse_args()
    image_dir=Path(a.images)
    images=sorted([p for p in image_dir.rglob('*') if p.is_file() and p.suffix.lower() in EXTS], key=lambda p:p.name.lower())
    out=Path(a.out_dir); out.mkdir(parents=True,exist_ok=True)
    proc=subprocess.Popen([a.exe],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,encoding='utf-8',bufsize=1)
    image_rows=[]; det_rows=[]
    try:
        for p in images:
            req={'Path':str(p.resolve()),'MaxSideLen':a.max_side_len}
            proc.stdin.write(json.dumps(req,separators=(',',':'))+'\n'); proc.stdin.flush()
            r=read_json_response(proc,p.name)
            ok=bool(r.get('Ok'))
            error='' if ok else (r.get('Error') or 'Unknown bridge error')
            raw=r.get('Text') or ''
            image_rows.append({'FileName':p.name,'RawText':raw,'Error':error,'ElapsedMilliseconds':r.get('ElapsedMilliseconds',''),'Engine':r.get('Engine','')})
            if not ok: continue
            for b in r.get('Blocks') or []:
                pts=b.get('Points') or []
                coords='|'.join(f"{int(round(float(q.get('X',0))))},{int(round(float(q.get('Y',0))))}" for q in pts)
                det_rows.append({'FileName':p.name,'Index':b.get('Index',''),'Text':b.get('Text') or '','BoxConfidence':b.get('BoxConfidence',0),'AverageCharacterConfidence':b.get('AverageCharacterConfidence',0),'Coordinates':coords})
    finally:
        if proc.stdin:
            try: proc.stdin.close()
            except Exception: pass
        try: proc.wait(timeout=10)
        except Exception: proc.kill()
    with open(out/'RapidOCR_Images.csv','w',encoding='utf-8-sig',newline='') as f:
        fields=['FileName','RawText','Error','ElapsedMilliseconds','Engine']; w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(image_rows)
    with open(out/'RapidOCR_Detections.csv','w',encoding='utf-8-sig',newline='') as f:
        fields=['FileName','Index','Text','BoxConfidence','AverageCharacterConfidence','Coordinates']; w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(det_rows)
    errors=sum(bool(r['Error']) for r in image_rows)
    print(json.dumps({'images':len(image_rows),'detections':len(det_rows),'errors':errors,'max_side_len':a.max_side_len},indent=2))
    if errors: return 2
    return 0

if __name__=='__main__':
    raise SystemExit(main())
