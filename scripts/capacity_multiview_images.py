import argparse,csv
from pathlib import Path
from PIL import Image,ImageEnhance,ImageFilter,ImageOps

IMAGE_EXTS={'.jpg','.jpeg','.png','.bmp','.tif','.tiff'}


def save_jpeg(img,path):
    img.convert('RGB').save(path,'JPEG',quality=95,optimize=True)


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--images',required=True)
    ap.add_argument('--out-dir',required=True)
    ap.add_argument('--expected-count',type=int,default=123)
    a=ap.parse_args()

    root=Path(a.images)
    out=Path(a.out_dir)
    out.mkdir(parents=True,exist_ok=True)
    images=sorted(p for p in root.rglob('*') if p.is_file() and p.suffix.lower() in IMAGE_EXTS)
    if len(images)!=a.expected_count:
        raise SystemExit(f'Expected exactly {a.expected_count} physical source images; found {len(images)}')
    names=[p.name.lower() for p in images]
    if len(set(names))!=len(names):
        raise SystemExit('Duplicate physical source image filenames are not allowed')

    rows=[]
    for src in images:
        with Image.open(src) as im:
            base=ImageOps.exif_transpose(im).convert('RGB')
            gray=ImageOps.grayscale(base)

            # View 1: conservative global contrast normalization. This changes only
            # presentation of source pixels; it does not introduce text or metadata.
            contrast=ImageOps.autocontrast(gray,cutoff=0.5)
            name1=f'{src.stem}__contrast.jpg'
            save_jpeg(contrast,out/name1)
            rows.append({'SourceImage':src.name,'ViewImage':name1,'Transform':'grayscale-autocontrast'})

            # View 2: same normalized pixels with a bounded unsharp mask. This is
            # intended to recover faint printed capacity glyphs without geometrically
            # changing character identity.
            sharp=contrast.filter(ImageFilter.UnsharpMask(radius=1.6,percent=160,threshold=3))
            sharp=ImageEnhance.Contrast(sharp).enhance(1.08)
            name2=f'{src.stem}__sharp.jpg'
            save_jpeg(sharp,out/name2)
            rows.append({'SourceImage':src.name,'ViewImage':name2,'Transform':'autocontrast-unsharp'})

    expected=a.expected_count*2
    if len(rows)!=expected:
        raise SystemExit(f'Expected {expected} derived views; created {len(rows)}')
    with open(out/'Capacity-Multiview-Map.csv','w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=['SourceImage','ViewImage','Transform'])
        w.writeheader(); w.writerows(rows)
    print(f'Created {len(rows)} deterministic capacity views from {len(images)} physical images')


if __name__=='__main__':
    main()
