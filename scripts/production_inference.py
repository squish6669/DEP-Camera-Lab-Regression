import argparse,csv,json,re,sys
from collections import defaultdict
from pathlib import Path

# Reuse the exact protected regression logic rather than copying or weakening it.
from serial_postprocess import extract as serial_extract, vendor_recover, vendor_correct
from model_postprocess import choose_candidate
from capacity_postprocess import extract_candidates as capacity_candidates, canonical_display, confidence_bucket


def norm(s):
    return re.sub(r'[^A-Z0-9]', '', (s or '').upper())


def load_det(path, source):
    out=defaultdict(list)
    if not path:
        return out
    with open(path, encoding='utf-8-sig') as f:
        for r in csv.DictReader(f):
            r['_Source']=source
            out[r['FileName']].append(r)
    return out


VENDORS = [
    ('SAMSUNG', ('SAMSUNG',), (r'MZVLB', r'MZ7TE', r'MZ7PD', r'MZ75E')),
    ('INTEL', ('INTEL',), (r'SSDPEM', r'SSDPEK')),
    ('KIOXIA', ('KIOXIA',), (r'KXG', r'KSG')),
    ('TOSHIBA', ('TOSHIBA',), (r'MQ01', r'DT01')),
    ('WESTERN DIGITAL', ('WESTERN DIGITAL','WDC'), (r'SDBQNTY', r'\bWD[A-Z0-9-]{8,}')),
    ('MICRON', ('MICRON',), (r'MTFDDA',)),
    ('SK HYNIX', ('SK HYNIX','HYNIX'), (r'HFM[A-Z0-9]{8,}',)),
    ('SANDISK', ('SANDISK','SAN DISK'), (r'SD6SP1M',)),
    ('LITE-ON', ('LITE-ON','LITEON','LITE ON'), (r'\bLJT[A-Z0-9-]{5,}', r'\bLCH[A-Z0-9-]{5,}')),
    ('SEAGATE', ('SEAGATE',), (r'\bST\d{3,4}(?:LM|DM)\d{3}',)),
    ('HGST', ('HGST','HITACHI'), (r'\bHTS[A-Z0-9]{8,}', r'\bZ7K\d{3}')),
    ('FUJITSU', ('FUJITSU',), (r'\bMHV[A-Z0-9]{7,}',)),
    ('CRUCIAL', ('CRUCIAL',), (r'\bCT\d{3,4}MX[A-Z0-9]{5,}',)),
]


def infer_manufacturer(blocks):
    raw=' '.join((b.get('Text') or '') for b in blocks).upper()
    compact=norm(raw)
    scored=[]
    for name,labels,patterns in VENDORS:
        score=0; evidence=[]
        for label in labels:
            if label in raw:
                score=max(score,100)
                evidence.append('label:'+label)
        for pat in patterns:
            if re.search(pat, raw, re.I) or re.search(pat, compact, re.I):
                score=max(score,80)
                evidence.append('family:'+pat)
        if score:
            scored.append((score,name,';'.join(evidence)))
    scored.sort(reverse=True)
    if not scored:
        return '','no-vendor-evidence'
    # Ambiguous family-only evidence must not silently select a vendor.
    if len(scored)>1 and scored[0][0] == scored[1][0] and scored[0][0] < 100:
        return '','ambiguous-vendor-family-evidence'
    return scored[0][1], scored[0][2]


def choose_serial(man, blocks, model=''):
    cands=serial_extract(blocks)
    plausible=[x for x in cands if any(ch.isdigit() for ch in x[1]) and (any(ch.isalpha() for ch in x[1]) or len(x[1])>=8)]
    cands=plausible or cands
    selected=cands[0][1] if cands else ''
    score=cands[0][0] if cands else 0
    reason=cands[0][2] if cands else 'no-serial-candidate'
    recovered,rr=vendor_recover(man,blocks,selected)
    if rr:
        selected=recovered; reason=rr
    corrected,cr=vendor_correct(man,selected,model)
    return corrected,score,(cr or reason),cands


def main():
    ap=argparse.ArgumentParser(description='Camera Lab production inference. Never consumes ground truth.')
    ap.add_argument('--detections',required=True)
    ap.add_argument('--images',required=True)
    ap.add_argument('--targeted-detections')
    ap.add_argument('--out-dir',required=True)
    a=ap.parse_args()
    out=Path(a.out_dir); out.mkdir(parents=True,exist_ok=True)
    full=load_det(a.detections,'full')
    target=load_det(a.targeted_detections,'targeted')
    images=list(csv.DictReader(open(a.images,encoding='utf-8-sig')))
    rows=[]
    for image in images:
        fn=image['FileName']
        blocks=full.get(fn,[])
        tblocks=target.get(fn,[])
        man,man_reason=infer_manufacturer(blocks)
        model_pick,model_decision=choose_candidate(man,blocks,tblocks) if man else (None,'no-manufacturer-evidence')
        model=model_pick[1] if model_pick else ''
        model_reason=(model_decision+':'+model_pick[2]) if model_pick else model_decision
        serial,serial_score,serial_reason,serial_cands=choose_serial(man,blocks,model)
        caps=capacity_candidates(blocks,man)
        cap=caps[0] if caps else None
        cap_gb=cap['gb'] if cap else None
        cap_score=cap['score'] if cap else 0
        rows.append({
            'Image':fn,
            'Manufacturer':man,
            'ManufacturerEvidence':man_reason,
            'Serial':serial,
            'SerialScore':round(serial_score,2),
            'SerialStatus':'FOUND' if serial else 'REVIEW',
            'SerialEvidence':serial_reason,
            'SerialTopCandidates':' | '.join(c for _,c,_ in serial_cands[:5]),
            'Model':model,
            'ModelStatus':'FOUND' if model else 'REVIEW',
            'ModelEvidence':model_reason,
            'Capacity':canonical_display(cap_gb),
            'CapacityGB':cap_gb or '',
            'CapacityConfidence':cap_score,
            'CapacityStatus':confidence_bucket(cap_score) if cap else 'REVIEW',
            'CapacityEvidence':cap['evidence'] if cap else '',
        })
    fields=list(rows[0].keys()) if rows else []
    with open(out/'Camera-Lab-Production-Inference.csv','w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(rows)
    with open(out/'Camera-Lab-Production-Inference.json','w',encoding='utf-8') as f:
        json.dump(rows,f,indent=2)
    summary={
        'images':len(rows),
        'manufacturer_found':sum(bool(r['Manufacturer']) for r in rows),
        'serial_found':sum(bool(r['Serial']) for r in rows),
        'model_found':sum(bool(r['Model']) for r in rows),
        'capacity_found':sum(bool(r['Capacity']) for r in rows),
        'ground_truth_consumed':False,
    }
    with open(out/'Camera-Lab-Production-Inference-Summary.json','w',encoding='utf-8') as f:
        json.dump(summary,f,indent=2)
    print(json.dumps(summary,indent=2))


if __name__=='__main__':
    main()
