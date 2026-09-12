import argparse,csv,hashlib,json
from pathlib import Path

RECORD_VERSION='1'
LOOKUP_STATES={'NOT_CHECKED','NO_CERT','CERT_FOUND','REVIEW'}
DS_BINS={f'DS-{i:02d}' for i in range(1,13)}


def read_csv(path):
    if not path:
        return []
    with open(path,encoding='utf-8-sig',newline='') as f:
        return list(csv.DictReader(f))


def truthy(value):
    return str(value or '').strip().lower() in {'1','true','yes','y'}


def record_id(image,serial):
    raw=f'{image}\n{serial}'.encode('utf-8')
    return 'CL-'+hashlib.sha256(raw).hexdigest()[:20].upper()


def main():
    ap=argparse.ArgumentParser(description='Build persistence-ready Camera Lab scan records from validated operational records without inventing capture or certificate data.')
    ap.add_argument('--records',required=True,help='Camera-Lab-Operational-Records.csv')
    ap.add_argument('--metadata',help='Optional CSV keyed by Image with SourcePath, CapturedAt, ManualCorrectionApplied, ManualCorrectionNote')
    ap.add_argument('--out-dir',required=True)
    ap.add_argument('--expected-count',type=int)
    a=ap.parse_args()

    rows=read_csv(a.records)
    if not rows:
        raise SystemExit('Operational records file is empty')
    if a.expected_count is not None and len(rows)!=a.expected_count:
        raise SystemExit(f'Expected {a.expected_count} operational records, found {len(rows)}')

    metadata={}
    for row in read_csv(a.metadata):
        image=(row.get('Image') or '').strip()
        if not image:
            raise SystemExit('Metadata row missing Image')
        if image in metadata:
            raise SystemExit(f'Duplicate metadata row for {image}')
        metadata[image]=row

    output=[]
    seen_ids=set()
    for src in rows:
        image=(src.get('Image') or '').strip()
        serial=(src.get('Serial') or '').strip()
        if not image:
            raise SystemExit('Operational record missing Image')
        lookup=(src.get('LookupStatus') or '').strip().upper()
        if lookup not in LOOKUP_STATES:
            raise SystemExit(f'Invalid LookupStatus {lookup!r} for {image}')

        cert_id=(src.get('CertId') or '').strip()
        cert_path=(src.get('CertPath') or '').strip()
        match_method=(src.get('CertMatchMethod') or '').strip()
        bin_id=(src.get('PendingDestructionBin') or '').strip().upper()
        destruction=(src.get('DestructionStatus') or '').strip().upper()

        if lookup=='CERT_FOUND':
            if match_method!='EXACT_NORMALIZED_SERIAL':
                raise SystemExit(f'CERT_FOUND record {image} lacks exact-normalized-serial match provenance')
            if not (cert_id or cert_path):
                raise SystemExit(f'CERT_FOUND record {image} lacks explicit certificate metadata')
        elif cert_id or cert_path or match_method:
            raise SystemExit(f'Non-CERT_FOUND record {image} contains certificate match metadata')

        if bin_id:
            if bin_id not in DS_BINS:
                raise SystemExit(f'Invalid destruction bin {bin_id!r} for {image}')
            if lookup!='NO_CERT':
                raise SystemExit(f'Destruction assignment rejected for {image}: lookup status is {lookup}')
            if destruction!='PENDING_DESTRUCTION':
                raise SystemExit(f'Destruction assignment for {image} must retain PENDING_DESTRUCTION status')
        elif destruction:
            raise SystemExit(f'Destruction status present without DS bin for {image}')

        meta=metadata.get(image,{})
        rid=record_id(image,serial)
        if rid in seen_ids:
            raise SystemExit(f'Duplicate stable scan record identity for {image} / {serial}')
        seen_ids.add(rid)

        needs_review=(lookup=='REVIEW' or (src.get('SerialStatus') or '').strip().upper()=='REVIEW' or (src.get('ModelStatus') or '').strip().upper()=='REVIEW' or (src.get('CapacityStatus') or '').strip().upper()=='REVIEW')
        row={
            'RecordVersion':RECORD_VERSION,
            'RecordId':rid,
            'Image':image,
            'SourcePath':(meta.get('SourcePath') or '').strip(),
            'CapturedAt':(meta.get('CapturedAt') or '').strip(),
            'Manufacturer':(src.get('Manufacturer') or '').strip(),
            'Serial':serial,
            'Model':(src.get('Model') or '').strip(),
            'Capacity':(src.get('Capacity') or '').strip(),
            'ManufacturerEvidence':(src.get('ManufacturerEvidence') or '').strip(),
            'SerialEvidence':(src.get('SerialEvidence') or '').strip(),
            'ModelEvidence':(src.get('ModelEvidence') or '').strip(),
            'CapacityEvidence':(src.get('CapacityEvidence') or '').strip(),
            'SerialStatus':(src.get('SerialStatus') or '').strip(),
            'ModelStatus':(src.get('ModelStatus') or '').strip(),
            'CapacityStatus':(src.get('CapacityStatus') or '').strip(),
            'LookupStatus':lookup,
            'CertMatchMethod':match_method,
            'CertMatchCount':(src.get('CertMatchCount') or '').strip(),
            'CertId':cert_id,
            'CertPath':cert_path,
            'PendingDestructionBin':bin_id,
            'DestructionStatus':destruction,
            'NeedsReview':'true' if needs_review else 'false',
            'ManualCorrectionApplied':'true' if truthy(meta.get('ManualCorrectionApplied')) else 'false',
            'ManualCorrectionNote':(meta.get('ManualCorrectionNote') or '').strip(),
        }
        output.append(row)

    out=Path(a.out_dir); out.mkdir(parents=True,exist_ok=True)
    fields=list(output[0].keys())
    with open(out/'Camera-Lab-Scan-Records.csv','w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(output)
    with open(out/'Camera-Lab-Scan-Records.json','w',encoding='utf-8') as f:
        json.dump(output,f,indent=2)
    summary={
        'record_version':RECORD_VERSION,
        'records':len(output),
        'needs_review':sum(r['NeedsReview']=='true' for r in output),
        'manual_corrections_applied':sum(r['ManualCorrectionApplied']=='true' for r in output),
        'cert_found':sum(r['LookupStatus']=='CERT_FOUND' for r in output),
        'no_cert':sum(r['LookupStatus']=='NO_CERT' for r in output),
        'pending_destruction':sum(bool(r['PendingDestructionBin']) for r in output),
        'capture_metadata_invented':False,
        'certificate_metadata_invented':False,
        'stable_record_id_basis':'sha256(Image + newline + Serial), truncated to 20 hex chars',
    }
    with open(out/'Camera-Lab-Scan-Records-Summary.json','w',encoding='utf-8') as f:
        json.dump(summary,f,indent=2)
    print(json.dumps(summary,indent=2))


if __name__=='__main__':
    main()
