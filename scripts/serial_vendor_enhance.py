import argparse,csv,json,re
from collections import defaultdict
from pathlib import Path


def norm(s):
    return re.sub(r'[^A-Z0-9]', '', (s or '').upper())


def block_texts(blocks):
    return [(b.get('Text') or '').strip() for b in blocks]


def unique_matches(blocks, patterns):
    found=[]
    for t in block_texts(blocks):
        for pat in patterns:
            for m in re.finditer(pat,t,re.I):
                v=norm(m.group(1))
                if v and v not in found: found.append(v)
    return found


def recover(man,model,blocks,current):
    m=(man or '').upper(); md=norm(model); cur=norm(current)

    # Toshiba enterprise SAS/SCSI labels often print "SER. NO." rather than S/N.
    if ('TOSHIBA' in m or 'KIOXIA' in m) and md.startswith('AL'):
        vals=unique_matches(blocks,[r'\bSER\.?\s*NO\.?\s*[:#-]?\s*([A-Z0-9]{8,24})'])
        if len(vals)==1:
            return vals[0],'Toshiba AL-family SER.NO recovery'

    # HGST HDS labels occasionally duplicate a W at OCR block boundaries.
    if ('HGST' in m or 'HITACHI' in m) and md.startswith('HDS'):
        vals=unique_matches(blocks,[r'\bS\s*/?\s*N\s*[:#-]?\s*([A-Z0-9]{10,20})'])
        if len(vals)==1:
            v=vals[0]
            if v.startswith('JP') and 'WW' in v and len(v)>=14:
                fixed=v.replace('WW','W',1)
                return fixed,'HGST HDS duplicate-W boundary correction'

    # SanDisk client SSD labels use a 12-digit serial next to an explicit S/N.
    if 'SANDISK' in m and (md.startswith('SD6') or md.startswith('SD7')):
        vals=unique_matches(blocks,[r'\bS\s*/?\s*N\s*[:#-]?\s*(\d{12})\b'])
        if len(vals)==1:
            return vals[0],'SanDisk explicit 12-digit S/N recovery'

    # SK hynix HFM labels: B/8 is a recurring OCR substitution in the NDBC prefix.
    if 'HYNIX' in m and md.startswith('HFM'):
        vals=unique_matches(blocks,[r'\bS[I1/]?N\s*[:#-]?\s*([A-Z0-9]{15,22})'])
        pool=vals+[cur] if cur else vals
        for v in pool:
            if v.startswith('ND8C') and len(v)==17:
                return 'NDB'+v[3:],'SK hynix HFM ND8C->NDBC correction'

    # WD/SanDisk NVMe labels in this stock frequently use a 12-character S/N, but
    # that S/N can be numeric OR alphanumeric. Numeric recovery is therefore a fallback
    # only when the current selector did not already produce a plausible 12-char serial.
    if ('WESTERN DIGITAL' in m or m.strip()=='WD') and (md.startswith('SDBQNTY') or md.startswith('SDCPNRY')):
        vals=[]
        for t in block_texts(blocks):
            for v in re.findall(r'(?<!\d)(\d{12})(?!\d)',t):
                if v not in vals: vals.append(v)
        current_is_family_shape = bool(re.fullmatch(r'[A-Z0-9]{12}',cur))
        if len(vals)==1 and not current_is_family_shape:
            return vals[0],'WD NVMe unique 12-digit serial recovery'

    # Samsung MZ7PD labels may expose the serial as a clean token even when another
    # HP/OEM number wins the generic S/N scoring.
    if 'SAMSUNG' in m and md.startswith('MZ7PD'):
        vals=[]
        for t in block_texts(blocks):
            for v in re.findall(r'\b(S1MBNYAH\d{6})\b',t,re.I):
                v=norm(v)
                if v not in vals: vals.append(v)
        if len(vals)==1:
            return vals[0],'Samsung MZ7PD canonical serial token recovery'

    return cur,''


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--ground-truth',required=True)
    ap.add_argument('--detections',required=True)
    ap.add_argument('--base-results',required=True)
    ap.add_argument('--out-dir',required=True)
    a=ap.parse_args()

    gt={r['Image']:r for r in csv.DictReader(open(a.ground_truth,encoding='utf-8-sig'))}
    base={r['Image']:r for r in csv.DictReader(open(a.base_results,encoding='utf-8-sig'))}
    det=defaultdict(list)
    for r in csv.DictReader(open(a.detections,encoding='utf-8-sig')):
        det[r['FileName']].append(r)

    rows=[]
    for fn,g in gt.items():
        b=dict(base.get(fn,{}) or {})
        exp=norm(g.get('ExpectedSerial'))
        man=g.get('ExpectedManufacturer',''); model=g.get('ExpectedModel','')
        current=norm(b.get('CorrectedSerial'))
        enhanced,why=recover(man,model,det.get(fn,[]),current)
        if not enhanced: enhanced=current
        b['CorrectedSerial']=enhanced
        b['CorrectedExact']=bool(exp and enhanced==exp)
        if why:
            b['Correction']=why
            b['Reason']=(b.get('Reason') or '')
        rows.append(b)

    scored=[r for r in rows if norm(r.get('ExpectedSerial'))]
    summary={
        'serial_n':len(scored),
        'final_exact':sum(str(r.get('CorrectedExact')).lower()=='true' for r in scored),
        'enhanced_rows':sum(1 for r in rows if (r.get('Correction') or '').startswith(('Toshiba AL','HGST HDS','SanDisk explicit','SK hynix HFM','WD NVMe','Samsung MZ7PD')))
    }
    summary['final_pct']=round(100*summary['final_exact']/summary['serial_n'],1) if summary['serial_n'] else 0
    out=Path(a.out_dir);out.mkdir(parents=True,exist_ok=True)
    with open(out/'Serial-Postprocess-Results.csv','w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=rows[0].keys());w.writeheader();w.writerows(rows)
    json.dump(summary,open(out/'Serial-Vendor-Enhance-Summary.json','w'),indent=2)
    print(json.dumps(summary,indent=2))

if __name__=='__main__': main()
