import argparse,csv,re
from collections import defaultdict
from pathlib import Path
from PIL import Image,ImageOps,ImageEnhance,ImageFilter

ANCHOR_RE=re.compile(r'(?i)\b(?:MODEL|MDL|MODE[1ILU])\b')
FAMILY_RE=re.compile(r'(?i)(?:MZV|MZ7|SSDPE|KXG|KSG|SDBQ|WD\d|SD6|LJT|LCH|ST\d|HTS|MHV|MTFD|HFM|CT\d)')


def box(coords):
    pts=[]
    for pair in (coords or '').split('|'):
        pair=pair.strip()
        if not pair: continue
        try:
            x,y=pair.split(',')[:2]; pts.append((float(x),float(y)))
        except Exception: pass
    if not pts: return None
    xs=[p[0] for p in pts]; ys=[p[1] for p in pts]
    return min(xs),min(ys),max(xs),max(ys)


def score_block(row):
    t=row.get('Text') or ''
    b=box(row.get('Coordinates'))
    if not b: return None
    if ANCHOR_RE.search(t): return (3,b,t)
    if FAMILY_RE.search(t): return (2,b,t)
    return None


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--images',required=True)
    ap.add_argument('--detections',required=True)
    ap.add_argument('--out-dir',required=True)
    a=ap.parse_args()
    image_dir=Path(a.images); out=Path(a.out_dir); out.mkdir(parents=True,exist_ok=True)
    det=defaultdict(list)
    with open(a.detections,encoding='utf-8-sig',newline='') as f:
        for r in csv.DictReader(f): det[r['FileName']].append(r)

    rows=[]
    for fn,blocks in det.items():
        src=image_dir/fn
        if not src.exists(): continue
        scored=[s for b in blocks if (s:=score_block(b))]
        if not scored: continue
        scored.sort(key=lambda x:x[0],reverse=True)
        tier=scored[0][0]
        chosen=[s for s in scored if s[0]==tier]
        x1=min(s[1][0] for s in chosen); y1=min(s[1][1] for s in chosen)
        x2=max(s[1][2] for s in chosen); y2=max(s[1][3] for s in chosen)
        with Image.open(src) as im:
            w,h=im.size
            bh=max(12,y2-y1)
            # Keep the model line plus neighboring text to the right/left. This is deliberately
            # much tighter vertically than a full-label pass so character pixels get more OCR budget.
            left=max(0,int(x1-max(80,w*0.05)))
            right=min(w,int(max(x2+max(160,w*0.18), x1+w*0.62)))
            top=max(0,int(y1-max(45,bh*2.0)))
            bottom=min(h,int(y2+max(55,bh*2.5)))
            crop=im.crop((left,top,right,bottom)).convert('L')
            crop=ImageOps.autocontrast(crop,cutoff=0.5)
            crop=ImageEnhance.Contrast(crop).enhance(1.35)
            crop=crop.filter(ImageFilter.SHARPEN)
            # Upscale small label text before RapidOCR's own resize.
            if crop.width<1800:
                scale=min(2.5,1800/max(1,crop.width))
                crop=crop.resize((int(crop.width*scale),int(crop.height*scale)),Image.Resampling.LANCZOS)
            crop.save(out/fn,quality=95)
        rows.append((fn,'anchor' if tier==3 else 'family',left,top,right,bottom,' | '.join(s[2] for s in chosen[:3])))

    with open(out/'Targeted-Crops.csv','w',encoding='utf-8-sig',newline='') as f:
        w=csv.writer(f); w.writerow(['FileName','Trigger','Left','Top','Right','Bottom','Evidence']); w.writerows(rows)
    print(f'Created {len(rows)} targeted model crops in {out}')

if __name__=='__main__': main()
