import argparse,csv,json,re
from pathlib import Path
from collections import defaultdict

CAPACITY_CANONICAL_MB = {
    16: 16000, 24: 24000, 32: 32000, 40: 40000, 60: 60000, 64: 64000,
    80: 80000, 100: 100000, 120: 120000, 128: 128000, 160: 160000,
    180: 180000, 200: 200000, 240: 240000, 250: 250000, 256: 256000,
    300: 300000, 320: 320000, 400: 400000, 480: 480000, 500: 500000,
    512: 512000, 600: 600000, 750: 750000, 800: 800000, 960: 960000,
    1000: 1000000, 1024: 1024000, 1200: 1200000, 1500: 1500000,
    1600: 1600000, 1920: 1920000, 2000: 2000000, 2048: 2048000,
    3000: 3000000, 3072: 3072000, 3840: 3840000, 4000: 4000000,
    4096: 4096000, 6000: 6000000, 8000: 8000000,
}

COMMON_GB = set(CAPACITY_CANONICAL_MB)


def norm_text(s):
    return (s or '').upper().replace(',', '')


def expected_to_gb(s):
    t = norm_text(s).strip()
    if not t:
        return None
    m = re.search(r'(\d+(?:\.\d+)?)\s*(TB|GB|G|T)\b', t)
    if not m:
        return None
    v = float(m.group(1)); unit = m.group(2)
    gb = int(round(v * 1000)) if unit.startswith('T') else int(round(v))
    if gb == 1024: gb = 1000
    if gb == 2048: gb = 2000
    if gb == 4096: gb = 4000
    return gb


def canonical_display(gb):
    if gb is None: return ''
    if gb >= 1000 and gb % 1000 == 0:
        return f'{gb//1000} TB'
    return f'{gb} GB'


def source_score(source):
    return 14 if source == 'full' else 8


def add_candidate(out, gb, score, reason, text, conf):
    if gb not in COMMON_GB:
        return
    score = max(0, min(100, int(round(score + min(max(conf,0),1)*8))))
    out.append({'gb':gb,'score':score,'reason':reason,'evidence':text.strip()})


def extract_candidates(blocks, manufacturer=''):
    out=[]
    man=(manufacturer or '').upper()
    all_text=' '.join(norm_text(b.get('Text')) for b in blocks)

    for b in blocks:
        text=norm_text(b.get('Text'))
        if not text: continue
        conf=float(b.get('BoxConfidence') or 0)
        src=b.get('_Source','full')
        base=source_score(src)

        # Explicit decimal TB/GB capacity text is the strongest generic evidence.
        for m in re.finditer(r'(?<![A-Z0-9])(\d+(?:\.\d+)?)\s*(TB|GB|G|T)(?![A-Z0-9])', text):
            raw=float(m.group(1)); unit=m.group(2)
            gb=int(round(raw*1000)) if unit.startswith('T') else int(round(raw))
            # Normalize common binary-ish marketing representations.
            if gb == 1024: gb=1000
            elif gb == 2048: gb=2000
            elif gb == 4096: gb=4000
            add_candidate(out,gb,72+base,'explicit-capacity-token',m.group(0),conf)

        # OCR commonly reads the B in a standalone GB token as 8. Only accept this
        # when the numeric part is itself a canonical capacity and the token is
        # bounded, so serial/model substrings cannot become generic capacity evidence.
        for m in re.finditer(r'(?<![A-Z0-9])(\d{2,4})G8(?![A-Z0-9])', text):
            gb=int(m.group(1))
            if gb in COMMON_GB:
                add_candidate(out,gb,70+base,'explicit-capacity-token-ocr-gb',m.group(0),conf)

        # Labels often print capacity immediately after words such as CAPACITY/CAP.
        for m in re.finditer(r'\b(?:CAPACITY|CAP|SIZE)\s*[:#-]?\s*(\d{2,4})\s*(?:GB|G)?\b',text):
            add_candidate(out,int(m.group(1)),83+base,'capacity-anchor',m.group(0),conf)

        compact=re.sub(r'[^A-Z0-9]','',text)

        # Repair a very small set of vendor/model OCR confusions before matching.
        # These substitutions are vendor-bounded and affect capacity inference only.
        model_compact=compact
        if 'INTEL' in man:
            model_compact=re.sub(r'SSDPEMKF258(?=G|$)','SSDPEMKF256',model_compact)
        elif 'TOSHIBA' in man or 'KIOXIA' in man:
            model_compact=re.sub(r'(KXG[0-9A-Z]{2}ZNV)258(?=G|$)',r'\g<1>256',model_compact)
            model_compact=re.sub(r'(KSG[0-9A-Z]{2}ZMV)258(?=G|$)',r'\g<1>256',model_compact)
            model_compact=re.sub(r'(KXG[0-9A-Z]{2})ZNN(?=128|256|512|1000|1024)',r'\g<1>ZNV',model_compact)

        # Capacity encoded in well-known model families. This is intentionally vendor-bounded.
        model_rules=[]
        if 'SAMSUNG' in man:
            model_rules=[r'MZVLB(128|256|512)',r'MZ7TE(128|256|512)',r'MZ7PD(128|256|512)',r'MZ75E(120|250|500)']
        elif 'INTEL' in man:
            model_rules=[r'SSDPEMKF(128|256|512)',r'SSDPEKN[UW](128|256|512|1000|2000)']
        elif 'TOSHIBA' in man or 'KIOXIA' in man:
            model_rules=[r'KXG[0-9A-Z]{2}ZNV(128|256|512|1000|1024)',r'KSG[0-9A-Z]{2}ZMV(128|256|512)',r'MQ01[A-Z0-9]*(500|750|1000|2000)']
        elif 'WESTERN DIGITAL' in man:
            model_rules=[r'SDBQNTY(128|256|512)',r'WD[0-9A-Z]*(250|320|500|750|1000|2000|3000|4000)']
        elif 'MICRON' in man:
            model_rules=[r'MTFDDA[VK](128|256|512|1000|1024|2000|2048)']
        elif 'HYNIX' in man:
            model_rules=[r'HFM[0-9A-Z]*(128|256|512|1000|1024)']
        elif 'SANDISK' in man:
            model_rules=[r'SD6SP1M(128|256|512)',r'SD[0-9A-Z]*(128|256|512|1000|2000)']
        elif 'LITE' in man:
            model_rules=[r'LJT(128|256|512)',r'LCH(128|256|512)']
        elif 'SEAGATE' in man:
            model_rules=[r'ST(250|320|500|750|1000|2000|3000|4000)[A-Z0-9]*']
        elif 'HGST' in man or 'HITACHI' in man:
            # Do not infer from generic HTS family digits such as HTS7250. Accept only
            # explicit vendor label anchors whose terminal token is a canonical capacity,
            # e.g. "HDD:Z7K320-320" or "TYPE TT7SAB320".
            for m in re.finditer(r'\b(?:HDD|TYPE)\s*[:#-]?\s*[A-Z0-9-]*?(250|320|500|750|1000|2000)\b',text):
                add_candidate(out,int(m.group(1)),82+base,'hgst-capacity-anchor',m.group(0),conf)
            model_rules=[]
        elif 'CRUCIAL' in man:
            model_rules=[r'CT(120|128|240|250|256|480|500|512|1000|2000)[A-Z0-9]*']

        for pat in model_rules:
            for m in re.finditer(pat,model_compact):
                vals=[g for g in m.groups() if g]
                if vals:
                    add_candidate(out,int(vals[-1]),68+base,'vendor-model-capacity',m.group(0),conf)

    # Consensus bonus: repeated capacity evidence across OCR blocks is valuable.
    counts=defaultdict(int)
    for c in out: counts[c['gb']]+=1
    for c in out:
        if counts[c['gb']] >= 2: c['score']=min(100,c['score']+6)
        if counts[c['gb']] >= 3: c['score']=min(100,c['score']+4)

    # If model family and explicit label agree, strongly prefer that capacity.
    kinds=defaultdict(set)
    for c in out: kinds[c['gb']].add(c['reason'])
    for c in out:
        if 'explicit-capacity-token' in kinds[c['gb']] and 'vendor-model-capacity' in kinds[c['gb']]:
            c['score']=min(100,c['score']+8)
        if 'explicit-capacity-token-ocr-gb' in kinds[c['gb']] and 'vendor-model-capacity' in kinds[c['gb']]:
            c['score']=min(100,c['score']+8)

    best={}
    for c in out:
        gb=c['gb']
        if gb not in best or c['score']>best[gb]['score']:
            best[gb]=c
    return sorted(best.values(),key=lambda x:(x['score'],x['gb']),reverse=True)


def confidence_bucket(score):
    if score >= 92: return 'READY'
    if score >= 80: return 'CONFIRM'
    return 'REVIEW'


def load_det(path,source='full'):
    d=defaultdict(list)
    with open(path,encoding='utf-8-sig') as f:
        for r in csv.DictReader(f):
            r['_Source']=source
            d[r['FileName']].append(r)
    return d


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--ground-truth',required=True)
    ap.add_argument('--detections',required=True)
    ap.add_argument('--out-dir',required=True)
    a=ap.parse_args()
    out=Path(a.out_dir); out.mkdir(parents=True,exist_ok=True)
    gt=list(csv.DictReader(open(a.ground_truth,encoding='utf-8-sig')))
    det=load_det(a.detections)
    rows=[]
    for g in gt:
        fn=g['Image']; exp=expected_to_gb(g.get('ExpectedCapacity',''))
        candidates=extract_candidates(det.get(fn,[]),g.get('ExpectedManufacturer',''))
        pick=candidates[0] if candidates else None
        selected=pick['gb'] if pick else None
        score=pick['score'] if pick else 0
        rows.append({
            'Image':fn,
            'Manufacturer':g.get('ExpectedManufacturer',''),
            'ExpectedCapacity':canonical_display(exp),
            'SelectedCapacity':canonical_display(selected),
            'CapacityGB':selected or '',
            'Confidence':score,
            'Decision':confidence_bucket(score),
            'Exact':bool(exp is not None and selected==exp),
            'Reason':pick['reason'] if pick else 'no-capacity-candidate',
            'Evidence':pick['evidence'] if pick else '',
            'TopCandidates':' | '.join(f"{canonical_display(c['gb'])}:{c['score']}" for c in candidates[:5])
        })
    scored=[r for r in rows if r['ExpectedCapacity']]
    exact=sum(bool(r['Exact']) for r in scored)
    ready=sum(r['Decision']=='READY' for r in scored)
    confirm=sum(r['Decision']=='CONFIRM' for r in scored)
    metrics={
        'capacity_n':len(scored),
        'capacity_exact':exact,
        'capacity_pct':round(100*exact/len(scored),1) if scored else 0,
        'ready':ready,
        'confirm':confirm,
        'review':len(scored)-ready-confirm,
    }
    fields=list(rows[0].keys()) if rows else []
    with open(out/'Capacity-Postprocess-Results.csv','w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(rows)
    with open(out/'Capacity-Postprocess-Summary.json','w',encoding='utf-8') as f:
        json.dump(metrics,f,indent=2)
    lines=['# Capacity Postprocess Evaluation','',
           f"- Capacity rows: **{metrics['capacity_n']}**",
           f"- Exact capacity: **{metrics['capacity_exact']}/{metrics['capacity_n']} ({metrics['capacity_pct']}%)**",
           f"- READY / CONFIRM / REVIEW: **{metrics['ready']} / {metrics['confirm']} / {metrics['review']}**",'',
           '## Remaining misses','',
           '| Image | Manufacturer | Expected | Selected | Confidence | Evidence |',
           '|---|---|---:|---:|---:|---|']
    for r in scored:
        if not r['Exact']:
            lines.append(f"| {r['Image']} | {r['Manufacturer']} | {r['ExpectedCapacity']} | {r['SelectedCapacity']} | {r['Confidence']} {r['Decision']} | {r['Evidence'].replace('|','/')} |")
    (out/'Capacity-Postprocess-Summary.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print('\n'.join(lines[:6]))

if __name__=='__main__':
    main()
