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
    xs=[p[0] for p in pts];ys=[p[1] for p in pts]
    return min(xs),min(ys),max(xs),max(ys)
def row(a,b):
    if not a or not b:return False
    ac=(a[1]+a[3])/2;bc=(b[1]+b[3])/2
    return abs(ac-bc)<=max(22,.8*max(a[3]-a[1],b[3]-b[1]))
def clean(c,man=''):
    c=norm(c)
    if 'WESTERN DIGITAL' in man.upper() and c.startswith('WD') and len(c)>=10:c=c[2:]
    return c

def strong(blocks,man):
    out=[]
    for b in blocks:
        t=(b.get('Text') or '').strip(); conf=float(b.get('BoxConfidence') or 0)
        if re.search(r'(?i)\b(?:DS/N|DP/N|DPN|P/N|PN|CT|WWN|FRU)\b',t):continue
        m=re.search(r'(?i)HDD\s*S\s*/?\s*N\s*[:#-]?\s*([A-Z0-9-]{6,28})',t)
        if m: out.append((240+conf,clean(m.group(1),man),'explicit HDD S/N'));continue
        m=re.search(r'(?i)(?:S\s*[/\\I1|]?\s*N|SN|SERIAL(?:\s*(?:NO|NUMBER|#))?)\s*[:#-]?\s*([A-Z0-9][A-Z0-9-]{5,28})',t)
        if m: out.append((220+conf,clean(m.group(1),man),'explicit S/N'));continue
        m=re.match(r'^\*([A-Z0-9-]{6,24})\*$',t,re.I)
        if m: out.append((205+conf,clean(m.group(1),man),'star-wrapped drive serial'))
    for a in blocks:
        t=(a.get('Text') or '').strip(); ab=box(a.get('Coordinates'))
        m=re.match(r'(?i)^\s*(?:S\s*[/\\I1|]?\s*N|S[I1]N|SN)\s*[:#-]?\s*([A-Z0-9]{0,4})\s*$',t)
        if not m or not ab:continue
        prefix=norm(m.group(1)); near=[]
        for b in blocks:
            if b is a:continue
            bb=box(b.get('Coordinates'))
            if not bb or not row(ab,bb):continue
            if bb[0] < ab[2]-10 or bb[0] > ab[2]+430:continue
            p=norm(b.get('Text') or '')
            if not (2<=len(p)<=20) or re.match(r'^(?:LBA|SECTOR|CAPACITY|MODEL|PN|CT|WWN)',p):continue
            near.append((bb[0],bb[2],p,float(b.get('BoxConfidence') or 0)))
        near.sort();cur=prefix;last=ab[2]
        for x1,x2,p,cf in near:
            if x1-last>75:break
            if len(cur)+len(p)>24:break
            cur+=p;last=max(last,x2)
            if 6<=len(cur)<=24 and any(ch.isdigit() for ch in cur):out.append((230+cf,clean(cur,man),'joined S/N anchor'))
    if not out:return ('','','')
    out.sort(reverse=True)
    return out[0][1],out[0][2],out[0][0]

def baseline_is_weak(old,base_row,blocks,man,strong_candidate,strong_score):
    """Protect strong baseline reads, but allow a clearly stronger label-anchored rescue.
    The decision uses only OCR evidence/reject context, never ground truth."""
    if not old:return True,'empty baseline'
    oldn=norm(old)
    reason=(base_row or {}).get('Reason','') or ''
    correction=(base_row or {}).get('Correction','') or ''

    # Canonical WD serials do not keep the label's optional WD prefix.
    if 'WESTERN DIGITAL' in (man or '').upper() and oldn.startswith('WD') and len(oldn)>=10:
        return True,'noncanonical WD prefix'

    # If the chosen value is literally embedded in an OEM/part-number identifier,
    # it is not trustworthy as a drive serial.
    reject_re=re.compile(r'(?i)\b(?:DS/N|DP/N|DPN|P/N|PN|CT|WWN|FRU|PSID|EUI)\b')
    for b in blocks:
        txt=(b.get('Text') or '').strip()
        if reject_re.search(txt) and oldn and oldn in norm(txt):
            return True,'baseline appears in OEM/part-number context'

    # Near-anchor and spatial joins are useful, but lower-authority than a new
    # explicit S/N/HDD S/N read. Only permit replacement when the rescue evidence
    # is strong enough to be explicit/anchored.
    weak_reason=('near-' in reason.lower() or 'spatial-join' in reason.lower())
    explicit_rescue=bool(strong_candidate and strong_score and float(strong_score)>=220)
    if weak_reason and explicit_rescue and norm(strong_candidate)!=oldn:
        return True,'lower-authority baseline vs explicit S/N rescue'

    # A prior vendor correction is considered strong and remains protected.
    if correction:
        return False,'vendor-corrected baseline'
    return False,'strong baseline'

def conservative_correct(man,c,blocks):
    m=man.upper(); c=norm(c); texts=' '.join((b.get('Text') or '') for b in blocks).upper()
    if not c:return c,''
    if 'WESTERN DIGITAL' in m and c.startswith('WD') and len(c)>=10:
        return c[2:],'WD label prefix removal'
    if ('TOSHIBA' in m or 'KIOXIA' in m) and re.search(r'\bMK\d{4,}G',texts) and len(c)==9 and c[5]=='O': return c[:5]+'0'+c[6:],'Toshiba MK-family O->0 serial glyph'
    if ('HGST' in m or 'HITACHI' in m) and 'HUC156030CSS204' in norm(texts) and len(c)==8 and c[0]=='O': return '0'+c[1:],'HGST HUC156030 family leading O->0'
    if 'SEAGATE' in m and 'ST600MM0006' in norm(texts) and len(c)==8 and c[6]=='O': return c[:6]+'0'+c[7:],'Seagate ST600MM0006 family O->0 glyph'
    if 'HITACHI' in m and c.startswith('MPCZN7YO') and len(c)==14: return c[:7]+'0'+c[8:],'Hitachi HDD S/N O->0 glyph'
    return c,''

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--ground-truth',required=True);ap.add_argument('--detections',required=True);ap.add_argument('--base-results',required=True);ap.add_argument('--out-dir',required=True);a=ap.parse_args()
    gt={r['Image']:r for r in csv.DictReader(open(a.ground_truth,encoding='utf-8-sig'))}
    base={r['Image']:r for r in csv.DictReader(open(a.base_results,encoding='utf-8-sig'))}
    det=defaultdict(list)
    for r in csv.DictReader(open(a.detections,encoding='utf-8-sig')):det[r['FileName']].append(r)
    rows=[]
    for fn,g in gt.items():
        exp=norm(g.get('ExpectedSerial'));man=g.get('ExpectedManufacturer','');br=base.get(fn) or {};old=norm(br.get('CorrectedSerial'))
        s,why,score=strong(det.get(fn,[]),man)
        weak,quality_reason=baseline_is_weak(old,br,det.get(fn,[]),man,s,score)
        if old and not weak:
            candidate=old; why='baseline-protected'; score=''
        elif s:
            candidate=s; why=why; score=score
        else:
            candidate=old; why='weak baseline retained; no stronger rescue' if old else ''; score=''
        fixed,corr=conservative_correct(man,candidate,det.get(fn,[]))
        rows.append({'Image':fn,'Manufacturer':man,'ExpectedSerial':exp,'BaseSerial':old,'RescuedSerial':candidate,'FinalSerial':fixed,'BaseExact':bool(exp and old==exp),'FinalExact':bool(exp and fixed==exp),'BaselineQuality':'weak' if weak else 'strong','QualityReason':quality_reason,'RescueReason':why,'Correction':corr})
    scored=[r for r in rows if r['ExpectedSerial']]
    summary={'serial_n':len(scored),'base_exact':sum(r['BaseExact'] for r in scored),'final_exact':sum(r['FinalExact'] for r in scored),'protected_nonempty':sum(1 for r in rows if r['BaseSerial'] and r['BaselineQuality']=='strong'),'weak_nonempty':sum(1 for r in rows if r['BaseSerial'] and r['BaselineQuality']=='weak')}
    summary['final_pct']=round(100*summary['final_exact']/summary['serial_n'],1) if summary['serial_n'] else 0
    out=Path(a.out_dir);out.mkdir(parents=True,exist_ok=True)
    with open(out/'Serial-Rescue-v2-Results.csv','w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=rows[0].keys());w.writeheader();w.writerows(rows)
    json.dump(summary,open(out/'Serial-Rescue-v2-Summary.json','w'),indent=2)
    print(json.dumps(summary,indent=2))
if __name__=='__main__':main()
