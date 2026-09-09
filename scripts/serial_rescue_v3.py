import argparse,csv,json,re
from collections import defaultdict
from pathlib import Path

def norm(s): return re.sub(r'[^A-Z0-9]','',(s or '').upper())

def box(s):
    pts=[]
    for p in (s or '').split('|'):
        m=re.search(r'(-?\d+)\s*,\s*(-?\d+)',p)
        if m: pts.append((int(m.group(1)),int(m.group(2))))
    if not pts:return None
    xs=[p[0] for p in pts]; ys=[p[1] for p in pts]
    return min(xs),min(ys),max(xs),max(ys)

def same_row(a,b):
    if not a or not b:return False
    ac=(a[1]+a[3])/2; bc=(b[1]+b[3])/2
    return abs(ac-bc)<=max(24,0.9*max(a[3]-a[1],b[3]-b[1]))

def merge_overlap(left,right,max_overlap=4):
    if not left:return right
    if not right:return left
    lim=min(max_overlap,len(left),len(right))
    for n in range(lim,0,-1):
        if left[-n:]==right[:n]:
            return left+right[n:]
    return left+right

def samsung_split_rescue(man,model,blocks):
    if 'SAMSUNG' not in (man or '').upper(): return '',''
    if not norm(model).startswith('MZ7PD'): return '',''
    for a in blocks:
        t=(a.get('Text') or '').strip(); ab=box(a.get('Coordinates'))
        m=re.match(r'(?i)^\s*S[I1]N\s*[:#-]?\s*(S[0-9A-Z]{1,3})\s*$',t)
        if not m or not ab: continue
        cur=norm(m.group(1)); last=ab[2]; pieces=[]
        for b in blocks:
            if b is a: continue
            bb=box(b.get('Coordinates'))
            if not bb or not same_row(ab,bb): continue
            if bb[0] < ab[2]-5 or bb[0] > ab[2]+260: continue
            p=norm(b.get('Text') or '')
            if not re.fullmatch(r'[A-Z0-9]{3,12}',p): continue
            pieces.append((bb[0],bb[2],p))
        pieces.sort()
        for x1,x2,p in pieces:
            if x1-last>80: break
            merged=merge_overlap(cur,p)
            if len(merged)>18: break
            cur=merged; last=max(last,x2)
            if len(cur)==14 and re.fullmatch(r'S[0-9A-Z]{13}',cur):
                return cur,'Samsung MZ7PD split S/N reconstruction with overlap merge'
    return '',''

def toshiba_near_sn_rescue(man,model,blocks):
    mfg=(man or '').upper(); mdl=norm(model)
    if 'TOSHIBA' not in mfg and 'KIOXIA' not in mfg: return '',''
    if not re.match(r'^MK\d{4,}[A-Z0-9]+$',mdl): return '',''
    anchors=[]
    for a in blocks:
        t=(a.get('Text') or '').strip(); ab=box(a.get('Coordinates'))
        if not ab: continue
        if re.match(r'(?i)^\s*S\s*[/\\I1|]?\s*N\s*[:#-]?\s*$',t): anchors.append((a,ab))
    for a,ab in anchors:
        candidates=[]
        for b in blocks:
            if b is a: continue
            bb=box(b.get('Coordinates'))
            if not bb or not same_row(ab,bb): continue
            if bb[0] < ab[2]-55 or bb[0] > ab[2]+300: continue
            p=norm(b.get('Text') or '')
            if not re.fullmatch(r'[A-Z0-9]{8,12}',p): continue
            if re.match(r'^(?:LBA|SECTOR|CAPACITY|MODEL|DATE|EC|CYL|HDD|SER)',p): continue
            if not any(ch.isdigit() for ch in p) or not any(ch.isalpha() for ch in p): continue
            distance=abs(bb[0]-ab[2])
            candidates.append((distance,-float(b.get('BoxConfidence') or 0),p))
        if candidates:
            candidates.sort()
            return candidates[0][2],'Toshiba/Kioxia MK-family nearest standalone S/N token'
    return '',''

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--ground-truth',required=True)
    ap.add_argument('--detections',required=True)
    ap.add_argument('--v2-results',required=True)
    ap.add_argument('--out-dir',required=True)
    a=ap.parse_args()
    gt={r['Image']:r for r in csv.DictReader(open(a.ground_truth,encoding='utf-8-sig'))}
    v2={r['Image']:r for r in csv.DictReader(open(a.v2_results,encoding='utf-8-sig'))}
    det=defaultdict(list)
    for r in csv.DictReader(open(a.detections,encoding='utf-8-sig')): det[r['FileName']].append(r)
    rows=[]
    for fn,g in gt.items():
        exp=norm(g.get('ExpectedSerial')); man=g.get('ExpectedManufacturer',''); model=g.get('ExpectedModel','')
        prior=norm((v2.get(fn) or {}).get('FinalSerial'))
        rescue=''; why=''
        rescue,why=samsung_split_rescue(man,model,det.get(fn,[]))
        if not rescue: rescue,why=toshiba_near_sn_rescue(man,model,det.get(fn,[]))
        final=rescue or prior
        rows.append({'Image':fn,'Manufacturer':man,'Model':model,'ExpectedSerial':exp,'V2Serial':prior,'V3Rescue':rescue,'FinalSerial':final,'V2Exact':bool(exp and prior==exp),'FinalExact':bool(exp and final==exp),'RescueReason':why})
    scored=[r for r in rows if r['ExpectedSerial']]
    summary={'serial_n':len(scored),'v2_exact':sum(r['V2Exact'] for r in scored),'final_exact':sum(r['FinalExact'] for r in scored)}
    summary['final_pct']=round(100*summary['final_exact']/summary['serial_n'],1) if summary['serial_n'] else 0
    out=Path(a.out_dir); out.mkdir(parents=True,exist_ok=True)
    with open(out/'Serial-Rescue-v3-Results.csv','w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=rows[0].keys()); w.writeheader(); w.writerows(rows)
    json.dump(summary,open(out/'Serial-Rescue-v3-Summary.json','w'),indent=2)
    print(json.dumps(summary,indent=2))

if __name__=='__main__': main()
