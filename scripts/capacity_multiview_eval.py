import argparse,csv,json
from collections import defaultdict
from pathlib import Path

from capacity_postprocess import canonical_display,expected_to_gb,extract_candidates

ALLOWED_GENERIC_REASONS={
    'explicit-capacity-token',
    'explicit-capacity-token-ocr-gb',
    'capacity-anchor',
}


def load_csv(path):
    with open(path,encoding='utf-8-sig') as f:
        return list(csv.DictReader(f))


def load_detections(path):
    out=defaultdict(list)
    for r in load_csv(path):
        # Keep alternate views distinguishable from the production full-image pass.
        r['_Source']='alternate'
        out[r['FileName']].append(r)
    return out


def verified(row):
    v=(row.get('Verified') or '').strip().upper()
    return (not v) or v=='YES'


def pick_alternate(source_image,view_names,detections):
    by_gb={}
    for view in view_names:
        blocks=detections.get(view,[])
        # Deliberately pass no manufacturer. Alternate-view recovery may only use
        # generic OCR capacity evidence; it cannot use expected vendor/model data.
        candidates=[c for c in extract_candidates(blocks,'') if c['reason'] in ALLOWED_GENERIC_REASONS]
        seen=set()
        for c in candidates:
            gb=c['gb']
            if gb in seen: continue
            seen.add(gb)
            item=by_gb.setdefault(gb,{'gb':gb,'max_score':0,'views':set(),'evidence':[],'reasons':set()})
            item['max_score']=max(item['max_score'],int(c['score']))
            item['views'].add(view)
            if c['evidence'] and c['evidence'] not in item['evidence']:
                item['evidence'].append(c['evidence'])
            item['reasons'].add(c['reason'])

    accepted=[]
    for item in by_gb.values():
        # A true CAPACITY/CAP/SIZE anchor may fill from one view. A generic bounded
        # GB token must independently survive both deterministic transforms.
        anchored='capacity-anchor' in item['reasons'] and item['max_score']>=92
        repeated=len(item['views'])>=2 and item['max_score']>=84
        if anchored or repeated:
            item['confidence']=item['max_score']
            item['accept_reason']='anchored-explicit-capacity' if anchored else 'two-view-explicit-capacity-consensus'
            accepted.append(item)
    if not accepted:
        return None
    accepted.sort(key=lambda x:(x['confidence'],len(x['views']),x['gb']),reverse=True)
    if len(accepted)>1:
        top=accepted[0]
        second=accepted[1]
        # Do not resolve competing capacities on a tie or near-tie.
        if top['confidence']-second['confidence']<6:
            return None
    return accepted[0]


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--ground-truth',required=True)
    ap.add_argument('--baseline-results',required=True)
    ap.add_argument('--view-map',required=True)
    ap.add_argument('--alternate-detections',required=True)
    ap.add_argument('--out-dir',required=True)
    a=ap.parse_args()

    out=Path(a.out_dir); out.mkdir(parents=True,exist_ok=True)
    gt=[r for r in load_csv(a.ground_truth) if verified(r)]
    baseline={r['Image']:r for r in load_csv(a.baseline_results)}
    mappings=load_csv(a.view_map)
    views=defaultdict(list)
    for r in mappings:
        views[r['SourceImage']].append(r['ViewImage'])
    det=load_detections(a.alternate_detections)

    if len(views)!=123:
        raise SystemExit(f'Multiview map must cover exactly 123 physical images; found {len(views)}')
    bad=[k for k,v in views.items() if len(v)!=2]
    if bad:
        raise SystemExit(f'Each physical image must have exactly two derived views; bad count={len(bad)}')

    rows=[]
    fills=0
    for g in gt:
        fn=g['Image']
        exp=expected_to_gb(g.get('ExpectedCapacity',''))
        if exp is None:
            continue
        base=baseline.get(fn,{})
        base_selected=base.get('CapacityGB','')
        try:
            selected=int(float(base_selected)) if str(base_selected).strip() else None
        except ValueError:
            selected=None
        source='baseline' if selected is not None else 'no-candidate'
        confidence=int(float(base.get('Confidence') or 0)) if selected is not None else 0
        reason=base.get('Reason','') if selected is not None else 'no-capacity-candidate'
        evidence=base.get('Evidence','') if selected is not None else ''

        # Never replace a production baseline capacity. Alternate views are an
        # empty-result fallback only.
        if selected is None:
            alt=pick_alternate(fn,views.get(fn,[]),det)
            if alt:
                selected=alt['gb']; source='alternate-explicit-fill'; fills+=1
                confidence=alt['confidence']; reason=alt['accept_reason']
                evidence=' || '.join(alt['evidence'][:4])

        rows.append({
            'Image':fn,
            'ExpectedCapacity':canonical_display(exp),
            'SelectedCapacity':canonical_display(selected),
            'CapacityGB':selected or '',
            'Exact':bool(selected==exp),
            'Source':source,
            'Confidence':confidence,
            'Reason':reason,
            'Evidence':evidence,
        })

    exact=sum(r['Exact'] for r in rows)
    metrics={
        'capacity_n':len(rows),
        'capacity_exact':exact,
        'capacity_pct':round(100*exact/len(rows),1) if rows else 0,
        'alternate_fills':fills,
        'physical_images':len(views),
        'derived_views':sum(len(v) for v in views.values()),
    }
    with open(out/'Capacity-Multiview-Results.csv','w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=rows[0].keys()); w.writeheader(); w.writerows(rows)
    with open(out/'Capacity-Multiview-Summary.json','w',encoding='utf-8') as f:
        json.dump(metrics,f,indent=2)

    lines=['# Capacity Multiview Evaluation','',
           f"- Physical images processed: **{metrics['physical_images']}**",
           f"- Derived OCR views: **{metrics['derived_views']}**",
           f"- Verified capacity rows scored: **{metrics['capacity_n']}**",
           f"- Exact capacity: **{metrics['capacity_exact']}/{metrics['capacity_n']} ({metrics['capacity_pct']}%)**",
           f"- Conservative alternate-view fills: **{metrics['alternate_fills']}**",'',
           '## Alternate-view fills','',
           '| Image | Expected | Selected | Confidence | Reason | Evidence |',
           '|---|---:|---:|---:|---|---|']
    for r in rows:
        if r['Source']=='alternate-explicit-fill':
            lines.append(f"| {r['Image']} | {r['ExpectedCapacity']} | {r['SelectedCapacity']} | {r['Confidence']} | {r['Reason']} | {r['Evidence'].replace('|','/')} |")
    lines += ['','## Remaining misses','',
              '| Image | Expected | Selected | Source |','|---|---:|---:|---|']
    for r in rows:
        if not r['Exact']:
            lines.append(f"| {r['Image']} | {r['ExpectedCapacity']} | {r['SelectedCapacity']} | {r['Source']} |")
    (out/'Capacity-Multiview-Summary.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print('\n'.join(lines[:8]))


if __name__=='__main__':
    main()
