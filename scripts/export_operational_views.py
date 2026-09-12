import argparse,csv,json
from pathlib import Path


def read_csv(path):
    with open(path,encoding='utf-8-sig',newline='') as f:
        return list(csv.DictReader(f))


def write_csv(path, rows, fields):
    with open(path,'w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore')
        w.writeheader()
        w.writerows(rows)


def main():
    ap=argparse.ArgumentParser(description='Export conservative Camera Lab operational views from established operational records. No matching or status inference occurs here.')
    ap.add_argument('--records',required=True,help='Camera-Lab-Operational-Records.csv')
    ap.add_argument('--out-dir',required=True)
    a=ap.parse_args()

    rows=read_csv(a.records)
    if not rows:
        raise SystemExit('Operational records file is empty')

    allowed={'CERT_FOUND','NO_CERT','REVIEW','NOT_CHECKED'}
    for row in rows:
        status=(row.get('LookupStatus') or '').strip().upper()
        if status not in allowed:
            raise SystemExit(f'Unsupported LookupStatus {status!r}; export refuses to reinterpret unknown states')
        bin_id=(row.get('PendingDestructionBin') or '').strip().upper()
        if bin_id and status!='NO_CERT':
            raise SystemExit(f'Pending-destruction record {row.get("Image","")!r} is not NO_CERT; refusing export')

    cert_found=[r for r in rows if (r.get('LookupStatus') or '').upper()=='CERT_FOUND']
    no_cert=[r for r in rows if (r.get('LookupStatus') or '').upper()=='NO_CERT']
    review=[r for r in rows if (r.get('LookupStatus') or '').upper() in {'REVIEW','NOT_CHECKED'}]
    pending=[r for r in no_cert if (r.get('PendingDestructionBin') or '').strip()]

    out=Path(a.out_dir); out.mkdir(parents=True,exist_ok=True)
    fields=list(rows[0].keys())
    write_csv(out/'Camera-Lab-Cert-Found.csv',cert_found,fields)
    write_csv(out/'Camera-Lab-No-Cert.csv',no_cert,fields)
    write_csv(out/'Camera-Lab-Review.csv',review,fields)
    write_csv(out/'Camera-Lab-Pending-Destruction.csv',pending,fields)

    summary={
        'records':len(rows),
        'cert_found':len(cert_found),
        'no_cert':len(no_cert),
        'review_or_not_checked':len(review),
        'pending_destruction':len(pending),
        'source_of_truth':'Camera-Lab-Operational-Records.csv',
        'status_reinterpretation':False,
        'certificate_matching_performed':False,
        'destruction_assignment_mutation':False,
    }
    with open(out/'Camera-Lab-Operational-Export-Summary.json','w',encoding='utf-8') as f:
        json.dump(summary,f,indent=2)
    print(json.dumps(summary,indent=2))


if __name__=='__main__':
    main()
