import argparse,csv,json
from pathlib import Path

CONTRACT_VERSION='1.0'
REQUIRED_COLUMNS=[
    'Image','Manufacturer','ManufacturerEvidence','Serial','SerialScore','SerialStatus',
    'SerialEvidence','SerialTopCandidates','Model','ModelStatus','ModelEvidence','Capacity',
    'CapacityGB','CapacityConfidence','CapacityStatus','CapacityEvidence'
]
ALLOWED_SERIAL_STATUS={'FOUND','REVIEW'}
ALLOWED_MODEL_STATUS={'FOUND','REVIEW'}
ALLOWED_CAPACITY_STATUS={'READY','CONFIRM','REVIEW'}


def fail(msg):
    raise SystemExit(msg)


def main():
    ap=argparse.ArgumentParser(description='Validate the stable Camera Lab production inference v1 contract.')
    ap.add_argument('--inference',required=True)
    ap.add_argument('--summary',required=True)
    ap.add_argument('--expected-images',type=int,default=123)
    ap.add_argument('--out-dir',required=True)
    a=ap.parse_args()

    with open(a.inference,encoding='utf-8-sig',newline='') as f:
        reader=csv.DictReader(f)
        columns=reader.fieldnames or []
        rows=list(reader)

    if columns != REQUIRED_COLUMNS:
        fail(f'Inference contract columns changed. Expected {REQUIRED_COLUMNS}; got {columns}')
    if len(rows) != a.expected_images:
        fail(f'Inference contract requires {a.expected_images} rows; got {len(rows)}')

    seen=set()
    for i,row in enumerate(rows,2):
        image=(row.get('Image') or '').strip()
        if not image:
            fail(f'Row {i}: Image is required')
        key=image.lower()
        if key in seen:
            fail(f'Row {i}: duplicate Image {image!r}')
        seen.add(key)

        if row['SerialStatus'] not in ALLOWED_SERIAL_STATUS:
            fail(f'Row {i}: invalid SerialStatus {row["SerialStatus"]!r}')
        if row['ModelStatus'] not in ALLOWED_MODEL_STATUS:
            fail(f'Row {i}: invalid ModelStatus {row["ModelStatus"]!r}')
        if row['CapacityStatus'] not in ALLOWED_CAPACITY_STATUS:
            fail(f'Row {i}: invalid CapacityStatus {row["CapacityStatus"]!r}')

        serial=(row.get('Serial') or '').strip()
        model=(row.get('Model') or '').strip()
        capacity=(row.get('Capacity') or '').strip()
        if (row['SerialStatus']=='FOUND') != bool(serial):
            fail(f'Row {i}: SerialStatus does not agree with Serial presence')
        if (row['ModelStatus']=='FOUND') != bool(model):
            fail(f'Row {i}: ModelStatus does not agree with Model presence')
        if not capacity and row['CapacityStatus']!='REVIEW':
            fail(f'Row {i}: missing Capacity must be REVIEW')

    with open(a.summary,encoding='utf-8') as f:
        summary=json.load(f)
    if summary.get('images') != a.expected_images:
        fail(f'Summary image count changed: {summary.get("images")}')
    if summary.get('ground_truth_consumed') is not False:
        fail('Production inference contract forbids ground-truth consumption')

    out=Path(a.out_dir); out.mkdir(parents=True,exist_ok=True)
    report={
        'contract':'DEP Camera Lab Production Inference',
        'contract_version':CONTRACT_VERSION,
        'rows':len(rows),
        'columns':REQUIRED_COLUMNS,
        'ground_truth_consumed':False,
        'status':'PASS'
    }
    (out/'Camera-Lab-Inference-Contract-Validation.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2))


if __name__=='__main__':
    main()
