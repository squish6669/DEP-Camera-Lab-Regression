import argparse,csv,json,re
from collections import defaultdict
from pathlib import Path

DS_BINS={f'DS-{i:02d}' for i in range(1,13)}


def norm_serial(value):
    return re.sub(r'[^A-Z0-9]','',(value or '').upper())


def read_csv(path):
    if not path:
        return []
    with open(path,encoding='utf-8-sig',newline='') as f:
        return list(csv.DictReader(f))


def build_cert_index(rows):
    """Index only explicit certificate serials. No fuzzy or inferred matching is allowed."""
    index=defaultdict(list)
    for row in rows:
        serial=norm_serial(row.get('Serial',''))
        if not serial:
            continue
        index[serial].append(row)
    return index


def build_assignments(rows):
    out={}
    for row in rows:
        image=(row.get('Image') or '').strip()
        serial=norm_serial(row.get('Serial',''))
        bin_id=(row.get('Bin') or '').strip().upper()
        if not image or not serial:
            raise ValueError('Every destruction assignment requires Image and Serial')
        if bin_id not in DS_BINS:
            raise ValueError(f'Invalid destruction bin {bin_id!r}; allowed bins are DS-01 through DS-12')
        key=(image,serial)
        if key in out:
            raise ValueError(f'Duplicate destruction assignment for {image} / {serial}')
        out[key]=bin_id
    return out


def main():
    ap=argparse.ArgumentParser(description='Build Camera Lab operational records from production inference. Certificate matching is unique exact normalized serial only.')
    ap.add_argument('--inference',required=True)
    ap.add_argument('--cert-index',help='Optional CSV with required Serial and optional CertId, CertPath columns')
    ap.add_argument('--destruction-assignments',help='Optional CSV with Image, Serial, Bin. Bin must be DS-01..DS-12.')
    ap.add_argument('--out-dir',required=True)
    a=ap.parse_args()

    inference=read_csv(a.inference)
    if not inference:
        raise SystemExit('Inference file is empty')
    cert_rows=read_csv(a.cert_index)
    certs=build_cert_index(cert_rows)
    assignments=build_assignments(read_csv(a.destruction_assignments))
    cert_lookup_performed=bool(a.cert_index)

    output=[]
    for src in inference:
        image=(src.get('Image') or '').strip()
        serial=norm_serial(src.get('Serial',''))
        matches=certs.get(serial,[]) if serial and cert_lookup_performed else []

        if not cert_lookup_performed:
            lookup='NOT_CHECKED'
        elif not serial:
            lookup='REVIEW'
        elif len(matches)==0:
            lookup='NO_CERT'
        elif len(matches)==1:
            lookup='CERT_FOUND'
        else:
            # Duplicate exact cert records require a human decision; never silently choose one.
            lookup='REVIEW'

        cert=matches[0] if lookup=='CERT_FOUND' else {}
        key=(image,serial)
        bin_id=assignments.get(key,'')
        if bin_id and lookup!='NO_CERT':
            raise SystemExit(f'Destruction assignment rejected for {image}: lookup status is {lookup}, not NO_CERT')

        row=dict(src)
        row.update({
            'LookupStatus':lookup,
            'CertMatchMethod':'EXACT_NORMALIZED_SERIAL' if lookup=='CERT_FOUND' else '',
            'CertMatchCount':len(matches),
            'CertId':(cert.get('CertId') or '').strip(),
            'CertPath':(cert.get('CertPath') or '').strip(),
            'PendingDestructionBin':bin_id,
            'DestructionStatus':'PENDING_DESTRUCTION' if bin_id else '',
        })
        output.append(row)

    out=Path(a.out_dir); out.mkdir(parents=True,exist_ok=True)
    fields=list(output[0].keys())
    with open(out/'Camera-Lab-Operational-Records.csv','w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(output)
    with open(out/'Camera-Lab-Operational-Records.json','w',encoding='utf-8') as f:
        json.dump(output,f,indent=2)

    summary={
        'records':len(output),
        'cert_lookup_performed':cert_lookup_performed,
        'cert_found':sum(r['LookupStatus']=='CERT_FOUND' for r in output),
        'no_cert':sum(r['LookupStatus']=='NO_CERT' for r in output),
        'review':sum(r['LookupStatus']=='REVIEW' for r in output),
        'not_checked':sum(r['LookupStatus']=='NOT_CHECKED' for r in output),
        'pending_destruction':sum(bool(r['PendingDestructionBin']) for r in output),
        'match_policy':'unique exact normalized serial only',
        'allowed_destruction_bins':sorted(DS_BINS),
    }
    with open(out/'Camera-Lab-Operational-Summary.json','w',encoding='utf-8') as f:
        json.dump(summary,f,indent=2)
    print(json.dumps(summary,indent=2))


if __name__=='__main__':
    main()
