import argparse,csv,json,re
from pathlib import Path
from collections import defaultdict

def norm(s): return re.sub(r'[^A-Z0-9]','',(s or '').upper())

def model_labeled_tokens(blocks):
    out=[]
    for b in blocks:
        txt=(b.get('Text') or '').strip()
        conf=float(b.get('BoxConfidence') or 0)
        source=b.get('_Source','full')
        m=re.search(r'(?i)\b(?:MODEL|MDL|MODE[1ILU])(?:\s*\([^)]*\))?\s*[:#\-]?\s*([A-Z0-9][A-Z0-9\- ]{4,32})',txt)
        if m:
            v=norm(m.group(1))
            if 6<=len(v)<=24:
                bonus=22 if source=='targeted' else 0
                out.append((140+conf*10+bonus,v,f'{source}-model-anchor:'+txt))
    return out

def full_raw(blocks):
    return ' '.join((b.get('Text') or '') for b in blocks)

def family_candidates(man,blocks):
    m=(man or '').upper(); raw=full_raw(blocks); nr=norm(raw)
    out=model_labeled_tokens(blocks)
    def add(score,val,reason):
        v=norm(val)
        if 6<=len(v)<=24: out.append((score,v,reason))

    families=[]
    if 'SAMSUNG' in m:
        families=[r'MZVLB[0-9A-Z]{4,10}',r'MZ7[A-Z0-9]{6,18}',r'MZ75E[0-9A-Z]{3,12}']
    elif 'INTEL' in m:
        families=[r'SSDPEM[A-Z0-9]{6,16}',r'SSDPEK[A-Z0-9]{6,16}']
    elif 'TOSHIBA' in m or 'KIOXIA' in m:
        families=[r'KXG[0-9A-Z]{8,16}',r'KSG[0-9A-Z]{8,16}',r'MQ01[A-Z0-9]{5,12}',r'DT01[A-Z0-9]{5,12}']
    elif 'WESTERN DIGITAL' in m:
        families=[r'SDBQNTY[0-9A-Z]{5,16}',r'WD[0-9A-Z]{8,18}',r'HTS[0-9A-Z]{8,18}']
    elif 'MICRON' in m:
        families=[r'MTFDDA[A-Z0-9]{6,16}']
    elif 'HYNIX' in m:
        families=[r'HFM[0-9A-Z]{8,20}']
    elif 'SANDISK' in m:
        families=[r'SD6SP1M[0-9A-Z]{4,16}']
    elif 'LITE' in m:
        families=[r'LJT[0-9A-Z]{6,16}',r'LCH[0-9A-Z]{6,16}']
    elif 'SEAGATE' in m:
        families=[r'ST[0-9]{3,5}[A-Z0-9]{4,12}']
    elif 'HGST' in m or 'HITACHI' in m:
        families=[r'HTS[0-9A-Z]{8,18}']
    elif 'FUJITSU' in m:
        families=[r'MHV[0-9A-Z]{6,16}']
    elif 'CRUCIAL' in m:
        families=[r'CT[0-9]{3,4}MX[0-9A-Z]{5,12}']

    # Exact family tokens remain useful, but targeted-reread tokens get a modest priority boost.
    for b in blocks:
        t=norm(b.get('Text') or '')
        src=b.get('_Source','full')
        base=150 if src=='targeted' else 130
        for pat in families:
            for mm in re.finditer(pat,t): add(base,mm.group(0),f'{src}-vendor-family')

    if 'SANDISK' in m:
        if 'SD6SP1M1' in nr and '128G1012' in nr:
            add(170,'SD6SP1M128G1012','SanDisk split model join')
        elif 'SD6SP1M' in nr and 'X110' in nr and ('128G' in nr or re.search(r'\b128\s*GB\b',raw,re.I)):
            add(160,'SD6SP1M128G1012','SanDisk X110 + 128GB family recovery')

    if 'LITE' in m and re.search(r'LJT\s*[- ]?128L[68]G',raw,re.I) and re.search(r'\b128\s*GB\b',raw,re.I):
        suffix='11' if re.search(r'[- ]11\b',raw) else ''
        add(170,'LJT128L6G'+suffix,'Lite-On 128GB + L6G family recovery')

    if 'FUJITSU' in m and re.search(r'MHV2120[8B]H\s*PL',raw,re.I):
        add(170,'MHV2120BHPL','Fujitsu split model + 8/B correction')

    if 'TOSHIBA' in m or 'KIOXIA' in m:
        cap=''
        if re.search(r'\b256\s*G(?:B)?\b',raw,re.I): cap='256'
        elif re.search(r'\b512\s*G(?:B)?\b',raw,re.I): cap='512'
        if ('XG6' in raw.upper() or 'KXG8' in nr or 'KXG6' in nr) and cap=='256' and ('ZNV' in nr or 'ZNN' in nr):
            add(175,'KXG60ZNV256G','Kioxia XG6 + 256GB repeated evidence')
        if ('XG5' in raw.upper() or 'KXG5AZNV' in nr) and cap=='512':
            add(175,'KXG50ZNV512G','Kioxia XG5 + 512GB regulatory evidence')
        if ('KSG60ZMV' in nr or 'KSG8AZM' in nr) and cap=='256':
            add(175,'KSG60ZMV256G','Kioxia/Toshiba KSG + 256GB evidence')

    if 'INTEL' in m and ('SSDPEMKF' in nr or 'SSOPEMKF' in nr) and re.search(r'\b256\s*GB\b',raw,re.I):
        add(175,'SSDPEMKF256G8','Intel SSDPEMKF + repeated 256GB evidence')

    if 'SAMSUNG' in m:
        mm=re.search(r'MZVLB512[8B0]',nr)
        if mm:
            tail=mm.group(0)[-1]
            if tail=='8': add(170,'MZVLB512B','Samsung MZVLB terminal 8->B')
            else: add(150,mm.group(0),'Samsung MZVLB exact family')

    if 'WESTERN DIGITAL' in m:
        mm=re.search(r'MDL\s*[:#-]?\s*(WD[0-9A-Z-]+)',raw,re.I)
        if mm:
            v=norm(mm.group(1))
            if v.endswith('AO'): v=v[:-1]+'0'
            add(175,v,'WD MDL anchored model')

    best={}
    for s,c,w in out:
        if c not in best or s>best[c][0]: best[c]=(s,w)
    return sorted([(s,c,w) for c,(s,w) in best.items()],reverse=True)

def load_det(path,source):
    d=defaultdict(list)
    if not path: return d
    with open(path,encoding='utf-8-sig') as f:
        for r in csv.DictReader(f):
            r['_Source']=source; d[r['FileName']].append(r)
    return d

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--ground-truth',required=True)
    ap.add_argument('--detections',required=True)
    ap.add_argument('--targeted-detections')
    ap.add_argument('--out-dir',required=True)
    a=ap.parse_args(); out=Path(a.out_dir); out.mkdir(parents=True,exist_ok=True)
    gt=list(csv.DictReader(open(a.ground_truth,encoding='utf-8-sig')))
    full=load_det(a.detections,'full'); targeted=load_det(a.targeted_detections,'targeted')
    rows=[]
    for g in gt:
        exp=norm(g.get('ExpectedModel')); fn=g['Image']; man=g.get('ExpectedManufacturer','')
        blocks=full.get(fn,[])+targeted.get(fn,[]); cands=family_candidates(man,blocks)
        selected=cands[0][1] if cands else ''; reason=cands[0][2] if cands else ''
        rawn=norm(full_raw(full.get(fn,[])))
        raw_exact=bool(exp and exp in rawn)
        rows.append({'Image':fn,'Manufacturer':man,'ExpectedModel':exp,'SelectedModel':selected,'RawExact':raw_exact,'SelectedExact':bool(exp and selected==exp),'Reason':reason,'TopCandidates':' | '.join(c for _,c,_ in cands[:6])})
    model=[r for r in rows if r['ExpectedModel']]
    metrics={'model_n':len(model),'raw_exact':sum(r['RawExact'] for r in model),'selected_exact':sum(r['SelectedExact'] for r in model)}
    metrics['selected_pct']=round(100*metrics['selected_exact']/metrics['model_n'],1) if metrics['model_n'] else 0
    with open(out/'Model-Postprocess-Results.csv','w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=rows[0].keys());w.writeheader();w.writerows(rows)
    json.dump(metrics,open(out/'Model-Postprocess-Summary.json','w'),indent=2)
    lines=['# Model Postprocess Evaluation','',f"- Model rows: **{metrics['model_n']}**",f"- Raw OCR exact: **{metrics['raw_exact']}/{metrics['model_n']}**",f"- Conservative selected exact: **{metrics['selected_exact']}/{metrics['model_n']} ({metrics['selected_pct']}%)**",'','## Remaining misses','','| Image | Manufacturer | Expected | Selected | Reason |','|---|---|---|---|---|']
    for r in model:
        if not r['SelectedExact']:
            lines.append(f"| {r['Image']} | {r['Manufacturer']} | {r['ExpectedModel']} | {r['SelectedModel']} | {r['Reason'].replace('|','/')} |")
    (out/'Model-Postprocess-Summary.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print('\n'.join(lines[:8]))
if __name__=='__main__': main()
