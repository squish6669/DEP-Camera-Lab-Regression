import argparse,csv,json,re
from pathlib import Path


def norm(s):
    return re.sub(r'[^A-Z0-9]', '', (s or '').upper())


def read_rows(path):
    return {r['Image']: r for r in csv.DictReader(open(path, encoding='utf-8-sig'))}


def plausible(v):
    v=norm(v)
    if not (6 <= len(v) <= 24): return False
    if not any(c.isdigit() for c in v): return False
    bad=('PSID','WWN','EUI','MODEL','MDL','DPN','CAPACITY','RATED','LBA','SECTOR','FORMAT','CYL','SATA')
    return not any(v.startswith(x) for x in bad)


def base_strength(r):
    if not r: return 0
    v=norm(r.get('CorrectedSerial'))
    if not plausible(v): return 0
    reason=(r.get('Reason') or '').lower()
    corr=(r.get('Correction') or '').lower()
    score=1
    if reason.startswith('embedded-sn:') or reason.startswith('inline:'): score=5
    elif reason.startswith('ser-no:'): score=5
    elif 'split-block recovery' in reason: score=5
    elif reason.startswith('near-'): score=3
    elif reason.startswith('spatial-join:'): score=3
    if corr: score=max(score,4)
    return score


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--ground-truth',required=True)
    ap.add_argument('--r1024-base',required=True)
    ap.add_argument('--r1024-v3',required=True)
    ap.add_argument('--r2048-base',required=True)
    ap.add_argument('--r2048-v3',required=True)
    ap.add_argument('--out-dir',required=True)
    a=ap.parse_args()

    gt=list(csv.DictReader(open(a.ground_truth,encoding='utf-8-sig')))
    b1=read_rows(a.r1024_base); v1=read_rows(a.r1024_v3)
    b2=read_rows(a.r2048_base); v2=read_rows(a.r2048_v3)
    rows=[]

    for g in gt:
        fn=g['Image']; exp=norm(g.get('ExpectedSerial'))
        rb1=b1.get(fn,{}); rv1=v1.get(fn,{}); rb2=b2.get(fn,{}); rv2=v2.get(fn,{})
        c1=norm(rv1.get('FinalSerial')); c2=norm(rv2.get('FinalSerial'))
        base1=norm(rb1.get('CorrectedSerial')); base2=norm(rb2.get('CorrectedSerial'))
        rescue1=norm(rv1.get('V3Rescue')); rescue2=norm(rv2.get('V3Rescue'))
        s1=base_strength(rb1); s2=base_strength(rb2)

        final=''; why=''
        # Consensus is the safest evidence: independent resolution passes agree.
        vals=[x for x in (c1,c2,base1,base2) if plausible(x)]
        counts={x:vals.count(x) for x in set(vals)}
        consensus=sorted(counts, key=lambda x:(counts[x],len(x)), reverse=True)[0] if counts and max(counts.values())>=2 else ''
        if consensus:
            final=consensus; why='cross-resolution consensus'

        # v3 rescues are narrowly vendor/model gated and may repair split/ambiguous OCR.
        # They can override only when both resolutions agree on the rescue, or when the
        # competing baseline is weak. This prevents a later heuristic from destroying a
        # strong S/N-anchored baseline.
        rescues=[x for x in (rescue1,rescue2) if plausible(x)]
        if rescue1 and rescue1==rescue2 and plausible(rescue1):
            final=rescue1; why='matching gated v3 rescue at 1024+2048'
        elif rescue1 and plausible(rescue1) and s1 < 4 and (not final or final in (c1,base1)):
            final=rescue1; why='1024 gated v3 rescue over weak baseline'
        elif rescue2 and plausible(rescue2) and s2 < 4 and (not final or final in (c2,base2)):
            final=rescue2; why='2048 gated v3 rescue over weak baseline'

        if not final:
            # Preserve strongest S/N evidence. Ties intentionally prefer the normal 1024
            # pass because it generalized best on the blind batch.
            choices=[]
            if plausible(base1): choices.append((s1,2,base1,'1024 baseline'))
            if plausible(base2): choices.append((s2,1,base2,'2048 baseline'))
            if plausible(c1): choices.append((max(1,s1),2,c1,'1024 v3'))
            if plausible(c2): choices.append((max(1,s2),1,c2,'2048 v3'))
            if choices:
                choices.sort(reverse=True)
                _,_,final,why=choices[0]

        rows.append({
            'Image':fn,'ExpectedSerial':exp,
            'R1024Base':base1,'R1024V3':c1,'R1024Strength':s1,
            'R2048Base':base2,'R2048V3':c2,'R2048Strength':s2,
            'FinalSerial':final,'FinalExact':bool(exp and final==exp),'FusionReason':why
        })

    scored=[r for r in rows if r['ExpectedSerial']]
    summary={
        'serial_n':len(scored),
        'final_exact':sum(r['FinalExact'] for r in scored),
    }
    summary['final_pct']=round(100*summary['final_exact']/summary['serial_n'],1) if summary['serial_n'] else 0
    out=Path(a.out_dir);out.mkdir(parents=True,exist_ok=True)
    with open(out/'Serial-Fusion-Results.csv','w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=rows[0].keys());w.writeheader();w.writerows(rows)
    json.dump(summary,open(out/'Serial-Fusion-Summary.json','w'),indent=2)
    print(json.dumps(summary,indent=2))

if __name__=='__main__': main()
