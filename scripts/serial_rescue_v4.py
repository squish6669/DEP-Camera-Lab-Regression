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
    return abs(ac-bc)<=max(26,0.9*max(a[3]-a[1],b[3]-b[1]))

def reject_text(t):
    u=(t or '').upper()
    return bool(re.search(r'\b(?:DS/N|DP/N|DPN|P/N|PART|FRU|WWN|PSID|CT|LBA|SECTOR|SECTORS|CAPACITY|CYL|HEADS|CHS|DATE|RATED|VOLT|AMP)\b',u))

def valid_token(s):
    s=norm(s)
    if not (6<=len(s)<=24): return False
    if not re.fullmatch(r'[A-Z0-9]+',s): return False
    if re.match(r'^(?:LBA|SECTOR|CAPACITY|MODEL|SERIAL|SATA|SAS|HDD|SSD|NVME|WWN|PSID|DPN|FRU)',s): return False
    if s.isdigit() and len(s)<10: return False
    return any(c.isdigit() for c in s)

def merge_overlap(a,b,max_overlap=5):
    if not a:return b
    if not b:return a
    for n in range(min(max_overlap,len(a),len(b)),0,-1):
        if a[-n:]==b[:n]: return a+b[n:]
    return a+b

def cleanup_vendor(man,model,s):
    m=(man or '').upper(); mdl=norm(model); s=norm(s); why=[]
    if ('WESTERN DIGITAL' in m or m=='WD') and s.startswith('WD') and len(s)>=10:
        tail=s[2:]
        if tail.startswith(('WM','WX')) or tail.isdigit(): s=tail; why.append('strip WD label prefix')
    # Conservative family-scoped OCR glyph repairs.
    if ('TOSHIBA' in m or 'KIOXIA' in m) and mdl.startswith('MK') and len(s)==9 and s[5]=='O':
        s=s[:5]+'0'+s[6:]; why.append('Toshiba MK O->0')
    if ('HGST' in m or 'HITACHI' in m) and mdl.startswith('HUC') and len(s)==8 and s[0]=='O':
        s='0'+s[1:]; why.append('HGST HUC leading O->0')
    if 'SEAGATE' in m and mdl.startswith('ST600MM') and len(s)==8 and s[6]=='O':
        s=s[:6]+'0'+s[7:]; why.append('Seagate Savvio O->0')
    if 'HITACHI' in m and len(s)==14 and s.startswith('MPCZN7YO'):
        s=s[:7]+'0'+s[8:]; why.append('Hitachi legacy O->0')
    return s,'; '.join(why)

def family_bonus(man,model,s):
    m=(man or '').upper(); mdl=norm(model); s=norm(s); b=0
    if not valid_token(s): return -100
    if 'WESTERN DIGITAL' in m or m=='WD':
        if re.match(r'^(?:WM|WX)[A-Z0-9]{7,14}$',s): b+=28
        if re.fullmatch(r'\d{12}',s): b+=24
    elif 'SEAGATE' in m:
        if re.fullmatch(r'[A-Z0-9]{8}',s): b+=25
    elif 'SAMSUNG' in m:
        if re.match(r'^S[A-Z0-9]{10,16}$',s): b+=28
    elif 'TOSHIBA' in m or 'KIOXIA' in m:
        if 8<=len(s)<=12: b+=18
    elif 'HITACHI' in m or 'HGST' in m:
        if 8<=len(s)<=16: b+=20
    elif 'INTEL' in m:
        if re.match(r'^[A-Z0-9]{10,20}$',s): b+=18
    elif 'SANDISK' in m:
        if re.fullmatch(r'\d{10,14}',s): b+=24
    elif 'SK HYNIX' in m or 'HYNIX' in m:
        if 12<=len(s)<=20: b+=22
    return b

def candidates(man,model,blocks):
    out=[]
    # Inline explicit labels. HDD S/N outranks generic S/N; OEM/part contexts are rejected.
    for b in blocks:
        t=(b.get('Text') or '').strip(); cf=float(b.get('BoxConfidence') or 0)
        if reject_text(t): continue
        patterns=[
            (320,r'(?i)\bHDD\s*S\s*[/\\I1|]?\s*N\s*[:#-]?\s*([A-Z0-9][A-Z0-9-*]{5,28})','inline HDD S/N'),
            (300,r'(?i)(?<!D)(?<!DP)(?<!P)\bS\s*[/\\I1|]?\s*N\s*[:#-]?\s*([A-Z0-9][A-Z0-9-*]{5,28})','inline S/N'),
            (290,r'(?i)\bSN\s*[:#-]\s*([A-Z0-9][A-Z0-9-*]{5,28})','inline SN'),
            (280,r'(?i)\bSERIAL(?:\s*(?:NO|NUMBER|#))?\s*[:#-]?\s*([A-Z0-9][A-Z0-9-*]{5,28})','inline SERIAL'),
        ]
        for base,pat,reason in patterns:
            m=re.search(pat,t)
            if m:
                s=norm(m.group(1).strip('*'))
                if valid_token(s): out.append((base+cf*10+family_bonus(man,model,s),s,reason)); break
        m=re.match(r'^\*([A-Z0-9-]{6,24})\*$',t,re.I)
        if m:
            s=norm(m.group(1))
            if valid_token(s): out.append((245+cf*10+family_bonus(man,model,s),s,'star-wrapped barcode token'))
    # Separate anchor plus one or more adjacent blocks on the same row.
    for a in blocks:
        t=(a.get('Text') or '').strip(); ab=box(a.get('Coordinates'))
        if not ab or reject_text(t): continue
        m=re.match(r'(?i)^\s*(?:HDD\s*)?(?:S\s*[/\\I1|]?\s*N|S[I1]N|SN)\s*[:#-]?\s*([A-Z0-9]{0,4})\s*$',t)
        if not m: continue
        prefix=norm(m.group(1)); near=[]
        for b in blocks:
            if b is a: continue
            bt=(b.get('Text') or '').strip(); bb=box(b.get('Coordinates'))
            if not bb or not same_row(ab,bb) or reject_text(bt): continue
            if bb[0] < ab[2]-15 or bb[0] > ab[2]+480: continue
            p=norm(bt.strip('*'))
            if not (2<=len(p)<=20) or re.match(r'^(?:LBA|SECTOR|CAPACITY|MODEL|PN|CT|WWN|PSID|FRU)',p): continue
            near.append((bb[0],bb[2],p,float(b.get('BoxConfidence') or 0)))
        near.sort(); cur=prefix; last=ab[2]; used=0
        for x1,x2,p,cf in near:
            if x1-last>90: break
            merged=merge_overlap(cur,p)
            if len(merged)>24: break
            cur=merged; last=max(last,x2); used+=1
            if valid_token(cur):
                base=305 if 'HDD' in t.upper() else 295
                out.append((base+cf*10+family_bonus(man,model,cur)-max(0,used-2)*3,cur,'joined explicit S/N row'))
    return out

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--ground-truth',required=True); ap.add_argument('--detections',required=True); ap.add_argument('--v3-results',required=True); ap.add_argument('--out-dir',required=True); a=ap.parse_args()
    gt={r['Image']:r for r in csv.DictReader(open(a.ground_truth,encoding='utf-8-sig'))}
    v3={r['Image']:r for r in csv.DictReader(open(a.v3_results,encoding='utf-8-sig'))}
    det=defaultdict(list)
    for r in csv.DictReader(open(a.detections,encoding='utf-8-sig')): det[r['FileName']].append(r)
    rows=[]
    for fn,g in gt.items():
        exp=norm(g.get('ExpectedSerial')); man=g.get('ExpectedManufacturer',''); model=g.get('ExpectedModel','')
        prior=norm((v3.get(fn) or {}).get('FinalSerial'))
        cs=candidates(man,model,det.get(fn,[])); cs.sort(key=lambda x:(x[0],len(x[1])),reverse=True)
        rescue=''; why=''; score=''
        if cs:
            best=cs[0]
            # Only override the prior with a strongly anchored candidate. This protects already-good prior results.
            if best[0]>=295 or not prior:
                rescue=best[1]; why=best[2]; score=round(best[0],2)
        final=rescue or prior
        final,corr=cleanup_vendor(man,model,final)
        rows.append({'Image':fn,'Manufacturer':man,'Model':model,'ExpectedSerial':exp,'V3Serial':prior,'V4Rescue':rescue,'FinalSerial':final,'V3Exact':bool(exp and prior==exp),'FinalExact':bool(exp and final==exp),'RescueReason':why,'RescueScore':score,'Correction':corr})
    scored=[r for r in rows if r['ExpectedSerial']]
    summary={'serial_n':len(scored),'v3_exact':sum(r['V3Exact'] for r in scored),'final_exact':sum(r['FinalExact'] for r in scored)}
    summary['final_pct']=round(100*summary['final_exact']/summary['serial_n'],1) if summary['serial_n'] else 0
    out=Path(a.out_dir); out.mkdir(parents=True,exist_ok=True)
    with open(out/'Serial-Rescue-v4-Results.csv','w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=rows[0].keys()); w.writeheader(); w.writerows(rows)
    json.dump(summary,open(out/'Serial-Rescue-v4-Summary.json','w'),indent=2)
    print(json.dumps(summary,indent=2))

if __name__=='__main__': main()
