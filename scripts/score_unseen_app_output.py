import argparse,csv,json,re
from pathlib import Path

def norm(s): return re.sub(r'[^A-Z0-9]','',(s or '').upper())
def norm_man(s):
    u=norm(s)
    if u in {'HGSTHITACHI','HITACHI','HGST'}: return 'HGSTHITACHI'
    if u in {'WESTERNDIGITAL','WDC'}: return 'WESTERNDIGITAL'
    return u

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--ground-truth',required=True)
    ap.add_argument('--app-output',required=True)
    ap.add_argument('--out-dir',required=True)
    a=ap.parse_args(); out=Path(a.out_dir); out.mkdir(parents=True,exist_ok=True)
    gt={r['Image']:r for r in csv.DictReader(open(a.ground_truth,encoding='utf-8-sig'))}
    app={r['Image']:r for r in csv.DictReader(open(a.app_output,encoding='utf-8-sig'))}
    rows=[]
    for fn,g in gt.items():
        r=app.get(fn,{})
        exp_ser=norm(g.get('ExpectedSerial')); got_ser=norm(r.get('Serial'))
        exp_mod=norm(g.get('ExpectedModel')); got_mod=norm(r.get('Model'))
        exp_man=norm_man(g.get('ExpectedManufacturer')); got_man=norm_man(r.get('Manufacturer'))
        state=(r.get('RecognitionState') or '').upper()
        serr=bool(exp_ser and got_ser==exp_ser); merr=bool(exp_mod and got_mod==exp_mod); manerr=bool(exp_man and got_man==exp_man)
        unsafe=bool(got_ser and exp_ser and got_ser!=exp_ser and state in {'READY','CONFIRM'})
        rows.append({'Image':fn,'ExpectedSerial':exp_ser,'Serial':got_ser,'SerialExact':serr,'ExpectedModel':exp_mod,'Model':got_mod,'ModelExact':merr,'ExpectedManufacturer':exp_man,'Manufacturer':got_man,'ManufacturerExact':manerr,'RecognitionState':state,'UnsafeIncorrectSerial':unsafe,'Error':r.get('Error','')})
    n=len(rows); serial=sum(x['SerialExact'] for x in rows); model=sum(x['ModelExact'] for x in rows); man=sum(x['ManufacturerExact'] for x in rows); unsafe=sum(x['UnsafeIncorrectSerial'] for x in rows); errors=sum(bool((x['Error'] or '').strip()) for x in rows)
    metrics={'rows':n,'serial_exact':serial,'serial_pct':round(100*serial/n,1) if n else 0,'model_exact':model,'model_pct':round(100*model/n,1) if n else 0,'manufacturer_exact':man,'manufacturer_pct':round(100*man/n,1) if n else 0,'unsafe_incorrect_serial':unsafe,'errors':errors}
    with open(out/'Unseen-Score.csv','w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=rows[0].keys());w.writeheader();w.writerows(rows)
    json.dump(metrics,open(out/'Unseen-Score.json','w'),indent=2)
    lines=['# Unseen Camera Lab Score','',f"- Rows: **{n}**",f"- Serial exact: **{serial}/{n} ({metrics['serial_pct']}%)**",f"- Model exact: **{model}/{n} ({metrics['model_pct']}%)**",f"- Manufacturer exact: **{man}/{n} ({metrics['manufacturer_pct']}%)**",f"- Unsafe incorrect serial in READY/CONFIRM: **{unsafe}**",f"- Processing errors: **{errors}**",'','## Misses','','| Image | Serial | Model | Manufacturer | State | Unsafe |','|---|---|---|---|---|---|']
    for x in rows:
        if not (x['SerialExact'] and x['ModelExact'] and x['ManufacturerExact']): lines.append(f"| {x['Image']} | {'OK' if x['SerialExact'] else x['Serial']} | {'OK' if x['ModelExact'] else x['Model']} | {'OK' if x['ManufacturerExact'] else x['Manufacturer']} | {x['RecognitionState']} | {x['UnsafeIncorrectSerial']} |")
    (out/'Unseen-Score.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print('\n'.join(lines[:9]))
    if unsafe: raise SystemExit('Unsafe incorrect serial reached READY/CONFIRM')
if __name__=='__main__': main()
