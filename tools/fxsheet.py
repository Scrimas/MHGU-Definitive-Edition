"""fxsheet.py : contact sheet of one effect list (EFL): its textures and the colours its files carry, 4U beside GU.

  fxsheet.py ARC EFL_PATH [--4u ARC4U EFL_PATH4U] [--out PNG]
      ARC = an arc file or a GU RomFS path (/nativeNX/...), EFL_PATH as the arc stores it (effect\\efl\\em\\em049\\em049_012);
      writes dump/fxsheet/<EFL name>.png (with --4u: <name>_vs_4u_<4U name>.png) and prints the same facts

One column per EFL (the --4u one first), from the file bytes only:
  header      EFL version, entries, tail records
  colour      the header +0x2c block (efl4u2gu.efl_colour_block). Its 4U reading (efl4u2gu M19A03_AREA_SOIL comment):
              word 0 bit 4 = colour on, +0xc byte 2 == 0 = the area colour, else the code colour (0xc48378); the block
              holds no RGB itself. A GU file's block is printed raw.
  units       every unit block (unit type, first entry naming it): colour words +0x48 / +0x4c (bytes R, G, B, A, as
              efl4u2gu area_multiply reads them; not for type 9, whose colour moved), colour mode +0x18 bits 0-3, 4U
              Intensity +0x18 bits 12-15 (x2 / x4 RGB in 4U, gone in GU), and the colour curve keys (prop 0)
  PEL         records of the arc's PELs naming this EFL (GU arcs): RGBA +0x60 drawn with its selectors: +0x70 on
              (0x327cb8 recolours only at 1), +0x56 / +0x73 (a table colour instead of +0x60), mode +0x71 (0 RGBA lerp,
              1 replace, 2 multiply, 3 RGB lerp), factor f32 +0x68
  textures    every TEX the EFL names (efl4u2gu.efl_paths) and those of the MRL of every model it names, decoded
              (tex.decode, mip 0): RGB and alpha side by side, path, size, format, mips. 4U files missing from the arc
              are looked up in the 4U core arcs (efl4u2gu.sources); GU files only in the arc given.
Swatches are drawn over a checkerboard (alpha shows). Not drawn: EAN UV animation, curve interpolation, the
stage's area colour, what a GU table colour resolves to.
"""
import os, struct, sys
import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import paths
import arcdiff, efl4u2gu, mrl, tex
from efl4u2gu import T

OUT = os.path.join(paths.DUMP, 'fxsheet')
COL_W, THUMB, SW = 720, 160, 18
FMT_4U = {0x0B: 'ETC1', 0x0C: 'ETC1A4'}
FONT = ImageFont.load_default(size=12)
LINE = 15


def colour_curves(blk):
    """[(frame, colour, colour)] of a unit's colour curve keys (prop 0; layout of efl4u2gu.intensity_bake)"""
    out, a = [], struct.unpack_from('<I', blk, 0x40)[0] >> 16
    while a and a + 4 <= len(blk):
        h = struct.unpack_from('<I', blk, a)[0]
        if not h & 0xFF or (h >> 8) & 0xFF != 2:
            break
        if h >> 24 == 0:
            out += [struct.unpack_from('<3I', blk, a + 4 + 12 * i) for i in range(h & 0xFF)]
        a += 4 + 12 * (h & 0xFF)
    return out


def rgba(word):
    return struct.pack('<I', word)


def load(arc_spec, efl_path):
    """(entries, EFL bytes, whether the 4U core arcs were added)"""
    ents = {(p, t): d for p, t, d in arcdiff.read_arc(arc_spec)}
    core = os.path.isfile(arc_spec) and struct.unpack_from('<H', open(arc_spec, 'rb').read(6), 4)[0] == 0x13
    if core:
        # 4U common effects (qe*, cm*) sit in the core arcs, not in the monster's arc
        ents = {**efl4u2gu.sources(arc_spec, []), **ents}
    if (efl_path, T['EFL']) not in ents:
        raise SystemExit('%s%s holds no EFL %s' % (arc_spec, ' (or the 4U core arcs)' if core else '', efl_path))
    return ents, ents[(efl_path, T['EFL'])], core


def facts(arc_spec, efl_path):
    """the column's content: [('text', str) | ('swatch', [bytes rgba], str) | ('tex', img, str)]"""
    ents, d, core = load(arc_spec, efl_path)
    p = efl4u2gu.efl_parse(d)
    gu = p['ver'] == efl4u2gu.GU_EFL_VER
    rows = [('text', '%s' % os.path.basename(arc_spec)), ('text', efl_path),
            ('text', 'EFL %#x (%s), %d entries, %d tail records, %d B' % (p['ver'], 'GU' if gu else '4U', p['n'],
                                                                       p['n2'], len(d)))]
    b = efl4u2gu.efl_colour_block(d)
    if not b:
        rows.append(('text', 'colour block: none'))
    else:
        rows.append(('text', 'colour block: %s' % ' '.join('%08x' % w for w in b)))
        if not gu:
            rows.append(('text', '  4U reading: colour %s, %s' % (
                'on' if b[0] & 0x10 else 'off (word 0 bit 4 clear)',
                'code colour (+0xc byte 2 set)' if (b[3] >> 16) & 0xFF else 'area colour (+0xc byte 2 0)')))
    first = {}
    for i, e in enumerate(p['ents']):
        for k, w in enumerate(e):
            if w >> 8:
                first.setdefault((w >> 8) + 0x30, i)
    for o, size, k in p['blocks']:
        if not k or k[0] != 1:
            continue
        blk = d[o:o + size]
        w18 = struct.unpack_from('<I', blk, 0x18)[0]
        head = 'unit @%#x type %d (entry %d) mode %d%s' % (o, k[1], first.get(o, -1), w18 & 0xF,
                                                          '' if gu else ' Intensity %d' % ((w18 >> 12) & 0xF))
        if k[1] == 9:
            rows.append(('text', head + ': Filter, colour words moved (not drawn)'))
            continue
        cw = struct.unpack_from('<2I', blk, 0x48)
        rows.append(('swatch', [rgba(c) for c in cw], head + ': RGBA ' + ' '.join(rgba(c).hex() for c in cw)))
        keys = colour_curves(blk)
        if keys:
            rows.append(('swatch', [rgba(c) for _, a, bb in keys for c in (a, bb)],
                         '  colour curve: %d keys, frames %s' % (len(keys), ' '.join(str(f) for f, _, _ in keys))))
    for (pp, t), pd in sorted(ents.items()):
        if t != T['PEL']:
            continue
        for li, (n, body) in enumerate(efl4u2gu.pel_lists(pd)):
            for rp, _, st in arcdiff.pel_records(body, n):
                if rp != efl_path:
                    continue
                rid, j = struct.unpack_from('<Hh', st, 0x30)
                rows.append(('swatch', [st[0x60:0x64]], '%s L%d id %d joint %d mask %x: +0x60 RGBA %s, +0x70 %d '
                             '+0x56 %d +0x73 %d mode %d factor %.3g' % (
                                 pp.rsplit('\\', 1)[-1], li, rid, j, struct.unpack_from('<I', st, 0x48)[0],
                                 st[0x60:0x64].hex(), st[0x70], st[0x56], st[0x73], st[0x71],
                                 struct.unpack_from('<f', st, 0x68)[0])))
    named = list(dict.fromkeys(efl4u2gu.efl_paths(d)))
    texs = [(q, 'named by the EFL') for q in named if (q, T['TEX']) in ents]
    for q in named:
        if (q, T['MOD']) in ents and (q, T['MRL']) in ents:
            texs += [(tp, 'material of %s' % q.rsplit('\\', 1)[-1]) for _, tp in mrl.read(ents[(q, T['MRL'])])['textures']
                     if tp and (tp, T['TEX']) in ents]
    other = [q for q in named if not any((q, t) in ents for t in (T['TEX'], T['MOD']))]
    for q in [q for q in named if (q, T['EAN']) in ents]:
        rows.append(('text', 'EAN %s' % q))
    for q in [q for q in named if (q, T['MOD']) in ents]:
        rows.append(('text', 'model %s' % q))
    for q in [q for q in other if (q, T['EAN']) not in ents]:
        rows.append(('text', 'not found in %s: %s' % ('the arc or the 4U core arcs' if core else 'the arc', q)))
    seen = set()
    for q, why in texs:
        if q in seen:
            continue
        seen.add(q)
        t = ents[(q, T['TEX'])]
        h = tex.parse(t)
        fmt = tex.FMT_GU.get(h['fmt']) if h['version'] == 0xA0 else FMT_4U.get(h['fmt'])
        rows.append(('tex', tex.decode(t), '%s (%s)' % (q, why)))
        rows.append(('text', '  %dx%d %s mips %d' % (h['width'], h['height'], fmt or 'fmt %#x' % h['fmt'], h['mips'])))
    return rows


def checker(w, h):
    y, x = np.mgrid[0:h, 0:w]
    c = np.where(((x // 6) + (y // 6)) % 2, 72, 40).astype(np.uint8)
    return Image.fromarray(np.stack([c, c, c], -1), 'RGB')


def thumb(img):
    im = Image.fromarray(np.ascontiguousarray(img), 'RGBA')
    s = THUMB / max(im.size)
    im = im.resize((max(1, round(im.width * s)), max(1, round(im.height * s))), Image.NEAREST)
    rgb = im.convert('RGB')
    a = im.getchannel('A').convert('RGB')
    return rgb, a


def render(rows):
    rows = [(r[0], thumb(r[1]), r[2]) if r[0] == 'tex' else r for r in rows]

    def height(r):
        if r[0] == 'tex':
            return r[1][0].height + LINE + 6
        if r[0] == 'swatch':
            n = (len(r[1]) * (SW + 3)) // (COL_W - 12) + 1
            return max(SW + 4, LINE) + (n - 1) * (SW + 3) + LINE
        return LINE
    im = Image.new('RGB', (COL_W, sum(height(r) for r in rows) + 12), (24, 24, 24))
    dr = ImageDraw.Draw(im)
    y = 6
    for r in rows:
        if r[0] == 'text':
            dr.text((6, y), r[1], fill=(230, 230, 230), font=FONT)
        elif r[0] == 'swatch':
            dr.text((6, y), r[2], fill=(230, 230, 230), font=FONT)
            x, yy = 6, y + LINE
            for c in r[1]:
                if x + SW > COL_W - 6:
                    x, yy = 6, yy + SW + 3
                cell = checker(SW, SW).convert('RGBA')
                cell.alpha_composite(Image.new('RGBA', (SW, SW), tuple(c)))
                im.paste(cell.convert('RGB'), (x, yy))
                dr.rectangle((x - 1, yy - 1, x + SW, yy + SW), outline=(160, 160, 160))
                x += SW + 3
        else:
            rgb, a = r[1]
            im.paste(rgb, (6, y))
            im.paste(a, (6 + rgb.width + 8, y))
            dr.text((6, y + rgb.height + 2), r[2], fill=(230, 230, 230), font=FONT)
        y += height(r)
    return im


def main():
    args = sys.argv[1:]
    out = None
    if '--out' in args:
        i = args.index('--out')
        out = args[i + 1]
        del args[i:i + 2]
    other = None
    if '--4u' in args:
        i = args.index('--4u')
        other = args[i + 1:i + 3]
        del args[i:i + 3]
        if len(other) != 2:
            raise SystemExit(__doc__)
    if len(args) != 2:
        raise SystemExit(__doc__)
    cols = ([facts(*other)] if other else []) + [facts(*args)]
    for rows in cols:
        for r in rows:
            print(r[1] if r[0] == 'text' else r[-1])
        print()
    imgs = [render(rows) for rows in cols]
    sheet = Image.new('RGB', (sum(i.width for i in imgs) + 4 * (len(imgs) - 1), max(i.height for i in imgs)), (0, 0, 0))
    x = 0
    for i in imgs:
        sheet.paste(i, (x, 0))
        x += i.width + 4
    name = args[1].rsplit('\\', 1)[-1] + ('_vs_4u_' + other[1].rsplit('\\', 1)[-1] if other else '')
    out = out or os.path.join(OUT, name + '.png')
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    sheet.save(out)
    print('written', out)


if __name__ == '__main__':
    main()
