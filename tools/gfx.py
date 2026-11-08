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
    return {r[0]: r[2].replace("\\n", "\n") if len(r) > 2 else "" for r in rows}   # no English: left blank


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


def section(b, a):
    """(section bytes, asset with its offset in them) for an asset inside an FCT section of file b (id 3). The texture
    is found by its PTP entry number, so it is found again after an earlier resize moved the section's entries."""
    from extract import fct
    orig = (FILES / f"{files(a)[0]:05d}.bin").read_bytes()
    n, h = struct.unpack_from("<II", orig, 4)
    start = struct.unpack_from("<I", orig, h + 8 * a["section"])[0]
    old, s = fct(orig, a["section"]), bytearray(fct(bytes(b), a["section"]))
    assert old[:4] == b"PTP\0", f"{a['name']}: section {a['section']} is not a PTP"
    ents = list(struct.unpack_from(f"<{struct.unpack_from('<I', old, 4)[0]}I", old, 0x10))
    i = ents.index(a["off"] - start)
    return s, dict(a, section=None, off=struct.unpack_from("<I", s, 0x10 + 4 * i)[0])


def palette(b, a):
    """The palette the redraw may use (n x 4 ints)."""
    if a["section"] is not None:
        return palette(*section(b, a))
    if a["kind"] == "ptx":
        t = ptx.parse(b, a["off"])
        return np.frombuffer(bytes(b), np.uint8, t["n"] * 4, t["po"]).reshape(-1, 4).astype(int)
    base, pieces, _ = ptx.ptg_parts(b, a["off"])
    pals = {bytes(b[base + t["po"]:base + t["po"] + t["n"] * 4]) for t in pieces}
    assert len(pals) == 1, "PTG pieces with different palettes: quantize per piece first"
    return np.frombuffer(pals.pop(), np.uint8).reshape(-1, 4).astype(int)


def read(b, a):
    if a["section"] is not None:
        return read(*section(b, a))
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
    if a["section"] is not None:   # write into the section, then re-lay the FCT (later sections move, as in insert.cpk)
        from insert import fct_pack
        s, inner = section(b, a)
        write(s, inner, img)
        b[:] = fct_pack(bytes(b), {a["section"]: bytes(s)})
        return
    if a["kind"] == "stack":
        for y, t in bands(b, a):
            out = ptx.encode(b, t, img[y:y + t["h"]])
            b[t["do"]:t["do"] + len(out)] = out
    elif a["kind"] == "ptx":
        t = ptx.parse(b, a["off"])
        out = ptx.encode(b, t, img)
        b[t["do"]:t["do"] + len(out)] = out
    else:
        if a["resize"]:   # the PNG sets the canvas: rebuild the PTG's atlas and sprites for it (the file size changes)
            ptx.ptg_resize(b, a["off"], img.shape[1], img.shape[0])
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
    bad = np.argwhere(~same(read(b, a), img))
    if len(bad):
        raise ValueError(f"{a['name']}: {len(bad)} pixels can't be drawn (outside every sprite?), first {bad[0][::-1]}")


def same(got, img):
    """Pixel mask: got (a decoded texture, maybe padded) shows img; clear pixels match any clear pixel (a packed PTG
    leaves the trimmed parts of each band undrawn)."""
    got = got[:img.shape[0], :img.shape[1]]
    return (got == img).all(2) | ((got[..., 3] == 0) & (img[..., 3] == 0))


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
    clear = pal[pal[:, 3] == 0]
    if len(clear):   # clear stays clear, whatever its RGB (a clear (0,0,0,0) is nearer a dark opaque entry)
        out[a[..., 3] == 0] = clear[0]
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


def layer_text(text, f, fill, stroke=0, stroke_fill=None, xscale=1.0, shear=0.0, lines=False):
    """Text on a tight transparent layer (stroke included), optionally squeezed and slanted. lines: the height spans
    the font's capitals and descenders whatever the text, so every word shares one baseline."""
    l, t, r, bt = f.getbbox(text, stroke_width=stroke)
    if lines:
        _, t, _, bt = f.getbbox("Hgy" + text, stroke_width=stroke)
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


# --- event banners (1945-1991: PTP entry 1 = the word, a PTG over the 480-wide art) ------------------------------

BANNER_ITALIC = {1955, 1961, 1974, 1977, 1982, 1983, 1986, 1987}   # 110x48 white italic words with a black rim


def banner_layer(text, italic, size, xscale=1.0):
    if italic:
        return layer_text(text, font("LiberationSans-BoldItalic.ttf", size), (255, 255, 255, 255), 2, (0, 0, 0, 255), xscale,
                          lines=True)
    return layer_text(text, font("LiberationSerif-Bold.ttf", size), (2, 2, 2, 255), 2, (255, 255, 255, 255), xscale,
                      lines=True)


def fit_canvas(layer, size, wmax, clear):
    """For a resize PTG: layer(size, xscale) on one line, squeezed to fit wmax (to 0.8 at worst, then a smaller
    font), centred on a canvas cut to the text (height rounded up to the 8-row bands)."""
    while True:
        lt = layer(size, 1.0)
        xs = min(1.0, wmax / lt.width)
        if xs >= 0.8:
            break
        size -= 1
    lt = layer(size, xs) if xs < 1 else lt
    w, h = lt.width + lt.width % 2, -(-lt.height // 8) * 8
    im = Image.new("RGBA", (w, h), clear)
    im.alpha_composite(lt, ((w - lt.width) // 2, (h - lt.height) // 2))
    out = np.array(im)
    out[out[..., 3] == 0] = clear
    return out


def draw_banner(fid, off, text):
    b = (FILES / f"{fid:05d}.bin").read_bytes()
    assert struct.unpack_from("<I", b, 0x14)[0] == off, f"{fid}: PTP entry 1 is not at {off:#x}"
    italic = fid in BANNER_ITALIC
    return fit_canvas(lambda s, xs: banner_layer(text, italic, s, xs), 30 if italic else 28, 240,
                      (255, 0, 255, 0) if italic else (255, 255, 255, 0))


# --- team banners (26-65: "<team> advances!", one PTG per file, shown in the field's Info bar) -------------------

def team_layer(text, rim, size, xscale):
    """White slanted serif, a thick rim in the team colour and a soft translucent halo of it."""
    f = font("LiberationSerif-Bold.ttf", size)
    body = layer_text(text, f, (249, 249, 249, 255), 2, rim + (255,), xscale, 0.25, lines=True)
    halo = Image.new("RGBA", (body.width + 4, body.height + 4), (0, 0, 0, 0))
    mask = Image.new("L", halo.size, 0)
    mask.paste(body.split()[3], (2, 2))
    halo.paste(Image.new("RGBA", halo.size, rim + (191,)), mask=mask.filter(ImageFilter.MaxFilter(3)).filter(ImageFilter.GaussianBlur(1)))
    halo.alpha_composite(body, (2, 2))
    return halo


def draw_team(fid, a, text):
    vals, counts = np.unique(a[(a[..., 3] == 255) & (a[..., :3].max(2) < 120)][:, :3], axis=0, return_counts=True)
    rim = tuple(int(v) for v in vals[counts.argmax()])   # the commonest dark colour: the rim
    return fit_canvas(lambda s, xs: team_layer(text, rim, s, xs), 24, 320, (255, 255, 255, 0))


# --- OK? dialog titles (2020 +20 再開 blue, +1580 中断 red) -------------------------------------------------------

def draw_okq(a, text, w=242):
    """Black serif on the white plate, the [bracketed] word in the plate's own red or blue (中断 / 再開)."""
    a = a.copy()
    px = a[:, :w].reshape(-1, 4)
    sat = px[(px[:, 3] == 255) & (np.ptp(px[:, :3].astype(int), 1) > 60)]
    vals, counts = np.unique(sat, axis=0, return_counts=True)
    key = tuple(int(v) for v in vals[counts.argmax()])
    a[:, :w] = (255, 255, 255, 255)
    im = Image.fromarray(a)
    pre, word, post = text.replace("]", "[").split("[")
    size = 30
    while True:
        f = font("LiberationSerif-Bold.ttf", size)
        parts = [(s, c) for s, c in ((pre, (0, 0, 0, 255)), (word, key), (post, (0, 0, 0, 255))) if s]
        width = sum(f.getlength(s) for s, _ in parts)
        if width <= w - 10 or size <= 16:
            break
        size -= 1
    x, d = 6.0, ImageDraw.Draw(im)
    top = (a.shape[0] - (f.getbbox("Hg")[3] - f.getbbox("Hg")[1])) // 2 - f.getbbox("Hg")[1]
    for s, c in parts:
        d.text((x, top), s, font=f, fill=c)
        x += f.getlength(s)
    return np.array(im)


# --- word sheets (id 3 menus: the game draws each word from a (u, v, w, h) table in the EBOOT) --------------------

ELF = ROOT / "work" / "re" / "eboot.elf"


def table_rects(vaddr, n):
    """The n (u, v, w, h) s16 rects of an EBOOT table (segment 0 vaddr = file offset - 0xA0)."""
    d = ELF.read_bytes()
    return [list(struct.unpack_from("<4h", d, vaddr + 0xA0 + 8 * i)) for i in range(n)]


def ink_colours(a):
    """(fill, rim) of the old lettering: the commonest light and the commonest dark opaque colour."""
    px = a[a[..., 3] == 255][:, :3].astype(int)
    lum = px.sum(1)
    def pick(m):
        vals, counts = np.unique(px[m], axis=0, return_counts=True)
        return tuple(int(v) for v in vals[counts.argmax()]) + (255,)
    return pick(lum >= np.percentile(lum, 75)), pick(lum <= np.percentile(lum, 25))


def draw_words(a, rects, words, size, stroke=1):
    """Each word left-aligned in its rect, vertically centred. Rects that share a row (same v) are re-packed left to
    right to the English widths; a word alone on its row may widen its rect to the texture edge. Returns (image,
    new rects): build writes the rects into the EBOOT table (gfx.eboot)."""
    fill, rim = ink_colours(a)
    clear = tuple(int(v) for v in a[a[..., 3] == 0][0]) if (a[..., 3] == 0).any() else (255, 255, 255, 0)
    out = a.copy()
    for u, v, w, h in rects:
        out[v:v + h, u:u + w] = clear
    im = Image.fromarray(out)
    rows = {}
    for i, r in enumerate(rects):
        rows.setdefault((r[1], r[3]), []).append(i)
    new = [list(r) for r in rects]
    tw = a.shape[1]
    for (v, h), idx in rows.items():
        u0 = min(rects[i][0] for i in idx)
        room = tw - u0 if len(idx) > 1 else max(rects[idx[0]][2], tw - u0)
        f_size, xs = size, 1.0
        while True:   # one size for the whole row; squeeze to 0.8, then a smaller font
            f = font("LiberationSans-Bold.ttf", f_size)
            layers = [layer_text(words[i], f, fill, stroke, rim, xs, lines=True) for i in idx]
            need = sum(lt.width for lt in layers) + (len(idx) - 1)
            if need <= room and max(lt.height for lt in layers) <= h + 4:
                break
            if xs > 0.8:
                xs = max(0.8, xs * room / need - 0.01)
            else:
                f_size, xs = f_size - 1, 1.0
            assert f_size >= 9, f"{words[idx[0]]!r}: no room on row v={v}"
        u = u0
        for i, lt in zip(idx, layers):
            w = lt.width if len(idx) > 1 else max(rects[i][2], lt.width)
            new[i] = [u, v, w, h]
            crop = lt.crop((0, max(0, (lt.height - h) // 2), lt.width, max(0, (lt.height - h) // 2) + min(h, lt.height)))
            im.alpha_composite(crop, (u, v + max(0, (h - crop.height) // 2)))
            u += lt.width + 1
    res = np.array(im)
    res[res[..., 3] == 0] = clear
    return res, new


def draw_sheet(a, rects, redraw, size, h=16, face="LiberationSans-Bold.ttf", stroke=1):
    """Re-pack a whole word sheet: rect i in redraw ({i: English}) becomes a new word h px high (the game centres the
    bar's pieces on their rect height: icons 24 and words 16 sit on one line), every other rect keeps its pixels
    (icons, English already there). Shelf packing, tallest first; rects that were identical stay shared. Returns
    (image, new rects) for gfx.eboot."""
    ink = np.zeros(a.shape[:2], bool)
    for i in redraw:
        u, v, w, hh = rects[i]
        ink[v:v + hh, u:u + w] = True
    fill, rim = ink_colours(np.where(ink[..., None], a, 0))
    th, tw = a.shape[:2]
    while True:
        f = font(face, size)
        pieces = {}   # rect tuple -> image
        for i, r in enumerate(rects):
            k = tuple(r)
            if k in pieces:
                continue
            if i in redraw:   # the game draws each piece at a fixed spot, so a word keeps to its old width
                s, room = size, r[2] + 2
                while True:
                    lt = layer_text(redraw[i], font(face, s), fill, stroke, rim, lines=True)
                    xs = min(1.0, room / (lt.width - 2))
                    if xs >= 0.72 or s <= 9:
                        break
                    s -= 1
                if xs < 1:
                    lt = layer_text(redraw[i], font(face, s), fill, stroke, rim, xs, lines=True)
                top = (lt.height - h) // 2   # negative: PIL pads the crop with clear rows
                pieces[k] = np.array(lt.crop((1, top, lt.width - 1, top + h)))
            else:
                u, v, w, hh = r
                pieces[k] = a[v:v + hh, u:u + w]
        order = sorted(pieces, key=lambda k: (-pieces[k].shape[0], -pieces[k].shape[1]))
        place, x, y, shelf = {}, 0, 0, 0
        for k in order:
            ph, pw = pieces[k].shape[:2]
            if x + pw > tw:
                x, y, shelf = 0, y + shelf, 0
            place[k] = (x, y)
            x, shelf = x + pw, max(shelf, ph)
        if y + shelf <= th:
            break
        size -= 1
        assert size >= 9, "word sheet: no room"
    out = np.zeros_like(a)
    for k, (x, y) in place.items():
        p = pieces[k]
        out[y:y + p.shape[0], x:x + p.shape[1]] = p
    out[out[..., 3] == 0] = 0
    return out, [[*place[tuple(r)], pieces[tuple(r)].shape[1], pieces[tuple(r)].shape[0]] for r in rects]


def eboot(e):
    """insert.py: write each word sheet's new rects (gfx/NAME.rects) into its EBOOT table."""
    for name, a in ASSETS.items():
        p = GFX / f"{name}.rects"
        if not a.get("table") or not p.exists():
            continue
        vaddr, n = a["table"]
        rects = [[int(x) for x in ln.split()] for ln in p.read_text("utf8").split("\n") if ln.strip()]
        assert len(rects) == n, f"{p}: {len(rects)} rects, table has {n}"
        old = ELF.read_bytes()[vaddr + 0xA0:vaddr + 0xA0 + 8 * n]
        e.put(vaddr, b"".join(struct.pack("<4h", *r) for r in rects), expect=old, by=f"gfx {name}")


def draw_label(a, text, face, size, keep=0, dark_fill=True, shear=0.0, stroke=2, wmax=0):
    """A one-line label (id 3 PTGs): the old lettering right of column `keep` (an icon left of it stays) cleared, the
    English in the old ink colours, left-aligned, vertically centred, squeezed (to 0.75, then a smaller font) to fit.
    wmax: the canvas may widen to that (a resize asset; the game centres a PTG on its w)."""
    light, dark = ink_colours(a[:, keep:])
    fill, rim = (dark, light) if dark_fill else (light, dark)
    clear = (0, 0, 0, 0)   # quantize maps it to the palette's clear entry
    h = a.shape[0]
    while True:
        f = font(face, size)
        lt = layer_text(text, f, fill, stroke, rim, 1.0, shear, lines=True)
        room = max(a.shape[1], min(wmax, lt.width + keep + 3)) - keep - 2
        xs = min(1.0, room / lt.width)
        if xs >= 0.75 and lt.height <= h + 2:
            break
        size -= 1
    if xs < 1:
        lt = layer_text(text, f, fill, stroke, rim, xs, shear, lines=True)
    cw = room + keep + 2
    out = np.zeros((h, cw + cw % 2, 4), np.uint8)
    out[:, :keep] = a[:, :keep]
    im = Image.fromarray(out)
    im.alpha_composite(lt.crop((0, max(0, (lt.height - h) // 2), lt.width, max(0, (lt.height - h) // 2) + h)),
                       (keep + 1, max(0, (h - lt.height) // 2)))
    res = np.array(im)
    res[res[..., 3] == 0] = clear
    return res


def draw_fixed(a, items, size, face="LiberationSans-Bold.ttf", stroke=1, pad=1, ink=None):
    """Same-rect redraw (the game's rects stay): each (rect, text, dark_fill) is cleared (pad px wider: the old shadow)
    and the English drawn in it left-aligned, vertically centred, in that rect's old ink colours (or ink=(light, dark)),
    squeezed (to 0.75, then a smaller font) to fit."""
    inks = [ink or ink_colours(a[v:v + h, u:u + w]) for (u, v, w, h), _, _ in items]
    out = a.copy()
    for (u, v, w, h), _, _ in items:
        out[max(0, v - pad):v + h + pad, max(0, u - pad):u + w + pad] = 0
    im = Image.fromarray(out)
    for ((u, v, w, h), text, dark), (light, darkc) in zip(items, inks):
        if not text:   # a counter English does without (枚, 人): left blank
            continue
        n = len(text) - len(text.lstrip(" "))   # leading spaces: a 4 px indent each (a word drawn after a name)
        text, u, w = text.lstrip(" "), u + 4 * n, w - 4 * n
        fill, rim = (darkc, light) if dark else (light, darkc)
        s = size
        while True:
            lt = layer_text(text, font(face, s), fill, stroke, rim, lines=True)
            xs = min(1.0, (w + 2) / lt.width)   # the layer has 2 px of clear padding each side
            if xs >= 0.75 and lt.height - 4 <= h + 1:
                break
            s -= 1
            assert s >= 8, f"{text!r}: no room in {w}x{h}"
        if xs < 1:
            lt = layer_text(text, font(face, s), fill, stroke, rim, xs, lines=True)
        top = (lt.height - h) // 2
        im.alpha_composite(lt.crop((2, max(0, top), min(lt.width, w + 2), max(0, top) + min(h, lt.height))),
                           (u, v + max(0, -top)))
    res = np.array(im)
    res[res[..., 3] == 0] = 0   # quantize maps it to the palette's clear entry
    return res


# --- registry ---------------------------------------------------------------------------------------------------

ASSETS = {}


def asset(name, file, kind, off, rect, draw, resize=False, table=None, section=None):
    """resize (ptg only): the redraw may have another w x h than the original; write() repacks the sprites to it.
    table (vaddr, n): an EBOOT rect table the draw function re-lays out (it returns (image, rects)).
    section: the FCT section (a PTP) of file id 3 holding the texture; off stays the offset in the whole file. Needed
    for a resize there (the section grows; insert.cpk re-lays id 3 the same way for the common scripts)."""
    assert not (resize and file == 3 and section is None), "a resize in id 3 needs its section"
    ASSETS[name] = dict(name=name, file=file, kind=kind, off=off, rect=rect, draw=draw, resize=resize, table=table,
                        section=section)


def words(name, file, off, w, h, table, keys, size):
    asset(name, file, "ptx", off, (0, 0, w, h),
          lambda a, t: draw_words(a, table_rects(*table), [t[k] for k in keys], size), table=table)


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
for _f in range(1945, 1992):
    _o = 0x8B40 if _f == 1986 else 0x8940 if _f in BANNER_ITALIC else 0x5C40
    asset(f"banner{_f}", _f, "ptg", _o, (0, 0, 0, 0), lambda a, t, f=_f, o=_o: draw_banner(f, o, t[f"banner{f}"]), resize=True)
for _f in range(26, 66):
    asset(f"team{_f}", _f, "ptg", 0, (0, 0, 0, 0), lambda a, t, f=_f: draw_team(f, a, t[f"team{f}"]), resize=True)
asset("ok_resume", 2020, "ptx", 0x20, (0, 0, 242, 38), lambda a, t: draw_okq(a, t["ok_resume"]))
asset("ok_suspend", 2020, "ptx", 0x1580, (0, 0, 242, 38), lambda a, t: draw_okq(a, t["ok_suspend"]))
asset("credits", 1992, "stack", [0x1640 + 0xE060 * i for i in range(9)], (0, 0, CRED_W, 4159), draw_credits)
MAP_MENU = ["menu_end_turn", "menu_full_map", "menu_unit_list", "menu_card_list", "menu_weapons", "menu_terrain",
            "menu_objects", "menu_tutorial", "menu_conditions", "menu_suspend"]
words("map_menu_hi", 3, 0x16db60, 256, 114, (0x2f3638, 10), MAP_MENU, 16)   # the highlighted row
words("map_menu", 3, 0x171ac0, 160, 170, (0x2f3688, 10), MAP_MENU, 16)
for _n, _o, _kw in (("ok_battle", 0x36f4c0, dict(face="LiberationSerif-Bold.ttf", size=34)),
                    ("ok_end_turn", 0x3708a0, dict(face="LiberationSans-BoldItalic.ttf", size=30, dark_fill=False)),
                    ("card_select", 0x3924e0, dict(face="LiberationSans-Bold.ttf", size=24, keep=24, wmax=220))):   # drawn from its left edge: Time/Weather starts ~225 px right of it
    asset(_n, 3, "ptg", _o, (0, 0, 512, 512), lambda a, t, n=_n, kw=_kw: draw_label(a, t[n], **kw), resize=True,
          section=14)


WHITE_INK = ((255, 255, 255, 255), (6, 6, 6, 251))   # plain white dialog text with its near-black rim


def id3_section(off):
    """The FCT section of id 3 holding offset off: needed from section 14 on, which the resizes there move."""
    return 14 if 0x36f230 <= off < 0x450e90 else 16 if off >= 0x4a6910 else None


def fixed(name, off, w, h, items, size, **kw):
    """An id 3 PTX redrawn inside the old words' ink boxes (items: (rect, text key, dark_fill)); no table change."""
    asset(name, 3, "ptx", off, (0, 0, w, h),
          lambda a, t: draw_fixed(a, [(r, t[k], d) for r, k, d in items], size, **kw), section=id3_section(off))


fixed("forecast", 0x33cb90, 96, 84, [((0, 0, 84, 15), "fc_survivors", False), ((0, 17, 45, 15), "fc_stat_gap", False),
                                      ((0, 33, 58, 15), "fc_bonus", False), ((0, 49, 84, 15), "fc_terrain", False),
                                      ((0, 65, 84, 19), "fc_morale", False)], 13)   # a bar icon at x 62-82, y 17-48
fixed("deploy", 0x175400, 128, 58, [((0, 0, 128, 29), "deploy_units", False), ((0, 29, 128, 29), "deploy_location", False)], 24)
fixed("checking", 0x168be0, 224, 40, [((18, 0, 204, 19), "checking_map", False), ((18, 20, 204, 19), "checking_status", False)],
      17, pad=2)   # ">>" at x 1-15 stays
fixed("conditions", 0x161060, 176, 65, [((0, 0, 119, 27), "cond_victory", True), ((0, 27, 119, 27), "cond_defeat", True)], 20)
fixed("suspend_slot", 0x131ad0, 192, 78, [((0, 0, 151, 23), "slot_suspend", False), ((140, 16, 41, 13), "slot_durability", False),
                                          ((0, 55, 191, 23), "slot_gloria", False)], 20)   # the ※まだ行動できます! pill: still JP
fixed("counts", 0xEC350, 320, 40, [((261, 0, 52, 15), "cnt_sortie", False), ((261, 15, 56, 15), "cnt_selectable", False),
                                   ((140, 25, 76, 15), "cnt_cards_left", False), ((221, 11, 14, 14), "cnt_cards", False),
                                   ((234, 25, 16, 15), "cnt_people", False)], 13, pad=0)   # rects: EBOOT table 0x2f2808..
fixed("range", 0xE0000, 320, 30, [((240, 16, 32, 14), "range", False)], 12, pad=0)   # table 0x2f2380 entry 11
fixed("items", 0x3812e0, 272, 154, [((0, 45, 224, 22), "item_none", False), ((107, 79, 70, 12), "item_ship", False),
                                    ((0, 95, 54, 11), "item_status", False), ((73, 90, 137, 24), "item_equipped", False),
                                    ((0, 115, 64, 11), "item_details", False), ((187, 112, 70, 18), "item_close", False)], 18)
fixed("save_ask", 0x4444d0, 352, 108, [((208, 1, 29, 19), "save_yes", False), ((253, 1, 45, 19), "save_no", False),
                                       ((3, 22, 320, 22), "save_q", False), ((0, 44, 296, 22), "save_nosave_q", False),
                                       ((0, 67, 72, 17), "save_save", False), ((75, 67, 110, 17), "save_next_map", False),
                                       ((4, 87, 248, 21), "save_clear_q", False)], 18, ink=WHITE_INK)
fixed("reset_ask", 0x4494f0, 352, 44, [((124, 2, 71, 17), "reset_cancel", False), ((196, 2, 128, 17), "reset_title", False),
                                       ((6, 23, 210, 21), "reset_q", False), ((224, 23, 95, 17), "reset_restart", False)], 18,
      ink=WHITE_INK)
fixed("hud_words", 0x3e2af0, 192, 31, [((102, 1, 38, 18), "hud_morale", False), ((145, 0, 34, 17), "hud_equip", False),
                                       ((145, 18, 30, 13), "hud_win_rate", False)], 14)
asset("hud_small", 3, "ptx", 0x398650, (0, 0, 224, 247),   # the 非戦闘ユニットです pill: still JP
      lambda a, t: draw_fixed(draw_fixed(a, [((140, 47, 25, 12), t["hud_morale"], False),
                                             ((21, 150, 42, 16), t["slot_durability"], False),
                                             ((71, 124, 42, 14), t["hud_on_board"], False)], 12, pad=0),
                              [((0, 166, 174, 34), t["checking_map"], False), ((0, 213, 133, 34), t["checking_status"], False)],
                              30, stroke=2, pad=0), section=14)


BUTTONS = {4: "btn_confirm", 5: "btn_back", 6: "btn_data", 7: "btn_help", 8: "btn_switch_unit", 10: "btn_enemy_cards",
           14: "btn_switch", 17: "btn_move_cursor", 20: "btn_select", 22: "btn_status", 23: "btn_captain", 24: "btn_back",
           25: "btn_field", 26: "btn_conditions", 27: "btn_map", 28: "btn_card_data", 30: "btn_next_page",
           31: "btn_skip_check", 32: "btn_end"}   # the rest: button icons and English words, kept
asset("buttons", 3, "ptx", 0xF0390, (0, 0, 240, 144),
      lambda a, t: draw_sheet(a, table_rects(0x2f28b0, 33), {i: t[k] for i, k in BUTTONS.items()}, 12),
      table=(0x2f28b0, 33))


def gen(names=None):
    t = text_tsv()
    GFX.mkdir(exist_ok=True)
    for name in names or ASSETS:
        a = ASSETS[name]
        b = (FILES / f"{files(a)[0]:05d}.bin").read_bytes()
        orig = read(b, a)
        for i in files(a)[1:]:
            assert np.array_equal(read((FILES / f"{i:05d}.bin").read_bytes(), a), orig), f"{name}: {i} differs"
        new = a["draw"](orig, t)
        if a["table"]:
            new, rects = new
            (GFX / f"{name}.rects").write_text("".join(" ".join(map(str, r)) + "\n" for r in rects), "utf8")
        new = fit(b, a, new)
        if new.shape == orig.shape:
            x, y, w, h = a["rect"]
            keep = np.ones(orig.shape[:2], bool)
            keep[y:y + h, x:x + w] = False
            new[keep] = orig[keep]
        Image.fromarray(new).save(GFX / f"{name}.png")
        print(name, f"{new.shape[1]}x{new.shape[0]} (was {orig.shape[1]}x{orig.shape[0]})" if new.shape != orig.shape
              else f"{(new != orig).any(2).sum()} pixels changed")


if __name__ == "__main__":
    cmd, *args = sys.argv[1:] or ["gen"]
    if cmd == "gen":
        gen(args)
    elif cmd == "orig":
        (ROOT / "work" / "gfx" / "orig").mkdir(parents=True, exist_ok=True)
        for name in args:
            Image.fromarray(original(name)).save(ROOT / "work" / "gfx" / "orig" / f"{name}.png")
