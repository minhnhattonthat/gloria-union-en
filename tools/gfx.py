"""gfx.py: English redraws of Japanese text textures (docs/re/graphics.md survey rows).

    python -X utf8 tools/gfx.py gen [NAME ...]    # regenerate gfx/NAME.png from the original files + gfx/text.tsv
    python -X utf8 tools/gfx.py orig NAME ...     # write the original image to work/gfx/orig/NAME.png (to compare)

One ASSETS entry per texture: CPK file id, kind (ptx = one texture at the offset, ptg = a PTG@ sprite composite),
the rect the redraw may change, and a draw function. gen quantizes each redraw to the texture's own palette, so the
PNG holds only colours the build can write; build.py calls apply() to write every PNG into its CPK file, keeping sizes
and offsets. tests/test_gfx.py checks every PNG changes pixels only inside its rect and writes back exactly.
Translations of the pictures are in gfx/text.tsv (name, Japanese, English); glossary.md applies.
"""
import struct
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import ptx  # noqa: E402

FILES = ROOT / "work" / "re" / "files"
GFX = ROOT / "gfx"
FONTS = ROOT / "fonts"


def text_tsv():
    rows = [ln.split("\t") for ln in (GFX / "text.tsv").read_text("utf8").splitlines()[1:] if ln.strip()]
    return {r[0]: r[2].replace("\\n", "\n") for r in rows}


def font(name, size):
    return ImageFont.truetype(str(FONTS / name), size)


# --- texture access -------------------------------------------------------------------------------------------

def bands(b, a):
    """stack kind: (first row, PTX header) of each texture, stacked top to bottom."""
    out, y = [], 0
    for o in a["off"]:
        t = ptx.parse(b, o)
        out.append((y, t))
        y += t["h"]
    return out


def palette(b, a):
    """The palette the redraw may use (n x 4 ints)."""
    if a["kind"] == "ptx":
        t = ptx.parse(b, a["off"])
        return np.frombuffer(bytes(b), np.uint8, t["n"] * 4, t["po"]).reshape(-1, 4).astype(int)
    base, pieces, _ = ptx.ptg_parts(b, a["off"])
    pals = {bytes(b[base + t["po"]:base + t["po"] + t["n"] * 4]) for t in pieces}
    assert len(pals) == 1, "PTG pieces with different palettes: quantize per piece first"
    return np.frombuffer(pals.pop(), np.uint8).reshape(-1, 4).astype(int)


def read(b, a):
    if a["kind"] == "stack":
        return np.vstack([ptx.decode(bytes(b), t) for _, t in bands(b, a)])
    return ptx.decode(bytes(b), ptx.parse(b, a["off"])) if a["kind"] == "ptx" else ptx.ptg(bytes(b), a["off"])


def fit(b, a, img):
    """Quantize img to the palette(s) it will be written with (stack: each texture's own)."""
    if a["kind"] != "stack":
        return quantize(img, palette(b, a))
    img = np.asarray(img)
    return np.vstack([quantize(img[y:y + t["h"]], np.frombuffer(bytes(b), np.uint8, t["n"] * 4, t["po"])
                               .reshape(-1, 4).astype(int)) for y, t in bands(b, a)])


def write(b, a, img):
    """Write the RGBA array img (palette colours only) into bytearray b; fail if it can't be shown exactly."""
    if a["kind"] == "stack":
        for y, t in bands(b, a):
            out = ptx.encode(b, t, img[y:y + t["h"]])
            b[t["do"]:t["do"] + len(out)] = out
    elif a["kind"] == "ptx":
        t = ptx.parse(b, a["off"])
        out = ptx.encode(b, t, img)
        b[t["do"]:t["do"] + len(out)] = out
    else:
        base, pieces, sprites = ptx.ptg_parts(b, a["off"])
        size = struct.unpack_from("<I", b, a["off"] + 12)[0]
        block = bytearray(b[base:base + size] if size else b[base:])
        atlas = [ptx.decode(bytes(block), t).copy() for t in pieces]
        for k, u0, v0, u1, v1, x0, y0, x1, y1 in sprites:
            atlas[k][v0:v1, u0:u1] = img[y0:y1, x0:x1]
        for t, p in zip(pieces, atlas):
            out = ptx.encode(block, t, p)
            block[t["do"]:t["do"] + len(out)] = out
        b[base:base + len(block)] = block
    got = read(b, a)
    if not np.array_equal(got[:img.shape[0], :img.shape[1]], img):
        bad = np.argwhere((got[:img.shape[0], :img.shape[1]] != img).any(2))
        raise ValueError(f"{a['name']}: {len(bad)} pixels can't be drawn (outside every sprite?), first {bad[0][::-1]}")


def files(a):
    """Every file an asset is written to (a tuple: copies with the same pixels at the same offset)."""
    return a["file"] if isinstance(a["file"], tuple) else (a["file"],)


def original(name):
    a = ASSETS[name]
    return read((FILES / f"{files(a)[0]:05d}.bin").read_bytes(), a)


def apply(repl):
    """build.py: write every gfx/*.png into its file; repl is {file id: bytes} and is updated in place."""
    for name, a in ASSETS.items():
        png = GFX / f"{name}.png"
        if not png.exists():
            continue
        for i in files(a):
            b = bytearray(repl.get(i) or (FILES / f"{i:05d}.bin").read_bytes())
            write(b, a, np.array(Image.open(png).convert("RGBA")))
            repl[i] = bytes(b)
    return repl


# --- drawing helpers ------------------------------------------------------------------------------------------

def quantize(img, pal):
    """Nearest palette colour (RGBA distance) for every pixel."""
    a = np.asarray(img, dtype=int)
    out = np.empty(a.shape, np.uint8)
    for y in range(a.shape[0]):   # row by row: h x w x n distances would be large for 480 x 272 x 256
        out[y] = pal[np.abs(a[y][:, None, :] - pal[None]).sum(2).argmin(1)]
    return out


def inpaint(a, mask, iters=200):
    """Fill the masked pixels of RGBA array a from their neighbours (diffusion)."""
    a = a.astype(float)
    known = ~mask
    cur = a.copy()
    cur[mask] = 0
    for _ in range(iters):
        if known.all():
            break
        wsum = np.zeros(mask.shape)
        acc = np.zeros(a.shape)
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            k = np.roll(known, (dy, dx), (0, 1))
            acc += np.roll(cur, (dy, dx), (0, 1)) * k[..., None]
            wsum += k
        fill = ~known & (wsum > 0)
        cur[fill] = acc[fill] / wsum[fill][:, None]
        known = known | fill
    return cur.clip(0, 255).astype(np.uint8)


def grow(m, n=1):
    for _ in range(n):
        g = m.copy()
        g[1:] |= m[:-1]; g[:-1] |= m[1:]; g[:, 1:] |= m[:, :-1]; g[:, :-1] |= m[:, 1:]
        m = g
    return m


def layer_text(text, f, fill, stroke=0, stroke_fill=None, xscale=1.0, shear=0.0):
    """Text on a tight transparent layer (stroke included), optionally squeezed and slanted."""
    l, t, r, bt = f.getbbox(text, stroke_width=stroke)
    im = Image.new("RGBA", (r - l + 4, bt - t + 4), (0, 0, 0, 0))
    ImageDraw.Draw(im).text((2 - l, 2 - t), text, font=f, fill=fill, stroke_width=stroke, stroke_fill=stroke_fill)
    if xscale != 1.0:
        im = im.resize((max(1, round(im.width * xscale)), im.height), Image.LANCZOS)
    if shear:
        extra = int(abs(shear) * im.height) + 1
        im = im.transform((im.width + extra, im.height), Image.AFFINE, (1, shear, -extra if shear > 0 else 0, 0, 1, 0),
                          Image.BICUBIC)
    return im


# --- chapter cards (1582-1588) --------------------------------------------------------------------------------

CARD_END = {1: 196, 2: 270, 3: 326, 4: 338, 5: 250, 6: 334, 7: 272}   # x where the Japanese title ends
CARD_BOX2 = {4: 170}   # second boxed character (x of its frame)


def _box_rows(a, x=8):
    w = np.where(a[:72, x, :3].min(1) > 225)[0]
    return w.min(), w.max()


def _boxed(a, x0, y0, y1, letter):
    """The 54 px framed box at x0 with its kanji replaced by a white serif letter."""
    tile = a[y0:y1 + 1, x0:x0 + 54].copy()
    inner = tile[4:-4, 4:-4]
    body = inner[inner[..., :3].min(2) < 200]
    colour = np.array([np.bincount(body[:, c]).argmax() for c in range(4)], np.uint8)
    tile[3:-3, 3:-3] = colour
    im = Image.fromarray(tile)
    lt = layer_text(letter, font("LiberationSerif-Bold.ttf", 46), (255, 255, 255, 255))
    im.alpha_composite(lt, ((im.width - lt.width) // 2, (im.height - lt.height) // 2 + 1))
    return np.array(im)


def draw_card(a, n, text):
    a = a.copy()
    y0, y1 = _box_rows(a)
    end = CARD_END[n]
    # old lettering: black ink and its white outline right of box 1, the whole second box
    reg = a[:66, 62:end + 4]
    m = np.zeros(a.shape[:2], bool)
    dark = reg[..., :3].max(2) < 110
    white = (reg[..., :3].min(2) > 175) & (np.ptp(reg[..., :3], 2) < 50)
    # lettering = black ink inside its white rim: keep art whites and art lines that aren't next to each other
    m[:66, 62:end + 4] = (dark & grow(white, 3)) | (white & grow(dark, 4))
    m = grow(m, 1)
    m[:66, end + 4:] = False
    tiles = [(7, a)]
    if n in CARD_BOX2:
        bx = CARD_BOX2[n]
        tiles.append((bx, a.copy()))
        m[y0:y1 + 1, bx:bx + 54] = True
    a = inpaint(a, m)
    parts = text.split("[")
    f_size, xscale = 38, 0.85
    # parts: '', 'W]ind Meets, ', 'E]arth Fights'
    segs = [(p.split("]", 1)[0], p.split("]", 1)[1]) for p in parts[1:]]
    limit = 400
    while True:
        f = font("LiberationSerif-Bold.ttf", f_size)
        layers = [layer_text(s.rstrip(), f, (0, 0, 0, 255), 3, (255, 255, 255, 255), xscale) for _, s in segs]
        width = 64 + sum(lt.width for lt in layers) + 56 * (len(segs) - 1) + 8 * (len(segs) - 1)
        if width <= limit or f_size <= 22:
            break
        f_size -= 1
    im = Image.fromarray(a)
    x = 7
    for k, ((letter, _), lt) in enumerate(zip(segs, layers)):
        src_x, src = tiles[k]
        im.paste(Image.fromarray(_boxed(src, src_x, y0, y1, letter)), (x, y0))
        x += 54 + 1
        im.alpha_composite(lt, (x, (y0 + y1) // 2 - lt.height // 2 + 3))
        x += lt.width + 8
    return np.array(im)


# --- game over (1758) -----------------------------------------------------------------------------------------

def draw_gameover_title(a, text):
    """ゲームオーバー: black brush lettering, pale lavender rim, blue glow, slanted."""
    h, w = a.shape[:2]
    im = Image.new("RGBA", (w, h), tuple(int(c) for c in a[0, 0]))
    f = font("LiberationSerif-Bold.ttf", 44)
    rim = layer_text(text, f, (235, 234, 254, 255), 3, (235, 234, 254, 255), 1.0, 0.3)
    glow = Image.new("RGBA", rim.size, (0, 0, 0, 0))
    glow.paste(Image.new("RGBA", rim.size, (120, 119, 170, 255)), mask=rim.split()[3].filter(ImageFilter.MaxFilter(5)))
    glow = glow.filter(ImageFilter.GaussianBlur(2))
    ink = layer_text(text, f, (27, 27, 27, 255), 3, (0, 0, 0, 0), 1.0, 0.3)
    body = layer_text(text, f, (27, 27, 27, 255), 0, None, 1.0, 0.3)
    x, y = (w - rim.width) // 2, (h - rim.height) // 2
    im.alpha_composite(glow, (x, y))
    im.alpha_composite(rim, (x, y))
    off = (ink.width - body.width) // 2, (ink.height - body.height) // 2
    im.alpha_composite(body, (x + off[0], y + off[1]))
    return np.array(im)


def draw_gameover_menu(a, retry, title):
    """Row 0-15: two menu sprites, u 0-100 and u 102-254 (split read off the texture's ink gap). Left-aligned: the
    game puts the cursor at a fixed x left of where each Japanese word starts (work/qa/gfx1/game_over/proof.png)."""
    a = a.copy()
    a[:16] = (255, 255, 255, 0)
    im = Image.fromarray(a)
    f = font("LiberationSans-BoldItalic.ttf", 14)
    for text, left in ((retry, 0), (title, 102)):
        sh = layer_text(text, f, (0, 0, 0, 125), 1, (0, 0, 0, 125))
        lt = layer_text(text, f, (255, 255, 255, 255), 1, (1, 1, 1, 253))
        x, y = left, (16 - lt.height) // 2
        im.alpha_composite(sh, (x + 1, y + 1))
        im.alpha_composite(lt, (x, y))
    out = np.array(im)
    out[16:] = a[16:]
    return out


# --- staff credits (1992) ---------------------------------------------------------------------------------------

CRED_W, CRED_END, CRED_PITCH = 194, 193, 14   # ink area, right edge of every line, line pitch


def credit_blocks(a):
    """(top row, lines) of each credit entry: ink runs separated by blank rows; lines are 14 px apart."""
    rows = (a[:, :CRED_W, 3] > 0).any(1)
    out, y = [], 0
    while y < len(rows):
        if rows[y]:
            y0 = y
            while y < len(rows) and rows[y]:
                y += 1
            out.append((y0, max(1, round((y - y0) / CRED_PITCH))))
        y += 1
    return out


def credits_tsv():
    rows = [ln.split("\t") for ln in (GFX / "credits.tsv").read_text("utf8").splitlines()[1:] if ln.strip()]
    return [(r[0], r[1]) for r in rows]


def _credit_line(im, text, f, baseline):
    """White letters with a translucent dark blue rim and a soft shadow, right edge at CRED_END."""
    for dx, fill, stroke, sf in ((1, (0, 0, 0, 70), 1, (0, 0, 0, 70)), (0, (250, 251, 254, 250), 1, (2, 23, 80, 140))):
        lt = layer_text(text, f, fill, stroke, sf)
        xs = min(1.0, (CRED_END - 2) / (lt.width - 4))   # squeeze only a line wider than the scroll
        if xs < 1:
            lt = layer_text(text, f, fill, stroke, sf, xs)
        top = baseline - (2 - f.getbbox(text, stroke_width=stroke)[1] + f.getmetrics()[0])   # layer_text's baseline
        im.alpha_composite(lt, (CRED_END + 2 - lt.width + dx, top + dx))


def draw_credits(a, _t):
    """One continuous scroll (8 pages + a stub); each entry = italic role line over right-aligned names. Lines whose
    English equals the Japanese (CAST, STAFF headers) keep the original pixels."""
    rows = credits_tsv()
    blocks = credit_blocks(a)
    assert sum(n for _, n in blocks) == len(rows), (sum(n for _, n in blocks), len(rows))
    out = a.copy()
    role, name = font("LiberationSans-BoldItalic.ttf", 11), font("LiberationSans-Bold.ttf", 13)
    k = 0
    for y0, n in blocks:
        lines = rows[k:k + n]
        k += n
        if all(jp == en for jp, en in lines):
            continue
        out[y0 - 1:y0 + n * CRED_PITCH + 2, :CRED_W] = (255, 255, 255, 0)
        im = Image.fromarray(out)
        for i, (_, en) in enumerate(lines):
            _credit_line(im, en, role if i == 0 else name, y0 + i * CRED_PITCH + (10 if i == 0 else 11))
        out = np.array(im)
    out[out[..., 3] == 0] = (255, 255, 255, 0)   # fully clear pixels must match the clear palette entry
    return out


# --- stage titles (1850-1905: horizontal +30, vertical +2d90) ----------------------------------------------------

def _plate(lines, f, spacing, shadow):
    """Centred white lines with a black rim and a black drop shadow, on a tight transparent layer."""
    text = "\n".join(lines)
    kw = dict(font=f, spacing=spacing, align="center", stroke_width=1)
    l, t, r, b = (round(v) for v in ImageDraw.Draw(Image.new("RGBA", (1, 1))).multiline_textbbox((0, 0), text, **kw))
    im = Image.new("RGBA", (r - l + 4 + shadow, b - t + 4 + shadow), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.multiline_text((2 - l + shadow, 2 - t + shadow), text, fill=(0, 0, 0, 255), stroke_fill=(0, 0, 0, 255), **kw)
    d.multiline_text((2 - l, 2 - t), text, fill=(255, 255, 255, 255), stroke_fill=(0, 0, 0, 255), **kw)
    return im


def _halves(s):
    """Split at the space nearest the middle."""
    sp = [i for i, c in enumerate(s) if c == " "]
    if not sp:
        return [s]
    i = min(sp, key=lambda i: abs(i - len(s) / 2))
    return [s[:i], s[i + 1:]]


def title_layer(text, w, h, one, two, shadow):
    """The title fitted into w x h: one line at font size `one` (down to 80%) if it needs no more than a 0.8 squeeze,
    else two lines (text's \\n, or split near the middle) at size `two` (down to 70%), squeezed to fit."""
    flat = text.replace("\n", " ")
    tries = [([flat], s, 0.8) for s in range(one, int(one * 0.8) - 1, -1)]
    tries += [(text.split("\n") if "\n" in text else _halves(flat), s, 0.6) for s in range(two, int(two * 0.7) - 1, -1)]
    for lines, size, min_xs in tries:
        im = _plate(lines, font("LiberationSerif-Bold.ttf", size), -size // 6, shadow)
        xs = min(1.0, w / im.width)
        if im.height <= h and xs >= min_xs:
            return im.resize((max(1, round(im.width * xs)), im.height), Image.LANCZOS) if xs < 1 else im
    raise ValueError(f"title doesn't fit {w}x{h}: {text!r}")


def draw_title(a, text, vertical):
    clear = (255, 255, 255, 0)   # in both palettes
    if vertical:   # the strip holds the horizontal title turned 90 degrees anticlockwise (reads bottom to top)
        h, w = a.shape[1] - 2, a.shape[0]
        lt = title_layer(text, w - 4, h, 22, 13, 1)
        im = Image.new("RGBA", (w, a.shape[1]), clear)
        im.alpha_composite(lt, ((w - lt.width) // 2, (a.shape[1] - lt.height) // 2))
        out = np.rot90(np.array(im), 1).copy()
    else:
        w, h = 300, a.shape[0]
        # the talk scene shows rows ~12-58 between the chapter bar and the portraits (JP ink: rows 15-55)
        lt = title_layer(text, w - 6, 48, 34, 24, 2)
        im = Image.new("RGBA", (a.shape[1], h), clear)
        im.alpha_composite(lt, ((w - lt.width) // 2, 35 - lt.height // 2))
        out = np.array(im)
    out[out[..., 3] == 0] = clear
    return out


# --- registry ---------------------------------------------------------------------------------------------------

ASSETS = {}


def asset(name, file, kind, off, rect, draw):
    ASSETS[name] = dict(name=name, file=file, kind=kind, off=off, rect=rect, draw=draw)


for _n in range(1, 8):
    asset(f"card{_n}", 1581 + _n, "ptg", 0x20, (0, 0, 440, 66), lambda a, t, n=_n: draw_card(a, n, t[f"card{n}"]))
asset("gameover", 1758, "ptx", 0x3310, (0, 0, 272, 54), lambda a, t: draw_gameover_title(a, t["gameover"]))
asset("gameover_menu", 1758, "ptx", 0x16b0, (0, 0, 256, 16),
      lambda a, t: draw_gameover_menu(a, t["gameover_retry"], t["gameover_title"]))
for _f, _n in ((1850, 2), (1852, 1), (1853, 1), (1854, 2), (1856, 2), (1858, 2), *((f, 1) for f in range(1860, 1878)),
               (1878, 2), *((f, 1) for f in range(1880, 1888)), (1888, 2), *((f, 1) for f in range(1890, 1906))):
    _ids = tuple(range(_f, _f + _n))
    asset(f"title{_f}", _ids, "ptx", 0x30, (0, 0, 300, 72), lambda a, t, f=_f: draw_title(a, t[f"title{f}"], False))
    asset(f"title{_f}v", _ids, "ptx", 0x2d90, (0, 0, 32, 180), lambda a, t, f=_f: draw_title(a, t[f"title{f}"], True))
asset("credits", 1992, "stack", [0x1640 + 0xE060 * i for i in range(9)], (0, 0, CRED_W, 4159), draw_credits)


def gen(names=None):
    t = text_tsv()
    GFX.mkdir(exist_ok=True)
    for name in names or ASSETS:
        a = ASSETS[name]
        b = (FILES / f"{files(a)[0]:05d}.bin").read_bytes()
        orig = read(b, a)
        for i in files(a)[1:]:
            assert np.array_equal(read((FILES / f"{i:05d}.bin").read_bytes(), a), orig), f"{name}: {i} differs"
        new = fit(b, a, a["draw"](orig, t))
        x, y, w, h = a["rect"]
        keep = np.ones(orig.shape[:2], bool)
        keep[y:y + h, x:x + w] = False
        new[keep] = orig[keep]
        Image.fromarray(new).save(GFX / f"{name}.png")
        print(name, (new != orig).any(2).sum(), "pixels changed")


if __name__ == "__main__":
    cmd, *args = sys.argv[1:] or ["gen"]
    if cmd == "gen":
        gen(args)
    elif cmd == "orig":
        (ROOT / "work" / "gfx" / "orig").mkdir(parents=True, exist_ok=True)
        for name in args:
            Image.fromarray(original(name)).save(ROOT / "work" / "gfx" / "orig" / f"{name}.png")
