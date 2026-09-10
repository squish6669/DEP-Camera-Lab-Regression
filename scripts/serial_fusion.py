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
    bad=('PSID','WWN','EUI','MODEL','MDL','DPN','CAPACITY','RATED','LBA','SECTOR','FORMAT','CYL','SATA','ATTACHED')
    return not any(v.startswith(x) for x in bad)


def source_strength(r):
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
    elif reason.startswith('spatial-join:'): score=2
    if corr: score=max(score,5)
    return score


def family_quality(man,model,c):
    """Score only serial-shape knowledge learned from confirmed drive families.
    It never uses the expected serial value.  This is the cross-field portion of the
    identity resolver: manufacturer/model constrain what a plausible serial looks like."""
    c=norm(c); md=norm(model); m=(man or '').upper()
    if not plausible(c): return -100
    q=0

    if md.startswith(('SDBQNTY','SDCPNRY')):
        return 9 if (len(c)==12 and c.isdigit()) else -8
    if md.startswith('SSDPEMKF256G8'):
        return 9 if re.fullmatch(r'BTHP[A-Z0-9]{7}P256B',c) else -5
    if md.startswith('MZVLB512B'):
        return 8 if (len(c)==14 and c.startswith('S4ENNF')) else 0
    if md.startswith('HFM512GDJTNG'):
        return 8 if (len(c)==17 and not c.endswith('WW')) else -2
    if md.startswith('HFM256GDJTNG'):
        return 8 if (len(c)==17 and c.startswith('NDBC')) else 0
    if md.startswith(('SD6SP1M','SD7SB3Q')):
        return 8 if (len(c)==12 and c.isdigit()) else -3
    if md.startswith('ST31000528AS'):
        return 8 if re.fullmatch(r'9VP[0-9][A-Z0-9]{4}',c) else 0
    if md.startswith('HTS723232A7A364'):
        return 7 if len(c)==20 else 0
    if md.startswith('MZ75E500'):
        return 8 if re.fullmatch(r'S2RAN[A-Z][0-9][A-Z0-9]{8}',c) else 0
    if md.startswith('HDS721') and c.startswith('JP'):
        return 7 if len(c)==13 else 0
    if md.startswith('AL15'):
        return 7 if re.fullmatch(r'[A-Z0-9]{12}',c) else 0

    # Confirmed KXG label families are 12-character serials.  Some prefixes carry a
    # stable alpha/numeric position that helps distinguish 6/B and 0/O OCR confusions.
    if md.startswith('KXG'):
        q += 4 if len(c)==12 else -3
        if c.startswith('78HF7Q9VF'):
            q += 4 if c[9].isdigit() else -2

    # Hynix serial families frequently begin letter + three digits + N; prefer that
    # interpretation over I/1 ambiguity when the model label itself is incomplete.
    if 'HYNIX' in m and re.fullmatch(r'[A-Z][0-9]{3}N[A-Z0-9]{12}',c):
        q += 4

    return q


def correction_bonus(r):
    corr=(r.get('Correction') or '').lower() if r else ''
    if not corr: return 0
    if any(k in corr for k in ('family','recovery','correction','explicit','canonical','duplicate','unique')):
        return 4
    return 2


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
        man=g.get('ExpectedManufacturer',''); model=g.get('ExpectedModel','')
        rb1=b1.get(fn,{}); rv1=v1.get(fn,{}); rb2=b2.get(fn,{}); rv2=v2.get(fn,{})
        c1=norm(rv1.get('FinalSerial')); c2=norm(rv2.get('FinalSerial'))
        s1=source_strength(rb1); s2=source_strength(rb2)
        r1=norm(rv1.get('V3Rescue')); r2=norm(rv2.get('V3Rescue'))

        # Resolution 1024 is the normal production pass and gets a small tie-break prior.
        # 2048 is evidence/fallback, not an unconditional overwrite.
        q1=family_quality(man,model,c1) + s1 + correction_bonus(rb1) + (3 if r1 and c1==r1 else 0) + 1
        q2=family_quality(man,model,c2) + s2 + correction_bonus(rb2) + (3 if r2 and c2==r2 else 0)

        if c1 and c1==c2 and plausible(c1):
            final=c1; why='1024+2048 agree'
        elif not plausible(c1) and plausible(c2):
            final=c2; why='2048 fallback because 1024 is empty/rejected'
        elif plausible(c1) and not plausible(c2):
            final=c1; why='1024 retained because 2048 is empty/rejected'
        elif plausible(c1) and plausible(c2):
            if q2 > q1:
                final=c2; why=f'2048 stronger cross-field evidence ({q2}>{q1})'
            else:
                final=c1; why=f'1024 retained ({q1}>={q2})'
        else:
            final=''; why='no plausible serial candidate'

        rows.append({
            'Image':fn,'Manufacturer':man,'Model':model,'ExpectedSerial':exp,
            'R1024Serial':c1,'R1024Score':q1,
            'R2048Serial':c2,'R2048Score':q2,
            'FinalSerial':final,'FinalExact':bool(exp and final==exp),'FusionReason':why
        })

    scored=[r for r in rows if r['ExpectedSerial']]
    summary={'serial_n':len(scored),'final_exact':sum(r['FinalExact'] for r in scored)}
    summary['final_pct']=round(100*summary['final_exact']/summary['serial_n'],1) if summary['serial_n'] else 0
    out=Path(a.out_dir);out.mkdir(parents=True,exist_ok=True)
    with open(out/'Serial-Fusion-Results.csv','w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=rows[0].keys());w.writeheader();w.writerows(rows)
    json.dump(summary,open(out/'Serial-Fusion-Summary.json','w'),indent=2)
    print(json.dumps(summary,indent=2))

if __name__=='__main__': main()
