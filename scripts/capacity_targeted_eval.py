import argparse,csv,json
from collections import defaultdict
from pathlib import Path

import capacity_postprocess as cp

BASELINE_CAPACITY_PCT = 97.1


def load(path, source):
    d=defaultdict(list)
    with open(path,encoding='utf-8-sig',newline='') as f:
        for r in csv.DictReader(f):
            r['_Source']=source
            d[r['FileName']].append(r)
    return d


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--ground-truth',required=True)
    ap.add_argument('--detections',required=True)
    ap.add_argument('--targeted-detections',required=True)
    ap.add_argument('--out-dir',required=True)
    a=ap.parse_args()
    out=Path(a.out_dir); out.mkdir(parents=True,exist_ok=True)
    gt=list(csv.DictReader(open(a.ground_truth,encoding='utf-8-sig')))
    full=load(a.detections,'full')
    targeted=load(a.targeted_detections,'targeted')
    rows=[]
    for g in gt:
        fn=g['Image']; man=g.get('ExpectedManufacturer','')
        exp=cp.expected_to_gb(g.get('ExpectedCapacity',''))
        base=cp.extract_candidates(full.get(fn,[]),man)
        # Safety rule: targeted OCR may only fill an empty full-image result. It can never
        # override or reorder an existing full-image capacity decision.
        if base:
            candidates=base; source='full-preserved'
        else:
            candidates=cp.extract_candidates(targeted.get(fn,[]),man); source='targeted-empty-fill'
        pick=candidates[0] if candidates else None
        selected=pick['gb'] if pick else None
        rows.append({
            'Image':fn,
            'Manufacturer':man,
            'ExpectedCapacity':cp.canonical_display(exp),
            'SelectedCapacity':cp.canonical_display(selected),
            'Exact':bool(exp is not None and selected==exp),
            'Source':source if pick else 'no-candidate',
            'Confidence':pick['score'] if pick else 0,
            'Reason':pick['reason'] if pick else 'no-capacity-candidate',
            'Evidence':pick['evidence'] if pick else ''
        })
    scored=[r for r in rows if r['ExpectedCapacity']]
    exact=sum(r['Exact'] for r in scored)
    pct=round(100*exact/len(scored),1) if scored else 0
    fills=[r for r in scored if r['Source']=='targeted-empty-fill']
    metrics={'capacity_n':len(scored),'capacity_exact':exact,'capacity_pct':pct,
             'targeted_empty_fills':len(fills),'baseline_pct':BASELINE_CAPACITY_PCT}
    with open(out/'Capacity-Targeted-Results.csv','w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=rows[0].keys()); w.writeheader(); w.writerows(rows)
    with open(out/'Capacity-Targeted-Summary.json','w',encoding='utf-8') as f:
        json.dump(metrics,f,indent=2)
    lines=['# Targeted Capacity Evaluation','',
           f"- Capacity rows: **{len(scored)}**",
           f"- Exact capacity: **{exact}/{len(scored)} ({pct}%)**",
           f"- Targeted empty-result fills: **{len(fills)}**",'',
           '## Targeted fills','',
           '| Image | Manufacturer | Expected | Selected | Confidence | Evidence |',
           '|---|---|---:|---:|---:|---|']
    for r in fills:
        lines.append(f"| {r['Image']} | {r['Manufacturer']} | {r['ExpectedCapacity']} | {r['SelectedCapacity']} | {r['Confidence']} | {r['Evidence'].replace('|','/')} |")
    lines += ['', '## Remaining misses','',
              '| Image | Manufacturer | Expected | Selected | Source |',
              '|---|---|---:|---:|---|']
    for r in scored:
        if not r['Exact']:
            lines.append(f"| {r['Image']} | {r['Manufacturer']} | {r['ExpectedCapacity']} | {r['SelectedCapacity']} | {r['Source']} |")
    (out/'Capacity-Targeted-Summary.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print('\n'.join(lines[:7]))
    if pct < BASELINE_CAPACITY_PCT:
        raise SystemExit(f'Capacity regression: {pct}% < {BASELINE_CAPACITY_PCT}%')

if __name__=='__main__': main()
