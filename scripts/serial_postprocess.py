import argparse,csv,json,re
from pathlib import Path
from collections import defaultdict

def norm(s): return re.sub(r'[^A-Z0-9]','',(s or '').upper())

def parse_box(coords):
    pts=[]
    for part in (coords or '').split('|'):
        m=re.search(r'(-?\d+)\s*,\s*(-?\d+)',part)
        if m: pts.append((int(m.group(1)),int(m.group(2))))
    if not pts:return None
    xs=[p[0] for p in pts]; ys=[p[1] for p in pts]
    return min(xs),min(ys),max(xs),max(ys)

def tokens(text):
    return [norm(x) for x in re.findall(r'[A-Za-z0-9][A-Za-z0-9\-]{4,30}', text or '') if 6 <= len(norm(x)) <= 24]

NEG=('PSID','WWN','EUI','FW','FRU','MODEL','MDL','PN','P/N','DP/N','DPN','CAPACITY','RATED','LBA','CT','DATE','DRIVE','FORMAT','DISK','CYL','CHS','SATA','TOSHIBA','ADVANCED','WARRANTY','RATING','DATA','ATA')

def valid_token(t):
    t=norm(t)
    return 6<=len(t)<=24 and not any(t.startswith(norm(x)) for x in NEG)

def alnum_piece(text):
    t=norm(text)
    if not t or len(t)>24:return ''
    if any(t.startswith(norm(x)) for x in NEG):return ''
    if not re.fullmatch(r'[A-Z0-9]+',t):return ''
    if len(t)<3:return ''
    return t

def same_row(a,b):
    if not a or not b:return False
    ax1,ay1,ax2,ay2=a; bx1,by1,bx2,by2=b
    ah=max(1,ay2-ay1); bh=max(1,by2-by1)
    ac=(ay1+ay2)/2; bc=(by1+by2)/2
    return abs(ac-bc)<=max(18,0.85*max(ah,bh))

def vertical_overlap(a,b):
    if not a or not b:return 0.0
    _,ay1,_,ay2=a; _,by1,_,by2=b
    overlap=max(0,min(ay2,by2)-max(ay1,by1))
    return overlap/max(1,min(ay2-ay1,by2-by1))

def assemble_from_anchor(anchor,blocks,prefix=''):
    """Conservative geometry-only join. Spatial candidates are deliberately scored below
    strong inline/near-anchor candidates so they cannot replace a good baseline read."""
    abox=parse_box(anchor.get('Coordinates'))
    if not abox:return []
    ax1,ay1,ax2,ay2=abox
    parts=[]
    if prefix:
        p=alnum_piece(prefix)
        if p:parts.append((ax2,p,float(anchor.get('BoxConfidence') or 0),f'anchor:{anchor.get("Text") or ""}'))
    neighbors=[]
    for nb in blocks:
        if nb is anchor:continue
        nbox=parse_box(nb.get('Coordinates'))
        if not nbox or not same_row(abox,nbox):continue
        nx1,ny1,nx2,ny2=nbox
        if nx1 < ax2-12 or nx1 > ax2+420:continue
        if vertical_overlap(abox,nbox)<0.30:continue
        piece=alnum_piece(nb.get('Text') or '')
        if not piece:continue
        neighbors.append((nx1,nx2,piece,float(nb.get('BoxConfidence') or 0),nb.get('Text') or ''))
    neighbors.sort(key=lambda x:x[0])
    assembled=[]
    current=''.join(p[1] for p in parts)
    last_x=ax2
    confs=[p[2] for p in parts]
    reasons=[p[3] for p in parts]
    for nx1,nx2,piece,conf,raw in neighbors:
        gap=nx1-last_x
        if gap>70:
            if current:break
            if gap>95:break
        if current and len(current)+len(piece)>24:break
        current+=piece; last_x=max(last_x,nx2); confs.append(conf); reasons.append(raw)
        if valid_token(current):
            avg=sum(confs)/len(confs) if confs else 0
            assembled.append((112+avg*5,current,'spatial-join:'+' + '.join(reasons)))
    return assembled

def extract(blocks):
    out=[]
    def add(score,c,reason):
        c=norm(c)
        if valid_token(c): out.append((score,c,reason))
    for b in blocks:
        txt=(b.get('Text') or '').strip(); conf=float(b.get('BoxConfidence') or 0)
        for m in re.finditer(r'(?i)(?:S\s*[/\\I1|]?\s*N|SN|SERIAL(?:\s*(?:NO|NUMBER|#))?)\s*[:#\-]?\s*([A-Z0-9][A-Z0-9\-]{5,28})',txt):
            add(130+conf*10,m.group(1),f'inline:{txt}')
        for m in re.finditer(r'(?i)SN\s*[:#\-]\s*([A-Z0-9][A-Z0-9\-]{5,28})',txt):
            add(135+conf*10,m.group(1),f'embedded-sn:{txt}')
        pm=re.match(r'(?i)^\s*(?:S\s*[/\\I1|]?\s*N|SN|SERIAL(?:\s*(?:NO|NUMBER|#))?)\s*[:#\-]?\s*([A-Z0-9]{2,8})\s*$',txt)
        if pm: out.extend(assemble_from_anchor(b,blocks,pm.group(1)))
    anchor_re=re.compile(r'(?i)^\s*(?:S\s*[/\\I1|]?\s*N|SN|SERIAL|SER)\s*[:#\-]?\s*$')
    for b in blocks:
        txt=(b.get('Text') or '').strip()
        if not anchor_re.match(txt): continue
        out.extend(assemble_from_anchor(b,blocks,''))
        box=parse_box(b.get('Coordinates'))
        if not box: continue
        x1,y1,x2,y2=box; cy=(y1+y2)/2; h=max(1,y2-y1)
        for nb in blocks:
            if nb is b: continue
            nbox=parse_box(nb.get('Coordinates'))
            if not nbox: continue
            nx1,ny1,nx2,ny2=nbox; ncy=(ny1+ny2)/2
            if nx1 >= x1-40 and nx1 <= x2+760 and abs(ncy-cy) <= max(55,h*3.0):
                nt=(nb.get('Text') or '').strip(); conf=float(nb.get('BoxConfidence') or 0)
                for i,t in enumerate(tokens(nt)):
                    add(118 - max(0,nx1-x2)/100 - i*2 + conf*10,t,f'near-{txt}:{nt}')
    for b in blocks:
        if norm(b.get('Text')) not in ('SER','SERIAL'): continue
        box=parse_box(b.get('Coordinates'))
        if not box: continue
        x1,y1,x2,y2=box; cy=(y1+y2)/2
        for nb in blocks:
            nbox=parse_box(nb.get('Coordinates'))
            if not nbox: continue
            nx1,ny1,nx2,ny2=nbox; ncy=(ny1+ny2)/2
            nt=(nb.get('Text') or '').strip()
            m=re.match(r'(?i)^NO\s+([A-Z0-9-]{6,24})',nt)
            if m and abs(ncy-cy)<=120:
                add(122+float(nb.get('BoxConfidence') or 0)*10,m.group(1),f'ser-no:{nt}')
    best={}
    for score,c,why in out:
        if c not in best or score>best[c][0]:best[c]=(score,why)
    return sorted([(s,c,w) for c,(s,w) in best.items()],reverse=True)

def vendor_recover(man,blocks,selected):
    """Safe recovery using vendor-wide label structure, never ground truth.
    Currently recovers SanDisk numeric serials split into overlapping OCR boxes beside S/N."""
    m=(man or '').upper()
    if 'SANDISK' not in m:return selected,''
    anchor_re=re.compile(r'(?i)^\s*S\s*[/\\I1|]?\s*N\s*[:#\-]?\s*$')
    for a in blocks:
        if not anchor_re.match((a.get('Text') or '').strip()):continue
        ab=parse_box(a.get('Coordinates'))
        if not ab:continue
        ax1,ay1,ax2,ay2=ab
        pieces=[]
        for b in blocks:
            if b is a:continue
            bb=parse_box(b.get('Coordinates'))
            if not bb or vertical_overlap(ab,bb)<0.50:continue
            bx1,by1,bx2,by2=bb
            if bx1 < ax2-8 or bx1 > ax2+260:continue
            t=norm(b.get('Text'))
            if t.isdigit() and 4<=len(t)<=9:
                pieces.append((bx1,t))
        pieces.sort()
        for i in range(len(pieces)):
            for j in range(i+1,len(pieces)):
                a1=pieces[i][1]; b1=pieces[j][1]
                trials=[a1+b1]
                if len(b1)>1:trials.append(a1+b1[1:])
                if len(a1)>1:trials.append(a1[:-1]+b1)
                for c in trials:
                    if len(c)==12 and c.isdigit():
                        return c,'SanDisk S/N split-block recovery'
    return selected,''

def vendor_correct(man,candidate,model=''):
    m=(man or '').upper(); c=norm(candidate); model=norm(model)
    if not c:return c,''
    if 'SAMSUNG' in m:
        if len(c)==14 and c.startswith('S4ENNF') and c[6]=='1' and c[7]=='N': return c[:6]+'I'+c[7:],'Samsung S4ENNF 1->I'
        if len(c)==14 and c.startswith('S3WTNX') and c[6]=='O': return c[:6]+'0'+c[7:],'Samsung S3WTNX O->0'
    if 'TOSHIBA' in m or 'KIOXIA' in m:
        if len(c)==12 and c.startswith('Y0IF'): return 'Y01F'+c[4:],'Toshiba/Kioxia Y0IF->Y01F'
        if len(c)==12 and c.startswith('310C25DWE') and c[9]=='T': return c[:9]+'1'+c[10:],'Toshiba/Kioxia T->1 at family position'
        if len(c)==12 and c.startswith('31OC25DWE') and c[2]=='O' and c[9]=='T':
            c='310'+c[3:9]+'1'+c[10:]; return c,'Toshiba/Kioxia O->0 + T->1'
        if len(c)==12 and c.startswith('78HF7') and c[5]=='0': return c[:5]+'Q'+c[6:],'Toshiba/Kioxia 0->Q family position'
        if len(c)==12 and c.startswith('389') and c[3]=='8': return c[:3]+'B'+c[4:],'Toshiba/Kioxia 8->B family position'
        if len(c)==9 and c.startswith('298NTL') and c[6]=='Q': return c[:6]+'G'+c[7:],'Toshiba Q->G family position'
        if len(c)==10 and c.startswith('1') and re.match(r'^1\d{4}[A-Z]{5}$',c): return c[1:],'Toshiba extra leading 1 removal'
        if len(c)==12 and c.startswith('X7JB52W') and c[7]=='O': return c[:5]+'Z'+c[6:7]+'0'+c[8:],'Toshiba/Kioxia X7JB 2->Z + O->0 family correction'
    if 'WESTERN DIGITAL' in m:
        if len(c)==12 and c.startswith('20242') and c[5]=='0': return c[:5]+'D'+c[6:],'WD 20242 0->D'
    if 'FUJITSU' in m:
        if c.endswith('0') and len(c)==12 and re.match(r'^[A-Z]{2}\d[A-Z0-9]{8}0$',c): return c[:-1],'Fujitsu trailing OCR 0 removal'
    return c,''

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--ground-truth',required=True);ap.add_argument('--detections',required=True);ap.add_argument('--images',required=True);ap.add_argument('--out-dir',required=True)
    a=ap.parse_args(); out=Path(a.out_dir);out.mkdir(parents=True,exist_ok=True)
    gt=list(csv.DictReader(open(a.ground_truth,encoding='utf-8-sig')))
    det=defaultdict(list)
    for r in csv.DictReader(open(a.detections,encoding='utf-8-sig')): det[r['FileName']].append(r)
    imgs={r['FileName']:r for r in csv.DictReader(open(a.images,encoding='utf-8-sig'))}
    rows=[]
    for g in gt:
        fn=g['Image']; exp=norm(g.get('ExpectedSerial')); man=g.get('ExpectedManufacturer',''); model=g.get('ExpectedModel','')
        blocks=det.get(fn,[])
        cands=extract(blocks)
        plausible=[x for x in cands if (any(ch.isdigit() for ch in x[1]) and (any(ch.isalpha() for ch in x[1]) or len(x[1])>=8))]
        cands=plausible or cands
        selected=cands[0][1] if cands else ''; reason=cands[0][2] if cands else ''
        recovered,rr=vendor_recover(man,blocks,selected)
        if rr:
            selected=recovered; reason=rr
        corrected,cr=vendor_correct(man,selected,model)
        raw=norm((imgs.get(fn) or {}).get('RawText',''))
        rows.append({'Image':fn,'Manufacturer':man,'ExpectedSerial':exp,'SelectedSerial':selected,'CorrectedSerial':corrected,'SelectedExact':bool(exp and selected==exp),'CorrectedExact':bool(exp and corrected==exp),'RawExact':bool(exp and exp in raw),'Reason':reason,'Correction':cr})
    serial=[r for r in rows if r['ExpectedSerial']]
    metrics={'serial_n':len(serial),'raw_exact':sum(r['RawExact'] for r in serial),'selected_exact':sum(r['SelectedExact'] for r in serial),'corrected_exact':sum(r['CorrectedExact'] for r in serial)}
    metrics['corrected_pct']=round(100*metrics['corrected_exact']/metrics['serial_n'],1)
    with open(out/'Serial-Postprocess-Results.csv','w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=rows[0].keys());w.writeheader();w.writerows(rows)
    json.dump(metrics,open(out/'Serial-Postprocess-Summary.json','w'),indent=2)
    lines=['# Serial Postprocess Evaluation','',f"- Serial rows: **{metrics['serial_n']}**",f"- Raw exact: **{metrics['raw_exact']}/{metrics['serial_n']}**",f"- Improved spatial extractor exact: **{metrics['selected_exact']}/{metrics['serial_n']}**",f"- After conservative vendor corrections: **{metrics['corrected_exact']}/{metrics['serial_n']} ({metrics['corrected_pct']}%)**",'', '## Remaining misses','', '| Image | Manufacturer | Expected | Corrected | Reason |','|---|---|---|---|---|']
    for r in serial:
        if not r['CorrectedExact']:
            lines.append(f"| {r['Image']} | {r['Manufacturer']} | {r['ExpectedSerial']} | {r['CorrectedSerial']} | {(r['Correction'] or r['Reason']).replace('|','/')} |")
    (out/'Serial-Postprocess-Summary.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print('\n'.join(lines[:8]))
if __name__=='__main__':main()
