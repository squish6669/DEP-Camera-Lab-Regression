import argparse,csv,json,re
from pathlib import Path


PROTECTED_MODEL_MIN_EXACT=65
PROTECTED_CAPACITY_MIN_EXACT=67


def norm(s):
    return re.sub(r'[^A-Z0-9]','',(s or '').upper())


def expected_capacity_gb(s):
    t=(s or '').upper().replace(',','')
    m=re.search(r'(\d+(?:\.\d+)?)\s*(TB|GB|G|T)\b',t)
    if not m:return None
    v=float(m.group(1)); unit=m.group(2)
    gb=int(round(v*1000)) if unit.startswith('T') else int(round(v))
    return {1024:1000,2048:2000,4096:4000}.get(gb,gb)


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--ground-truth',required=True)
    ap.add_argument('--inference',required=True)
    ap.add_argument('--out-dir',required=True)
    ap.add_argument('--serial-min-pct',type=float,default=95.0)
    ap.add_argument('--model-min-exact',type=int,default=PROTECTED_MODEL_MIN_EXACT)
    ap.add_argument('--capacity-min-exact',type=int,default=PROTECTED_CAPACITY_MIN_EXACT)
    a=ap.parse_args()
    # Callers may raise these floors, but must never weaken the validated production baseline.
    model_min_exact=max(a.model_min_exact,PROTECTED_MODEL_MIN_EXACT)
    capacity_min_exact=max(a.capacity_min_exact,PROTECTED_CAPACITY_MIN_EXACT)
    out=Path(a.out_dir);out.mkdir(parents=True,exist_ok=True)
    gt=list(csv.DictReader(open(a.ground_truth,encoding='utf-8-sig')))
    pred={r['Image']:r for r in csv.DictReader(open(a.inference,encoding='utf-8-sig'))}
    verified=[g for g in gt if (g.get('Verified') or '').strip().upper()=='YES']
    if len(verified)!=68: raise SystemExit(f'Expected 68 verified rows; found {len(verified)}')
    serial_n=serial_exact=model_n=model_exact=cap_n=cap_exact=0
    rows=[]
    for g in verified:
        fn=g['Image'];p=pred.get(fn,{})
        exp_serial=norm(g.get('ExpectedSerial')); got_serial=norm(p.get('Serial'))
        exp_model=norm(g.get('ExpectedModel')); got_model=norm(p.get('Model'))
        exp_cap=expected_capacity_gb(g.get('ExpectedCapacity')); got_cap=int(p['CapacityGB']) if str(p.get('CapacityGB','')).strip().isdigit() else None
        if exp_serial:
            serial_n+=1; serial_exact+=int(exp_serial==got_serial)
        if exp_model:
            model_n+=1; model_exact+=int(exp_model==got_model)
        if exp_cap is not None:
            cap_n+=1; cap_exact+=int(exp_cap==got_cap)
        rows.append({'Image':fn,'ExpectedSerial':exp_serial,'Serial':got_serial,'SerialExact':bool(exp_serial and exp_serial==got_serial),'ExpectedModel':exp_model,'Model':got_model,'ModelExact':bool(exp_model and exp_model==got_model),'ExpectedCapacityGB':exp_cap or '','CapacityGB':got_cap or '','CapacityExact':bool(exp_cap is not None and exp_cap==got_cap)})
    serial_pct=round(100*serial_exact/serial_n,1) if serial_n else 0
    metrics={'verified_rows':len(verified),'serial_n':serial_n,'serial_exact':serial_exact,'serial_pct':serial_pct,'model_n':model_n,'model_exact':model_exact,'model_pct':round(100*model_exact/model_n,1) if model_n else 0,'capacity_n':cap_n,'capacity_exact':cap_exact,'capacity_pct':round(100*cap_exact/cap_n,1) if cap_n else 0}
    json.dump(metrics,open(out/'Production-Inference-Validation.json','w'),indent=2)
    with open(out/'Production-Inference-Validation.csv','w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=rows[0].keys());w.writeheader();w.writerows(rows)
    md=['# Production Inference Validation','',f"- Verified rows: **{len(verified)}**",f"- Serial: **{serial_exact}/{serial_n} ({serial_pct}%)**",f"- Model: **{model_exact}/{model_n} ({metrics['model_pct']}%)**",f"- Capacity: **{cap_exact}/{cap_n} ({metrics['capacity_pct']}%)**",'', '> Ground truth is used only by this validation scorer after production inference has completed.']
    (out/'Production-Inference-Validation.md').write_text('\n'.join(md)+'\n',encoding='utf-8')
    print('\n'.join(md))
    if serial_pct < a.serial_min_pct: raise SystemExit(f'Production serial gate failed: {serial_exact}/{serial_n}={serial_pct}% < {a.serial_min_pct}%')
    if model_exact < model_min_exact: raise SystemExit(f'Production model regression: {model_exact}/{model_n} < {model_min_exact}')
    if cap_exact < capacity_min_exact: raise SystemExit(f'Production capacity regression: {cap_exact}/{cap_n} < {capacity_min_exact}')

if __name__=='__main__': main()
