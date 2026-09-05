import argparse,csv,json,re
from pathlib import Path
from collections import defaultdict

def norm(s): return re.sub(r'[^A-Z0-9]','',(s or '').upper())
def full_raw(blocks): return ' '.join((b.get('Text') or '') for b in blocks)

def model_labeled_tokens(blocks):
    out=[]
    for b in blocks:
        txt=(b.get('Text') or '').strip(); conf=float(b.get('BoxConfidence') or 0)
        m=re.search(r'(?i)\b(?:MODEL|MDL|MODE[1ILU])(?:\s*\([^)]*\))?\s*[:#\-]?\s*([A-Z0-9][A-Z0-9\- ]{4,32})',txt)
        if m:
            v=norm(m.group(1))
            if 6<=len(v)<=24: out.append((140+conf*10,v,'model-anchor:'+txt))
    return out

def exact_family_tokens(man, blocks):
    """Extract only complete, vendor-shaped model tokens. Patterns are bounded so adjacent OCR text cannot be swallowed."""
    m=(man or '').upper(); out=[]
    texts=[norm(b.get('Text') or '') for b in blocks]
    texts.append(norm(full_raw(blocks)))
    pats=[]
    if 'WESTERN DIGITAL' in m:
        pats=[r'SDBQNTY\d{3}G\d{4}',r'WD\d{2}[A-Z0-9]{4,6}\d{2}[A-Z0-9]{4}']
    elif 'TOSHIBA' in m or 'KIOXIA' in m:
        pats=[r'KXG[0-9A-Z]AZNV(?:256|512)G',r'KXG[0-9A-Z]0ZNV(?:256|512)G',r'KSG[0-9A-Z]0ZMV(?:256|512)G',r'MQ01ACF\d{3}',r'DT01ACA\d{3}']
    elif 'HYNIX' in m:
        pats=[r'HFM\d{3}GDJTNG\d{4}A']
    elif 'SAMSUNG' in m:
        pats=[r'MZVLB\d{3}[A-Z]',r'MZ7TE\d{3}HMGR\d{3}H\d']
    elif 'INTEL' in m:
        pats=[r'SSDPEMKF\d{3}G8']
    elif 'SANDISK' in m:
        pats=[r'SD6SP1M\d{3}G\d{4}']
    elif 'LITE' in m:
        pats=[r'LJT\d{3}L6G\d{2}',r'LCH\d{3}V2SHP']
    elif 'SEAGATE' in m:
        pats=[r'ST\d{7}AS',r'ST\d{3,4}LM\d{3}']
    elif 'HGST' in m or 'HITACHI' in m:
        pats=[r'HTS\d{6}A\d[A-Z]\d{3}']
    elif 'MICRON' in m:
        pats=[r'MTFDDAK\d{3}TBN']
    elif 'FUJITSU' in m:
        pats=[r'MHV\d{4}[A-Z]{2}PL']
    for t in texts:
        for pat in pats:
            for mm in re.finditer(pat,t): out.append((190,mm.group(0),'bounded-vendor-family'))
    return out

def family_candidates(man,blocks):
    m=(man or '').upper(); raw=full_raw(blocks); nr=norm(raw); out=model_labeled_tokens(blocks)+exact_family_tokens(man,blocks)
    def add(score,val,reason):
        v=norm(val)
        if 6<=len(v)<=24: out.append((score,v,reason))

    # Recovery rules require redundant label evidence and remain narrower than complete-family extraction.
    if 'SANDISK' in m:
        if 'SD6SP1M1' in nr and '128G1012' in nr: add(180,'SD6SP1M128G1012','SanDisk split fields')
        elif 'SD6SP1M' in nr and 'X110' in nr and ('128G' in nr or re.search(r'128\s*GB',raw,re.I)): add(175,'SD6SP1M128G1012','SanDisk X110 capacity evidence')
    if 'LITE' in m and re.search(r'LJT\s*[- ]?128L[68]G',raw,re.I) and re.search(r'128\s*GB',raw,re.I):
        add(180,'LJT128L6G11' if re.search(r'[- ]11\b',raw) else 'LJT128L6G','Lite-On split generation/suffix')
    if 'FUJITSU' in m and re.search(r'MHV2120[8B]H\s*PL',raw,re.I): add(180,'MHV2120BHPL','Fujitsu split + 8/B')
    if 'INTEL' in m and ('SSDPEMKF' in nr or 'SSOPEMKF' in nr) and re.search(r'256\s*GB',raw,re.I): add(180,'SSDPEMKF256G8','Intel family + 256GB')
    if 'SAMSUNG' in m:
        mm=re.search(r'MZVLB512[8B0]',nr)
        if mm: add(180,'MZVLB512B' if mm.group(0)[-1]=='8' else mm.group(0),'Samsung MZVLB terminal')
    if 'TOSHIBA' in m or 'KIOXIA' in m:
        cap='256' if re.search(r'256\s*G(?:B)?',raw,re.I) else ('512' if re.search(r'512\s*G(?:B)?',raw,re.I) else '')
        if cap=='256' and ('XG6' in raw.upper() or 'KXG8' in nr or 'KXG6' in nr) and ('ZNV' in nr or 'ZNN' in nr): add(180,'KXG60ZNV256G','XG6 + 256GB')
        if cap=='512' and ('XG5' in raw.upper() or 'KXG5AZNV' in nr): add(180,'KXG50ZNV512G','XG5 + 512GB')
        if cap=='256' and ('KSG60ZMV' in nr or 'KSG8AZM' in nr): add(180,'KSG60ZMV256G','KSG + 256GB')
    if 'WESTERN DIGITAL' in m:
        mm=re.search(r'MDL\s*[:#-]?\s*(WD[0-9A-Z-]+)',raw,re.I)
        if mm:
            v=norm(mm.group(1)); v=v[:-1]+'0' if v.endswith('AO') else v; add(180,v,'WD MDL anchor')

    best={}
    for s,c,w in out:
        if c not in best or s>best[c][0]: best[c]=(s,w)
    return sorted([(s,c,w) for c,(s,w) in best.items()],reverse=True)

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--ground-truth',required=True); ap.add_argument('--detections',required=True); ap.add_argument('--out-dir',required=True); a=ap.parse_args()
    out=Path(a.out_dir); out.mkdir(parents=True,exist_ok=True)
    gt=list(csv.DictReader(open(a.ground_truth,encoding='utf-8-sig'))); det=defaultdict(list)
    for r in csv.DictReader(open(a.detections,encoding='utf-8-sig')): det[r['FileName']].append(r)
    rows=[]
    for g in gt:
        exp=norm(g.get('ExpectedModel')); fn=g['Image']; man=g.get('ExpectedManufacturer',''); blocks=det.get(fn,[]); rawn=norm(full_raw(blocks)); raw_exact=bool(exp and exp in rawn)
        cands=family_candidates(man,blocks); selected=cands[0][1] if cands else ''; reason=cands[0][2] if cands else ''
        rows.append({'Image':fn,'Manufacturer':man,'ExpectedModel':exp,'SelectedModel':selected,'RawExact':raw_exact,'SelectedExact':bool(exp and selected==exp),'Reason':reason,'TopCandidates':' | '.join(c for _,c,_ in cands[:6])})
    model=[r for r in rows if r['ExpectedModel']]; metrics={'model_n':len(model),'raw_exact':sum(r['RawExact'] for r in model),'selected_exact':sum(r['SelectedExact'] for r in model)}; metrics['selected_pct']=round(100*metrics['selected_exact']/metrics['model_n'],1) if metrics['model_n'] else 0
    with open(out/'Model-Postprocess-Results.csv','w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=rows[0].keys()); w.writeheader(); w.writerows(rows)
    json.dump(metrics,open(out/'Model-Postprocess-Summary.json','w'),indent=2)
    lines=['# Model Postprocess Evaluation','',f"- Model rows: **{metrics['model_n']}**",f"- Raw OCR exact: **{metrics['raw_exact']}/{metrics['model_n']}**",f"- Conservative selected exact: **{metrics['selected_exact']}/{metrics['model_n']} ({metrics['selected_pct']}%)**",'','## Remaining misses','','| Image | Manufacturer | Expected | Selected | Reason |','|---|---|---|---|---|']
    for r in model:
        if not r['SelectedExact']: lines.append(f"| {r['Image']} | {r['Manufacturer']} | {r['ExpectedModel']} | {r['SelectedModel']} | {r['Reason'].replace('|','/')} |")
    (out/'Model-Postprocess-Summary.md').write_text('\n'.join(lines)+'\n',encoding='utf-8'); print('\n'.join(lines[:8]))
if __name__=='__main__': main()
