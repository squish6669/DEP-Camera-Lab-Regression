import argparse,csv,re
from collections import defaultdict
from pathlib import Path
from PIL import Image,ImageOps,ImageEnhance,ImageFilter

ANCHOR_RE=re.compile(r'(?i)\b(?:CAPACITY|CAP|SIZE|MODEL|MDL|MODE[1ILU])\b')
PRODUCT_LINE_RE=re.compile(r'(?i)\bX110\b')
FAMILY_RE=re.compile(r'(?i)(?:MZV|MZ7|SSDPE|KXG|KSG|SDBQ|WD\d|SD6|LJT|LCH|ST\d|HTS|MHV|MTFD|HFM|CT\d)')


def box(coords):
    pts=[]
    for pair in (coords or '').split('|'):
        pair=pair.strip()
        if not pair: continue
        try:
            x,y=pair.split(',')[:2]; pts.append((float(x),float(y)))
        except Exception:
            pass
    if not pts: return None
    xs=[p[0] for p in pts]; ys=[p[1] for p in pts]
    return min(xs),min(ys),max(xs),max(ys)


def score_block(row):
    t=row.get('Text') or ''
    b=box(row.get('Coordinates'))
    if not b: return None
    if re.search(r'(?i)\b(?:CAPACITY|CAP|SIZE)\b',t): return (5,b,t)
    if PRODUCT_LINE_RE.search(t): return (4,b,t)
    if ANCHOR_RE.search(t): return (3,b,t)
    if FAMILY_RE.search(t): return (2,b,t)
    return None


def enhance(crop):
    crop=crop.convert('L')
    crop=ImageOps.autocontrast(crop,cutoff=0.5)
    crop=ImageEnhance.Contrast(crop).enhance(1.35)
    crop=crop.filter(ImageFilter.SHARPEN)
    if crop.width<1800:
        scale=min(2.5,1800/max(1,crop.width))
        crop=crop.resize((int(crop.width*scale),int(crop.height*scale)),Image.Resampling.LANCZOS)
    return crop


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

    # Iterate physical images rather than only files with OCR detections. This lets a
    # geometry-only fallback reread labels whose full-image OCR produced no useful anchor.
    image_files=[p for p in image_dir.iterdir() if p.is_file() and p.suffix.lower() in ('.jpg','.jpeg','.png','.bmp','.tif','.tiff')]
    rows=[]
    for src in image_files:
        fn=src.name; blocks=det.get(fn,[])
        scored=[s for b in blocks if (s:=score_block(b))]
        with Image.open(src) as im:
            w,h=im.size
            if scored:
                scored.sort(key=lambda x:x[0],reverse=True)
                tier=scored[0][0]
                chosen=[s for s in scored if s[0]==tier]
                x1=min(s[1][0] for s in chosen); y1=min(s[1][1] for s in chosen)
                x2=max(s[1][2] for s in chosen); y2=max(s[1][3] for s in chosen)
                bh=max(12,y2-y1)
                left=max(0,int(x1-max(100,w*0.07)))
                right=min(w,int(max(x2+max(200,w*0.20),x1+w*0.68)))
                if tier<=2:
                    top_pad=max(180,bh*6.5); bottom_pad=max(100,bh*3.5)
                else:
                    top_pad=max(70,bh*2.5); bottom_pad=max(80,bh*3.0)
                top=max(0,int(y1-top_pad)); bottom=min(h,int(y2+bottom_pad))
                trigger='capacity-anchor' if tier==5 else ('product-line' if tier==4 else ('anchor' if tier==3 else 'family'))
                evidence=' | '.join(s[2] for s in chosen[:3])
            else:
                # Deterministic ground-truth-free fallback: reread a broad center label region.
                # It is evaluation-safe because targeted capacity results may only fill an
                # otherwise empty full-image result; they can never override a baseline pick.
                left=int(w*0.08); right=int(w*0.92)
                top=int(h*0.10); bottom=int(h*0.90)
                trigger='geometry-fallback'; evidence='no OCR capacity/model anchor'
            if right<=left or bottom<=top: continue
            crop=enhance(im.crop((left,top,right,bottom)))
            crop.save(out/fn,quality=95)
        rows.append((fn,trigger,left,top,right,bottom,evidence))

    with open(out/'Targeted-Crops.csv','w',encoding='utf-8-sig',newline='') as f:
        w=csv.writer(f); w.writerow(['FileName','Trigger','Left','Top','Right','Bottom','Evidence']); w.writerows(rows)
    print(f'Created {len(rows)} capacity crops in {out}')

if __name__=='__main__': main()
