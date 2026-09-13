import argparse,csv,json,re,sys
from collections import defaultdict
from pathlib import Path

# Reuse the exact protected regression logic rather than copying or weakening it.
from serial_postprocess import extract as serial_extract, vendor_recover, vendor_correct
from model_postprocess import choose_candidate, family_candidates
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


def load_capacity_views(path):
    out=defaultdict(list)
    if not path:
        return out
    with open(path, encoding='utf-8-sig') as f:
        for r in csv.DictReader(f):
            source=(r.get('SourceImage') or '').strip()
            view=(r.get('ViewImage') or '').strip()
            if source and view:
                out[source].append(view)
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

ALLOWED_GENERIC_CAPACITY_REASONS = {
    'explicit-capacity-token',
    'explicit-capacity-token-ocr-gb',
    'capacity-anchor',
}


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


def choose_alternate_model(man, view_names, detections):
    """Fill an empty model only when both deterministic views OCR the same bounded vendor-family token.

    This deliberately excludes synthesized family recoveries and ground truth. It never replaces an
    existing production model and requires exact two-view agreement on a token independently accepted
    by the existing vendor-bounded model parser.
    """
    if not man or len(view_names) != 2:
        return None
    per_view=[]
    evidence={}
    for view in view_names:
        blocks=detections.get(view,[])
        candidates=family_candidates(man,blocks)
        raw_norm=norm(' '.join((b.get('Text') or '') for b in blocks))
        exact={}
        for score,candidate,reason in candidates:
            # family_candidates deduplicates by candidate and may retain a higher-scoring
            # recovery reason even when the exact same candidate is literally present in
            # this OCR view. Accept only bounded-parser candidates whose normalized token
            # is directly present in the view, or whose retained reason is already the
            # direct bounded-family reason. This preserves evidence without admitting a
            # synthesized model.
            direct_reason = reason == 'capacity-alternate-bounded-vendor-family'
            literal_evidence = bool(candidate and candidate in raw_norm)
            if direct_reason or literal_evidence:
                exact[candidate]=(score,reason)
        if not exact:
            return None
        per_view.append(set(exact))
        evidence[view]=exact
    common=per_view[0] & per_view[1]
    if len(common) != 1:
        return None
    candidate=next(iter(common))
    scores=[evidence[v][candidate][0] for v in view_names]
    return candidate,min(scores),'two-view-exact-vendor-family-consensus'


def choose_alternate_capacity(view_names, detections):
    by_gb={}
    for view in view_names:
        blocks=detections.get(view,[])
        # Ground-truth-free and vendor-free by design: alternate recovery can use
        # only explicit generic OCR capacity evidence from deterministic views.
        candidates=[c for c in capacity_candidates(blocks,'') if c['reason'] in ALLOWED_GENERIC_CAPACITY_REASONS]
        seen=set()
        for c in candidates:
            gb=c['gb']
            if gb in seen:
                continue
            seen.add(gb)
            item=by_gb.setdefault(gb,{'gb':gb,'max_score':0,'views':set(),'evidence':[],'reasons':set()})
            item['max_score']=max(item['max_score'],int(c['score']))
            item['views'].add(view)
            if c['evidence'] and c['evidence'] not in item['evidence']:
                item['evidence'].append(c['evidence'])
            item['reasons'].add(c['reason'])

    accepted=[]
    for item in by_gb.values():
        anchored='capacity-anchor' in item['reasons'] and item['max_score']>=92
        repeated=len(item['views'])>=2 and item['max_score']>=84
        if anchored or repeated:
            item['confidence']=item['max_score']
            item['accept_reason']='anchored-explicit-capacity' if anchored else 'two-view-explicit-capacity-consensus'
            accepted.append(item)
    if not accepted:
        return None
    accepted.sort(key=lambda x:(x['confidence'],len(x['views']),x['gb']),reverse=True)
    if len(accepted)>1 and accepted[0]['confidence']-accepted[1]['confidence']<6:
        return None
    return accepted[0]


def main():
    ap=argparse.ArgumentParser(description='Camera Lab production inference. Never consumes ground truth.')
    ap.add_argument('--detections',required=True)
    ap.add_argument('--images',required=True)
    ap.add_argument('--targeted-detections')
    ap.add_argument('--capacity-view-map')
    ap.add_argument('--capacity-alternate-detections')
    ap.add_argument('--rotated-label-view-map')
    ap.add_argument('--rotated-label-detections')
    ap.add_argument('--out-dir',required=True)
    a=ap.parse_args()
    out=Path(a.out_dir); out.mkdir(parents=True,exist_ok=True)
    full=load_det(a.detections,'full')
    target=load_det(a.targeted_detections,'targeted')
    alt_capacity=load_det(a.capacity_alternate_detections,'capacity-alternate')
    rotated_label=load_det(a.rotated_label_detections,'rotated-label')
    capacity_views=load_capacity_views(a.capacity_view_map)
    rotated_views=load_capacity_views(a.rotated_label_view_map)
    if bool(a.capacity_view_map) != bool(a.capacity_alternate_detections):
        raise SystemExit('Capacity multiview recovery requires both --capacity-view-map and --capacity-alternate-detections')
    if bool(a.rotated_label_view_map) != bool(a.rotated_label_detections):
        raise SystemExit('Rotated-label capacity recovery requires both --rotated-label-view-map and --rotated-label-detections')
    if capacity_views:
        if len(capacity_views)!=123:
            raise SystemExit(f'Capacity view map must cover exactly 123 physical images; found {len(capacity_views)}')
        bad=[k for k,v in capacity_views.items() if len(v)!=2]
        if bad:
            raise SystemExit(f'Each physical image must have exactly two deterministic capacity views; bad count={len(bad)}')
    if rotated_views:
        if len(rotated_views)!=123:
            raise SystemExit(f'Rotated label view map must cover exactly 123 physical images; found {len(rotated_views)}')
        bad=[k for k,v in rotated_views.items() if len(v)!=1]
        if bad:
            raise SystemExit(f'Each physical image must have exactly one deterministic rotated label view; bad count={len(bad)}')
    images=list(csv.DictReader(open(a.images,encoding='utf-8-sig')))
    rows=[]
    alternate_model_fills=0
    alternate_capacity_fills=0
    rotated_capacity_fills=0
    for image in images:
        fn=image['FileName']
        blocks=full.get(fn,[])
        tblocks=target.get(fn,[])
        man,man_reason=infer_manufacturer(blocks)
        model_pick,model_decision=choose_candidate(man,blocks,tblocks) if man else (None,'no-manufacturer-evidence')
        model=model_pick[1] if model_pick else ''
        model_reason=(model_decision+':'+model_pick[2]) if model_pick else model_decision
        if not model and man and capacity_views:
            alt_model=choose_alternate_model(man,capacity_views.get(fn,[]),alt_capacity)
            if alt_model:
                model,model_score,model_alt_reason=alt_model
                model_reason='multiview:'+model_alt_reason+f':score={model_score}'
                alternate_model_fills+=1
        serial,serial_score,serial_reason,serial_cands=choose_serial(man,blocks,model)
        caps=capacity_candidates(blocks,man)
        cap=caps[0] if caps else None
        cap_gb=cap['gb'] if cap else None
        cap_score=cap['score'] if cap else 0
        cap_evidence=cap['evidence'] if cap else ''
        cap_status=confidence_bucket(cap_score) if cap else 'REVIEW'
        if cap is None and capacity_views:
            alt=choose_alternate_capacity(capacity_views.get(fn,[]),alt_capacity)
            if alt:
                cap_gb=alt['gb']
                cap_score=alt['confidence']
                cap_evidence='multiview:'+alt['accept_reason']+':'+' || '.join(alt['evidence'][:4])
                cap_status=confidence_bucket(cap_score)
                alternate_capacity_fills+=1
        # Final capacity-only fallback for labels whose normal orientation defeats OCR.
        # It cannot alter serial or model fields, never replaces an existing capacity,
        # and accepts a single rotated view only when the existing generic parser sees
        # an explicit "capacity" anchor at the same protected >=92 score used above.
        if cap_gb is None and rotated_views:
            alt=choose_alternate_capacity(rotated_views.get(fn,[]),rotated_label)
            if alt and alt['accept_reason']=='anchored-explicit-capacity':
                cap_gb=alt['gb']
                cap_score=alt['confidence']
                cap_evidence='rotated-label:'+alt['accept_reason']+':'+' || '.join(alt['evidence'][:4])
                cap_status=confidence_bucket(cap_score)
                rotated_capacity_fills+=1
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
            'CapacityStatus':cap_status,
            'CapacityEvidence':cap_evidence,
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
        'model_multiview_fills':alternate_model_fills,
        'capacity_multiview_fills':alternate_capacity_fills,
        'rotated_label_capacity_fills':rotated_capacity_fills,
        'ground_truth_consumed':False,
    }
    with open(out/'Camera-Lab-Production-Inference-Summary.json','w',encoding='utf-8') as f:
        json.dump(summary,f,indent=2)
    print(json.dumps(summary,indent=2))


if __name__=='__main__':
    main()
