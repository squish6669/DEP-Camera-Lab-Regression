import argparse,csv,json,re
from collections import defaultdict
from pathlib import Path


def norm_serial(value):
    return re.sub(r'[^A-Z0-9]','',(value or '').upper())


def read_csv(path):
    with open(path,encoding='utf-8-sig',newline='') as f:
        return list(csv.DictReader(f))


def build_cert_index(rows):
    """Index only explicit certificate serials. No fuzzy or inferred matching is allowed."""
    index=defaultdict(list)
    for row in rows:
        serial=norm_serial(row.get('Serial',''))
        if serial:
            index[serial].append(row)
    return index


def main():
    ap=argparse.ArgumentParser(description='Reconcile prior Camera Lab NO_CERT records against a later explicit certificate index using unique exact normalized serial only.')
    ap.add_argument('--records',required=True,help='Camera-Lab-Operational-Records.csv from the operational bridge')
    ap.add_argument('--cert-index',required=True,help='Current explicit certificate CSV with Serial and optional CertId, CertPath')
    ap.add_argument('--out-dir',required=True)
    a=ap.parse_args()

    records=read_csv(a.records)
    cert_rows=read_csv(a.cert_index)
    if not records:
        raise SystemExit('Operational records file is empty')
    certs=build_cert_index(cert_rows)

    output=[]
    for src in records:
        row=dict(src)
        original=(src.get('LookupStatus') or '').strip().upper()
        serial=norm_serial(src.get('Serial',''))
        matches=certs.get(serial,[]) if serial else []

        status='NOT_ELIGIBLE'
        action='NONE'
        cert={}
        method=''

        # Reconciliation is intentionally limited to records previously established as NO_CERT.
        # CERT_FOUND / REVIEW / NOT_CHECKED are never silently reclassified here.
        if original=='NO_CERT':
            if not serial:
                status='REVIEW'
                action='MANUAL_REVIEW'
            elif len(matches)==0:
                status='STILL_NO_CERT'
            elif len(matches)==1:
                status='RECONCILED_CERT_FOUND'
                action='REMOVE_FROM_PENDING_DESTRUCTION' if src.get('PendingDestructionBin') else 'CERT_FOUND'
                cert=matches[0]
                method='EXACT_NORMALIZED_SERIAL'
            else:
                status='REVIEW'
                action='MANUAL_REVIEW'

        row.update({
            'ReconciliationStatus':status,
            'ReconciliationMatchMethod':method,
            'ReconciliationMatchCount':len(matches) if original=='NO_CERT' else 0,
            'ReconciledCertId':(cert.get('CertId') or '').strip(),
            'ReconciledCertPath':(cert.get('CertPath') or '').strip(),
            'RecommendedAction':action,
        })
        output.append(row)

    out=Path(a.out_dir); out.mkdir(parents=True,exist_ok=True)
    fields=list(output[0].keys())
    with open(out/'Camera-Lab-Reconciliation.csv','w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(output)
    with open(out/'Camera-Lab-Reconciliation.json','w',encoding='utf-8') as f:
        json.dump(output,f,indent=2)

    summary={
        'records':len(output),
        'eligible_no_cert':sum((r.get('LookupStatus') or '').upper()=='NO_CERT' for r in output),
        'reconciled_cert_found':sum(r['ReconciliationStatus']=='RECONCILED_CERT_FOUND' for r in output),
        'still_no_cert':sum(r['ReconciliationStatus']=='STILL_NO_CERT' for r in output),
        'review':sum(r['ReconciliationStatus']=='REVIEW' for r in output),
        'not_eligible':sum(r['ReconciliationStatus']=='NOT_ELIGIBLE' for r in output),
        'match_policy':'unique exact normalized serial only',
        'automatic_destruction_history_mutation':False,
    }
    with open(out/'Camera-Lab-Reconciliation-Summary.json','w',encoding='utf-8') as f:
        json.dump(summary,f,indent=2)
    print(json.dumps(summary,indent=2))


if __name__=='__main__':
    main()
