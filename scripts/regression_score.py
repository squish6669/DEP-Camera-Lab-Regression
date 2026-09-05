import argparse, csv, json, math, re
from pathlib import Path
from collections import defaultdict, Counter

SERIAL_ANCHOR = re.compile(r'(?i)(?:\bS\s*[/\\I1|]?\s*N\b|\bSN\b|\bSERIAL(?:\s*(?:NO|NUMBER|#))?)\s*[:#\-]?\s*([A-Z0-9][A-Z0-9\-]{5,28})')
SERIAL_LABEL_ONLY = re.compile(r'(?i)^\s*(?:S\s*[/\\I1|]?\s*N|SN|SERIAL(?:\s*(?:NO|NUMBER|#))?)\s*[:#\-]?\s*$')
NEGATIVE_PREFIXES = ('PSID','WWN','EUI','FW','FRU','MODEL','MDL','PN','P/N','DP/N','DPN','CAPACITY','RATED','LBA','CT')

def norm(s):
    return re.sub(r'[^A-Z0-9]', '', (s or '').upper())

def levenshtein(a,b):
    if a == b: return 0
    if not a: return len(b)
    if not b: return len(a)
    if len(a) > len(b): a,b = b,a
    prev = list(range(len(a)+1))
    for i, cb in enumerate(b,1):
        cur=[i]
        for j, ca in enumerate(a,1):
            cur.append(min(cur[-1]+1, prev[j]+1, prev[j-1]+(ca!=cb)))
        prev=cur
    return prev[-1]

def parse_box(coords):
    pts=[]
    for part in (coords or '').split('|'):
        m=re.search(r'(-?\d+)\s*,\s*(-?\d+)', part)
        if m: pts.append((int(m.group(1)), int(m.group(2))))
    if not pts: return None
    xs=[p[0] for p in pts]; ys=[p[1] for p in pts]
    return min(xs),min(ys),max(xs),max(ys)

def clean_candidate(v):
    v=norm(v)
    if len(v) < 6 or len(v) > 24: return ''
    if v.isdigit() and len(v) > 18: return ''
    if any(v.startswith(norm(x)) for x in NEGATIVE_PREFIXES): return ''
    return v

def serial_candidates(blocks):
    out=[]
    for b in blocks:
        text=str(b.get('Text') or '')
        upper=text.upper().strip()
        if any(upper.startswith(p) for p in NEGATIVE_PREFIXES):
            continue
        for m in SERIAL_ANCHOR.finditer(text):
            c=clean_candidate(m.group(1))
            if c:
                out.append((120 + float(b.get('BoxConfidence') or 0)*10, c, f'anchored:{text}'))
        if SERIAL_LABEL_ONLY.match(text):
            box=parse_box(b.get('Coordinates'))
            if box:
                x1,y1,x2,y2=box; cy=(y1+y2)/2; h=max(1,y2-y1)
                for nb in blocks:
                    if nb is b: continue
                    nbox=parse_box(nb.get('Coordinates'))
                    if not nbox: continue
                    nx1,ny1,nx2,ny2=nbox; ncy=(ny1+ny2)/2
                    if nx1 >= x1 and nx1 <= x2+700 and abs(ncy-cy) <= max(45, h*2.5):
                        c=clean_candidate(str(nb.get('Text') or ''))
                        if c:
                            dist=max(0,nx1-x2)
                            out.append((105 - dist/80 + float(nb.get('BoxConfidence') or 0)*10, c, f'right-of-anchor:{text}->{nb.get("Text")}'))
    for b in blocks:
        text=norm(str(b.get('Text') or ''))
        for prefix in ('SIN','S1N','SN'):
            if text.startswith(prefix) and len(text) >= len(prefix)+6:
                c=clean_candidate(text[len(prefix):])
                if c:
                    out.append((112 + float(b.get('BoxConfidence') or 0)*10, c, f'ocr-anchor:{b.get("Text")}'))
    best={}
    for score,c,why in out:
        if c not in best or score>best[c][0]: best[c]=(score,why)
    return sorted([(s,c,w) for c,(s,w) in best.items()], reverse=True)

def best_near(expected, raw_text):
    e=norm(expected)
    if not e: return None
    toks=[norm(x) for x in re.findall(r'[A-Za-z0-9][A-Za-z0-9\-]{4,30}', raw_text or '')]
    toks=[t for t in toks if abs(len(t)-len(e))<=2]
    if not toks: return None
    return min((levenshtein(e,t),t) for t in toks)

def pick(row, *names):
    for name in names:
        if name in row and row[name] is not None:
            return row[name]
    return ''

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--ground-truth',required=True)
    ap.add_argument('--detections',required=True)
    ap.add_argument('--images',required=True)
    ap.add_argument('--out-dir',required=True)
    ap.add_argument('--thresholds',default=None)
    args=ap.parse_args()
    out=Path(args.out_dir); out.mkdir(parents=True,exist_ok=True)

    gt=list(csv.DictReader(open(args.ground_truth,encoding='utf-8-sig',newline='')))
    det=defaultdict(list)
    with open(args.detections,encoding='utf-8-sig',newline='') as f:
        for r in csv.DictReader(f): det[pick(r,'FileName','Image','Filename')].append(r)
    img={pick(r,'FileName','Image','Filename'):r for r in csv.DictReader(open(args.images,encoding='utf-8-sig',newline=''))}

    rows=[]
    manuf=defaultdict(lambda: Counter())
    for g in gt:
        fn=pick(g,'Image','FileName','Filename')
        exp_s=norm(pick(g,'ExpectedSerial','Serial','Expected Serial'))
        exp_m=norm(pick(g,'ExpectedModel','Model','Expected Model'))
        raw=(img.get(fn) or {}).get('RawText','') or ''
        raw_n=norm(raw)
        raw_s_exact=bool(exp_s and exp_s in raw_n)
        near=best_near(exp_s,raw) if exp_s else None
        raw_s_near=bool(raw_s_exact or (near and near[0] <= 1))
        raw_m_exact=bool(exp_m and exp_m in raw_n)
        mnear=best_near(exp_m,raw) if exp_m else None
        raw_m_near=bool(raw_m_exact or (mnear and mnear[0] <= 1))
        cands=serial_candidates(det.get(fn,[]))
        chosen=cands[0][1] if cands else ''
        chosen_reason=cands[0][2] if cands else ''
        selected_exact=bool(exp_s and chosen==exp_s)
        selected_near=bool(exp_s and chosen and levenshtein(exp_s,chosen)<=1)
        verified=(pick(g,'Verified') or '').strip().upper()=='YES'
        err=(img.get(fn) or {}).get('Error','') or ''
        ms=float((img.get(fn) or {}).get('ElapsedMilliseconds') or 0)
        manufacturer=pick(g,'ExpectedManufacturer','Manufacturer','Expected Manufacturer')
        rows.append({
            'Image':fn,'Manufacturer':manufacturer,'ExpectedSerial':exp_s,
            'SelectedSerial':chosen,'SelectedSerialExact':selected_exact,'SelectedSerialNear1':selected_near,
            'SelectedReason':chosen_reason,'RawSerialExact':raw_s_exact,'RawSerialNear1':raw_s_near,
            'ExpectedModel':exp_m,'RawModelExact':raw_m_exact,'RawModelNear1':raw_m_near,
            'ElapsedMilliseconds':round(ms,1),'Error':err,'Verified':verified,
            'CandidateCount':len(cands),'TopCandidates':' | '.join(c for _,c,_ in cands[:5])
        })
        if verified and exp_s:
            m=manuf[manufacturer]
            m['n']+=1; m['raw_exact']+=int(raw_s_exact); m['raw_near']+=int(raw_s_near); m['selected_exact']+=int(selected_exact); m['selected_near']+=int(selected_near)

    verified_serial=[r for r in rows if r['Verified'] and r['ExpectedSerial']]
    model_rows=[r for r in rows if r['ExpectedModel']]
    elapsed=[r['ElapsedMilliseconds'] for r in rows if not r['Error'] and r['ElapsedMilliseconds']>0]
    elapsed_sorted=sorted(elapsed)
    def pct(n,d): return round(100*n/d,1) if d else 0
    def percentile(xs,p):
        if not xs:return 0
        k=(len(xs)-1)*p; f=math.floor(k); c=math.ceil(k)
        return xs[f] if f==c else xs[f]*(c-k)+xs[c]*(k-f)
    metrics={
        'images':len(rows),'errors':sum(bool(r['Error']) for r in rows),
        'serial_verified':len(verified_serial),
        'raw_serial_exact':sum(r['RawSerialExact'] for r in verified_serial),
        'raw_serial_near1':sum(r['RawSerialNear1'] for r in verified_serial),
        'selected_serial_exact':sum(r['SelectedSerialExact'] for r in verified_serial),
        'selected_serial_near1':sum(r['SelectedSerialNear1'] for r in verified_serial),
        'model_expected':len(model_rows),'raw_model_exact':sum(r['RawModelExact'] for r in model_rows),
        'raw_model_near1':sum(r['RawModelNear1'] for r in model_rows),
        'avg_ms':round(sum(elapsed)/len(elapsed),1) if elapsed else 0,
        'median_ms':round(percentile(elapsed_sorted,.5),1),'p95_ms':round(percentile(elapsed_sorted,.95),1),'max_ms':round(max(elapsed),1) if elapsed else 0,
    }
    metrics['raw_serial_exact_pct']=pct(metrics['raw_serial_exact'],metrics['serial_verified'])
    metrics['raw_serial_near1_pct']=pct(metrics['raw_serial_near1'],metrics['serial_verified'])
    metrics['selected_serial_exact_pct']=pct(metrics['selected_serial_exact'],metrics['serial_verified'])
    metrics['selected_serial_near1_pct']=pct(metrics['selected_serial_near1'],metrics['serial_verified'])
    metrics['raw_model_exact_pct']=pct(metrics['raw_model_exact'],metrics['model_expected'])
    metrics['raw_model_near1_pct']=pct(metrics['raw_model_near1'],metrics['model_expected'])

    with open(out/'Regression-Results.csv','w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=rows[0].keys()); w.writeheader(); w.writerows(rows)
    with open(out/'Regression-Summary.json','w',encoding='utf-8') as f:
        json.dump({'metrics':metrics,'manufacturer':{k:dict(v) for k,v in manuf.items()}},f,indent=2)

    lines=['# DEP Camera Lab Regression Summary','',f"- Images: **{metrics['images']}**; OCR errors: **{metrics['errors']}**",
           f"- Raw serial exact: **{metrics['raw_serial_exact']}/{metrics['serial_verified']} ({metrics['raw_serial_exact_pct']}%)**",
           f"- Raw serial within 1 char: **{metrics['raw_serial_near1']}/{metrics['serial_verified']} ({metrics['raw_serial_near1_pct']}%)**",
           f"- Spatial extractor serial exact: **{metrics['selected_serial_exact']}/{metrics['serial_verified']} ({metrics['selected_serial_exact_pct']}%)**",
           f"- Spatial extractor within 1 char: **{metrics['selected_serial_near1']}/{metrics['serial_verified']} ({metrics['selected_serial_near1_pct']}%)**",
           f"- Raw model exact: **{metrics['raw_model_exact']}/{metrics['model_expected']} ({metrics['raw_model_exact_pct']}%)**",
           f"- Raw model within 1 char: **{metrics['raw_model_near1']}/{metrics['model_expected']} ({metrics['raw_model_near1_pct']}%)**",
           f"- OCR runtime: avg **{metrics['avg_ms']} ms**, median **{metrics['median_ms']} ms**, p95 **{metrics['p95_ms']} ms**, max **{metrics['max_ms']} ms**",'',
           '## Serial accuracy by manufacturer','','| Manufacturer | N | Raw exact | Raw near-1 | Extractor exact | Extractor near-1 |','|---|---:|---:|---:|---:|---:|']
    for k in sorted(manuf):
        m=manuf[k]; n=m['n']
        lines.append(f"| {k or '(blank)'} | {n} | {m['raw_exact']}/{n} | {m['raw_near']}/{n} | {m['selected_exact']}/{n} | {m['selected_near']}/{n} |")
    wrong=[r for r in verified_serial if not r['SelectedSerialExact']]
    lines += ['', '## Extractor misses', '', '| Image | Expected | Selected | Near-1 | Reason |','|---|---|---|---|---|']
    for r in wrong:
        reason=str(r['SelectedReason']).replace('|','/')[:90]
        lines.append(f"| {r['Image']} | {r['ExpectedSerial']} | {r['SelectedSerial']} | {r['SelectedSerialNear1']} | {reason} |")
    (out/'Regression-Summary.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')

    print('\n'.join(lines[:18]))
    failed=[]
    if args.thresholds:
        thresholds=json.load(open(args.thresholds,encoding='utf-8'))
        for key,minv in thresholds.get('minimums',{}).items():
            if metrics.get(key,0) < minv: failed.append(f'{key}={metrics.get(key)} < {minv}')
        for key,maxv in thresholds.get('maximums',{}).items():
            if metrics.get(key,0) > maxv: failed.append(f'{key}={metrics.get(key)} > {maxv}')
    if failed:
        print('REGRESSION GATE FAILED: ' + '; '.join(failed))
        raise SystemExit(2)

if __name__=='__main__': main()
