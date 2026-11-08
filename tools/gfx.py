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


def moved(b, a):
    """The asset with its offset in b: a PTG resize in a PTP file moves the later entries (two resized PTGs in one
    file), so a PTP entry is found again by its number."""
    if a["kind"] == "stack" or b[:4] != b"PTP\0":
        return a
    orig = (FILES / f"{files(a)[0]:05d}.bin").read_bytes()
    n = struct.unpack_from("<I", orig, 4)[0]
    ents = list(struct.unpack_from(f"<{n}I", orig, 0x10))
    if a["off"] not in ents:
        return a
    return dict(a, off=struct.unpack_from("<I", b, 0x10 + 4 * ents.index(a["off"]))[0])


def read(b, a):
    if a["section"] is not None:
        return read(*section(b, a))
    a = moved(b, a)
    if a["kind"] == "stack":
        return np.vstack([ptx.decode(bytes(b), t) for _, t in bands(b, a)])
    return ptx.decode(bytes(b), ptx.parse(b, a["off"])) if a["kind"] == "ptx" else ptx.ptg(bytes(b), a["off"])


def fit(b, a, img):
    """Quantize img to the palette(s) it will be written with (stack: each texture's own)."""
    if a["kind"] == "ptg" and not a["resize"] and a["section"] is None:
        base, pieces, sprites = ptx.ptg_parts(b, moved(b, a)["off"])
        pals = [np.frombuffer(bytes(b), np.uint8, t["n"] * 4, base + t["po"]).reshape(-1, 4).astype(int) for t in pieces]
        if len({p.tobytes() for p in pals}) > 1:   # pieces with their own palettes: each sprite in its piece's palette
            img = np.asarray(img)
            out = np.zeros_like(img)
            shown = np.zeros(img.shape[:2], bool)
            for k, u0, v0, u1, v1, x0, y0, x1, y1 in sprites:
                out[y0:y1, x0:x1] = quantize(img[y0:y1, x0:x1], pals[k])
                shown[y0:y1, x0:x1] = True
            lost = (img[..., 3] > 0) & ~shown   # dropped: a few rim specks are fine, whole letters are not
            assert lost.sum() <= 120, f"{a['name']}: {lost.sum()} pixels outside every sprite, first {np.argwhere(lost)[0][::-1]}"
            return out
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
    a = moved(b, a)
    if a["kind"] == "stack":
        for y, t in bands(b, a):
            out = ptx.encode(b, t, img[y:y + t["h"]])
            b[t["do"]:t["do"] + len(out)] = out
    elif a["kind"] == "ptx":
        t = ptx.parse(b, a["off"])
        out = ptx.encode(b, t, img)
        b[t["do"]:t["do"] + len(out)] = out
        if a.get("used"):   # a texture the game draws whole, `used` px wide (header +8): widen it to the new ink
            cols = np.flatnonzero(img[..., 3].any(0))
            struct.pack_into("<H", b, a["off"] + 8, int(cols[-1]) + 1 if len(cols) else t["used"])
    else:
        if a["resize"]:   # the PNG sets the canvas: rebuild the PTG's atlas and sprites for it (the file size changes)
            ptx.ptg_resize(b, a["off"], img.shape[1], img.shape[0], a.get("trim") and spans(img))
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


def spans(img, gap=16):
    """Per 8-row band, the (x0, x1) runs holding any non-clear pixel (runs closer than gap merged): a trimmed resize
    gives sprites only to these, so the file grows little (the game loads some files into fixed buffers: file 2023
    at twice its size hung the tutorial)."""
    out = []
    for y in range(0, img.shape[0], 8):
        cols = np.flatnonzero(img[y:y + 8, :, 3].any(0))
        runs = []
        for c in cols:
            if runs and c - runs[-1][1] < gap:
                runs[-1][1] = c + 1
            else:
                runs.append([c, c + 1])
        out.append([tuple(map(int, r)) for r in runs])
    return out


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
    clear = pal[pal[:, 3] == pal[:, 3].min()]
    if clear[0, 3] <= 8:   # clear stays clear, whatever its RGB (a clear (0,0,0,0) is nearer a dark opaque entry);
        out[a[..., 3] == 0] = clear[0]   # some palettes' clearest entry is alpha 1 (2427 place plates)
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
        px = np.array(im)
        px[px[..., 3] < 48] = 0   # Lanczos ringing: faint specks that quantize to visible dots
        im = Image.fromarray(px)
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


def _word(text, face, size, ink, stroke, h, wmax, smin=9):
    """One word piece h px high, at most wmax px wide: squeezed to 0.75 (font shrunk down to smin px if need be), else
    its two halves (split at a space) stacked in a smaller font."""
    for s in range(size, smin - 1, -1):
        lt = layer_text(text, font(face, s), ink[0], stroke, ink[1], lines=True)
        if wmax / (lt.width - 2) >= 0.75:
            break
    if wmax / (lt.width - 2) < 0.75:   # two lines below
        lt = layer_text(text, font(face, size), ink[0], stroke, ink[1], lines=True)
    elif lt.width - 2 > wmax:
        lt = layer_text(text, font(face, s), ink[0], stroke, ink[1], (wmax + 2) / lt.width, lines=True)
    if lt.width - 2 > wmax:
        assert " " in text, f"{text!r}: wider than {wmax} px and no space to split at"
        top, bot = text.split(" ", 1)
        for s in range(size, 6, -1):
            ls = [layer_text(x, font(face, s), ink[0], stroke, ink[1]) for x in (top, bot)]
            if sum(x.height - 3 for x in ls) <= h + 1:
                break
        xs = min(1.0, (wmax + 2) / max(x.width for x in ls))
        ls = [x.resize((max(1, round(x.width * xs)), x.height), Image.LANCZOS) for x in ls]
        lt = Image.new("RGBA", (max(x.width for x in ls), h + 4), (0, 0, 0, 0))
        y = max(0, (h + 4 - sum(x.height - 2 for x in ls)) // 2)
        for x in ls:
            lt.alpha_composite(x, ((lt.width - x.width) // 2, y))
            y += x.height - 3
    top = (lt.height - h) // 2
    return np.array(lt.crop((1, top, lt.width - 1, top + h)))


def draw_pack(a, rects, redraw, size, face="LiberationSans-Bold.ttf", stroke=1, wmax=999, smin=9):
    """Words too wide for their cells: rect i in redraw ({i: English}) is cleared and its English (one font size for
    all, shrunk until every word fits, the old rect height, at most wmax ({i: px} or px) wide: _word) placed in the first free spot
    of the sheet, longest first. Free = clear pixels outside every kept rect of the table. Returns (image, new rects)
    for gfx.eboot."""
    sub = np.zeros(a.shape[:2], bool)
    inks = {}   # each word in its own old colours (time of day: orange, red, blue)
    for i in redraw:
        u, v, w, h = rects[i]
        sub[v:v + h, u:u + w] = True
        inks[i] = ink_colours(a[v:v + h, u:u + w])
    out = a.copy()
    out[sub] = 0
    th, tw = a.shape[:2]
    while True:
        used = out[..., 3] > 4   # some sheets' clear colour has alpha 2
        for i, (u, v, w, h) in enumerate(rects):
            if i not in redraw:
                used[v:v + h, u:u + w] = True
        layers = {}
        for i, t in redraw.items():
            layers[i] = _word(t, face, size, inks[i], stroke, rects[i][3],
                              wmax.get(i, 999) if isinstance(wmax, dict) else wmax, smin)
        new, ok = [list(r) for r in rects], True
        for i in sorted(layers, key=lambda i: -layers[i].shape[1]):
            h, w = layers[i].shape[:2]
            spot = next(((x, y) for y in range(th - h + 1) for x in range(tw - w + 1)
                         if not used[y:y + h, x:x + w].any()), None)
            if spot is None:
                ok = False
                break
            x, y = spot
            used[y:y + h, x:x + w] = True
            new[i] = [x, y, w, h]
        if ok:
            break
        size -= 1
        assert size >= smin, "pack: no room"
    im = Image.fromarray(out)
    for i, p in layers.items():
        im.alpha_composite(Image.fromarray(p), tuple(new[i][:2]))
    res = np.array(im)
    res[res[..., 3] == 0] = 0
    return res, new


def eboot(e):
    """insert.py: write each word sheet's new rects (gfx/NAME.rects) into its EBOOT table."""
    for name, a in ASSETS.items():
        p = GFX / f"{name}.rects"
        if not a.get("table") or not p.exists():
            continue
        rects = [[int(x) for x in ln.split()] for ln in p.read_text("utf8").split("\n") if ln.strip()]
        tables = tables_of(a)
        assert len(rects) == sum(n for _, n in tables), f"{p}: {len(rects)} rects, tables have {tables}"
        for vaddr, n in tables:   # the .rects file lists every table's rects in order
            old = ELF.read_bytes()[vaddr + 0xA0:vaddr + 0xA0 + 8 * n]
            e.put(vaddr, b"".join(struct.pack("<4h", *r) for r in rects[:n]), expect=old, by=f"gfx {name}")
            rects = rects[n:]


def tables_of(a):
    """An asset's EBOOT rect tables: table is (vaddr, n) or a list of them (one sheet used by several screens)."""
    return a["table"] if isinstance(a["table"], list) else [a["table"]]


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


def draw_fixed(a, items, size, face="LiberationSans-Bold.ttf", stroke=1, pad=1, ink=None, clear=True, center=False):
    """Same-rect redraw (the game's rects stay): each (rect, text, dark_fill) is cleared (pad px wider: the old shadow)
    and the English drawn in it left-aligned (or centred), vertically centred, in that rect's old ink colours (or
    ink=(light, dark)), squeezed (to 0.75, then a smaller font) to fit. clear=False: the caller already removed the
    old lettering (text on a filled shape)."""
    inks = [ink or ink_colours(a[v:v + h, u:u + w]) for (u, v, w, h), _, _ in items]
    out = a.copy()
    for (u, v, w, h), _, _ in items:
        if clear:
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
        dx = max(0, (w - (lt.width - 4)) // 2) if center else 0
        im.alpha_composite(lt.crop((2, max(0, top), min(lt.width, w + 2 - dx), max(0, top) + min(h, lt.height))),
                           (u + dx, v + max(0, -top)))
    res = np.array(im)
    res[res[..., 3] == 0] = 0   # quantize maps it to the palette's clear entry
    return res


# --- registry ---------------------------------------------------------------------------------------------------

ASSETS = {}


def asset(name, file, kind, off, rect, draw, resize=False, table=None, section=None, trim=False, used=False):
    """resize (ptg only): the redraw may have another w x h than the original; write() repacks the sprites to it.
    table (vaddr, n): an EBOOT rect table the draw function re-lays out (it returns (image, rects)).
    section: the FCT section (a PTP) of file id 3 holding the texture; off stays the offset in the whole file. Needed
    for a resize there (the section grows; insert.cpk re-lays id 3 the same way for the common scripts).
    used (ptx): the game draws the whole texture `used` px wide (PTX header +8, e.g. the 2427 place plates): write()
    sets it to the redraw's ink width, so English may use the texture's full width."""
    assert not (resize and file == 3 and section is None), "a resize in id 3 needs its section"
    ASSETS[name] = dict(name=name, file=file, kind=kind, off=off, rect=rect, draw=draw, resize=resize, table=table,
                        section=section, trim=trim, used=used)


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


REGULAR = "LiberationSans-Regular.ttf"   # small light lettering with a 1 px rim: bold closes up below ~15 px
WHITE_INK = ((255, 255, 255, 255), (6, 6, 6, 251))   # plain white dialog text with its near-black rim


def id3_section(off):
    """The FCT section of id 3 holding offset off: needed from section 14 on, which the resizes there move."""
    return 14 if 0x36f230 <= off < 0x450e90 else 16 if off >= 0x4a6910 else None


def fixed(name, off, w, h, items, size, file=3, **kw):
    """A PTX (id 3 unless file=) redrawn inside the old words' ink boxes (items: (rect, text key, dark_fill)); no
    table change."""
    asset(name, file, "ptx", off, (0, 0, w, h),
          lambda a, t: draw_fixed(a, [(r, t[k], d) for r, k, d in items], size, **kw),
          section=id3_section(off) if file == 3 else None)


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
fixed("stat_words", 0xEAED0, 128, 30, [((0, 15, 23, 15), "stat_durability", False), ((23, 15, 23, 15), "stat_morale", False)],
      12, pad=0)   # table 0x2f2630 entries 11-12; the number after each is drawn at a fixed x, so 23 px is all there is
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


TERRAIN = ["ter_bridge", "ter_road", "ter_plains", "ter_wasteland", "ter_forest", "ter_desert", "ter_swamp", "ter_sea",
           "ter_ice", "ter_waterside", "ter_village", "ter_city", "ter_fortress", "ter_beach", "ter_street", "ter_ruins",
           "ter_alley"]   # table 0x2f3368.., entries 9-25 of the run from 0x2f3320
WEATHER = {1: "wx_clear", 2: "wx_rain", 3: "wx_fog", 4: "wx_snow", 5: "wx_storm"}   # 0x2f3328.. (entry 0: the slash)
asset("hud_terrain", 3, "ptx", 0x1583a0, (0, 0, 224, 202),
      lambda a, t: draw_pack(a, table_rects(0x2f3320, 26),
                             {**{i: t[k] for i, k in WEATHER.items()}, **{9 + i: t[k] for i, k in enumerate(TERRAIN)}}, 13,
                             wmax={**{i: 28 for i in WEATHER}, **{9 + i: 40 for i in range(len(TERRAIN))}}),
      # the field bar draws each word at a fixed x: the sun icon ~30 px, "-20%" ~41 px right of it

      table=(0x2f3320, 26))
asset("hud_time", 3, "ptx", 0x15e1a0, (0, 0, 96, 110),
      lambda a, t: draw_pack(a, table_rects(0x2f3478, 3), {0: t["time_day"], 1: t["time_evening"], 2: t["time_night"]}, 14,
                             wmax=38),   # the "/" after it is ~40 px right
      table=(0x2f3478, 3))


BUTTONS = {4: "btn_confirm", 5: "btn_back", 6: "btn_data", 7: "btn_help", 8: "btn_switch_unit", 10: "btn_enemy_cards",
           14: "btn_switch", 17: "btn_move_cursor", 20: "btn_select", 22: "btn_status", 23: "btn_captain", 24: "btn_back",
           25: "btn_field", 26: "btn_conditions", 27: "btn_map", 28: "btn_card_data", 30: "btn_next_page",
           31: "btn_skip_check", 32: "btn_end"}   # the rest: button icons and English words, kept
asset("buttons", 3, "ptx", 0xF0390, (0, 0, 240, 144),
      lambda a, t: draw_sheet(a, table_rects(0x2f28b0, 33), {i: t[k] for i, k in BUTTONS.items()}, 12),
      table=(0x2f28b0, 33))


# --- character select (asset file 2418) ---------------------------------------------------------------------------

def draw_arrows(a, words):
    """The two 60 px double arrows (装備|回復, 船長|改造; the screen shows each one's left half at the left edge and its
    right half at the right). The lettering is found as opaque non-yellow pixels whose mirror image across the
    arrow's axis differs (the outline is symmetric), filled from the yellow around it, and the English drawn in the
    old orange, one word per half."""
    body = np.array([253, 243, 68, 255])
    m = np.zeros(a.shape[:2], bool)
    for x0 in (0, 60):
        part = a[17:39, x0:x0 + 60].astype(int)
        mirror = part[:, ::-1]
        inner = np.zeros(part.shape[:2], bool)
        inner[:, 7:53] = True   # no outline there in these rows
        m[17:39, x0:x0 + 60] = (part[..., 3] >= 100) & (part != body).any(2) & ((part != mirror).any(2) | inner)
    out = inpaint(a, grow(m) & (a[..., 3] >= 100))
    orange = (251, 113, 40, 255)
    rects = [(3, 18, 26, 20), (31, 18, 26, 20), (63, 18, 26, 20), (91, 18, 26, 20)]
    return draw_fixed(out, [(r, w, False) for r, w in zip(rects, words)], 11, stroke=0, ink=(orange, orange),
                      clear=False, center=True)


asset("cs_arrows", 2418, "ptx", 0x15590, (0, 0, 120, 62),
      lambda a, t: draw_arrows(a, [t["cs_equip"], t["cs_heal"], t["cs_captain"], t["cs_refit"]]))
SORT = {0: "sort_default", 1: "sort_name", 4: "sort_used", 5: "sort_label", 7: "sort_kana", 8: "sort_recovery"}
asset("cs_sort", 2418, "ptx", 0x1cfc0, (0, 0, 160, 38),
      # tables: the equipment list's words + ":並び替え" (0x2ca29e), the morale list's ":並び替え" + words (0x2cb0cc);
      # each word is drawn after the label at a fixed x with nothing right of it, so it may grow
      lambda a, t: (lambda r: (r[0], r[1][:6] + [r[1][5]] + r[1][7:]))(
          draw_pack(a, table_rects(0x2ca29e, 6) + table_rects(0x2cb0cc, 3), {i: t[k] for i, k in SORT.items()}, 11)),
      table=[(0x2ca29e, 6), (0x2cb0cc, 3)])
asset("cs_headers", 2418, "ptx", 0x1dd40, (0, 0, 96, 135),   # rects (0, 27k, 84, 27): table 0x2ca846 and others
      lambda a, t: draw_fixed(a, [((0, 27 * i, 96 if i == 4 else 84, 27), t[k], False) for i, k in
                                  enumerate(["hd_equip", "hd_equipped", "hd_morale", "hd_captain", "hd_refit"])],
                              20, face="LiberationSans-BoldItalic.ttf", stroke=2, pad=0))
def draw_chips(a, t):
    out = a.copy()
    box = out[30:43, 72:85]   # the 出 chip (table 0x2f9604): dark letter on light grey inside a dark frame
    corners = [box[i, j].copy() for i, j in ((1, 1), (1, 11), (11, 1), (11, 11))]
    box[1:12, 1:12] = (206, 206, 206, 255)
    for (i, j), c in zip(((1, 1), (1, 11), (11, 1), (11, 11)), corners):
        box[i, j] = c
    out = draw_fixed(out, [((73, 31, 11, 11), t["chip_sortie"], False)], 11, stroke=0,
                     ink=((43, 42, 41, 255), (43, 42, 41, 255)), clear=False, center=True)
    return draw_fixed(out, [((50, 29, 21, 15), t["chip_repair"], True), ((73, 56, 73, 11), t["chip_ship"], False)],
                      11, pad=0, center=True)


asset("cs_chips", 2418, "ptx", 0x1f750, (0, 0, 160, 79), draw_chips)
NAMES = ["ishut", "pinger", "ruru", "zazarland", "elisha", "minesota", "locomoco", "raspberry", "gangr", "fiebee",
         "anne", "kamuru", "yggdra", "pamela", "eater"]
asset("cs_names", 2418, "ptx", 0x28770, (0, 0, 224, 192),   # cells: table 0x2ca6e6 (and 0x2cb034, same cells)
      lambda a, t: draw_fixed(a, [(tuple(r), t[f"name_{k}"], True) for r, k in zip(table_rects(0x2ca6e6, 15), NAMES)],
                              20, face="LiberationSans-BoldItalic.ttf", stroke=2, pad=0, center=True))


asset("cs_names_list", 2422, "ptx", 0xea0, (0, 0, 224, 192), ASSETS["cs_names"]["draw"])   # same pixels: the equip bar


def draw_ship_abilities(a, t):
    """2424 status list: the last two rows (夜間も砲撃可, 砲撃後も移動可) are text on the sheet's own pale yellow."""
    out = a.copy()
    out[80:100, 9:76] = (255, 251, 149, 255)
    for y0, k, ink in ((80, "ab_night_fire", (65, 162, 228, 255)), (90, "ab_fire_move", (255, 58, 35, 255))):
        out = draw_fixed(out, [((9, y0, 67, 10), t[k], False)], 11, stroke=0, ink=(ink, ink), clear=False)
    return out


asset("ship_abilities", 2424, "ptx", 0x23a60, (9, 80, 67, 20), draw_ship_abilities)
for _n, _o, _s in (("refit_prompt", 0x266d0, 17), ("reward_prompt", 0x2dbd0, 21)):   # one-line PTG prompts (ship, reward)
    asset(_n, 2418, "ptg", _o, (0, 0, 512, 512),
          lambda a, t, n=_n, s=_s: draw_label(a, t[n], "LiberationSans-Bold.ttf", s, dark_fill=False), resize=True)


def draw_fixed_chip(a, text):
    """固定 (weather fixed) on the field bar: white letters on a brown chip, table 0x2b7ffc (149, 15, 20, 16)."""
    out = a.copy()
    out[17:27, 149:169] = (166, 145, 125, 255)
    white = (254, 251, 243, 255)
    return draw_fixed(out, [((149, 17, 20, 10), text, False)], 9, stroke=0, ink=(white, white), clear=False,
                      center=True)


asset("weather_fixed", 3, "ptx", 0x38bd80, (149, 17, 20, 10), lambda a, t: draw_fixed_chip(a, t["wx_fixed"]),
      section=id3_section(0x38bd80))


def draw_cards_left(a, t):
    """2426 card list footer: 残された戦略は… over あと [n] 枚 (the number is drawn between the two words)."""
    # glyph boxes: NOW USING... starts at x 48 in rows 16-23, right of 枚
    return draw_fixed(a, [((0, 0, 115, 16), t["cl_left"], False), ((0, 16, 30, 18), t["cl_only"], False),
                          ((31, 16, 17, 18), t["cl_cards"], False)], 17, stroke=2, pad=0,
                      ink=ink_colours(a[0:16, 0:115]))   # the small boxes' commonest light colour is a grey edge


asset("cards_left", 2426, "ptx", 0x3520, (0, 0, 115, 34), draw_cards_left)
asset("card_headers", 2362, "ptx", 0x9040, (0, 26, 211, 15),   # rects: table 0x2c98ba
      lambda a, t: draw_fixed(a, [((0, 26, 155, 15), t["cd_effect"], False), ((155, 26, 56, 15), t["cd_condition"], False)],
                              14, pad=0, stroke=0, ink=((68, 250, 255, 254),) * 2))   # plain cyan, no rim


def card_names():
    """The 54 card names in card order (script/eboot/data.json from e:2bccb0, メイクドール), as the text shows them."""
    import json
    items = json.loads((ROOT / "script" / "eboot" / "data.json").read_text("utf8"))
    i = next(k for k, e in enumerate(items) if e["id"] == "e:2bccb0")
    names = [e["en"] for e in items[i:i + 54]]
    assert items[i + 53]["jp"] == "トリックスター", "card name run moved"
    return names


def draw_card_names(a, table, n, size, face, stroke, center):
    rects, seen, items = table_rects(table, n), set(), []
    for r, name in zip(rects, card_names()):
        if tuple(r) not in seen:   # cards past the sheet's last name share one rect: draw it once
            seen.add(tuple(r))
            items.append((tuple(r), name, False))
    # the sheet holds only names, and their dakuten reach into the rows between cells: start from a clear sheet
    return draw_fixed(np.zeros_like(a), items, size, face=face, stroke=stroke, pad=0, center=center,
                      ink=ink_colours(a))


# card name sheets of file 2419: small (card select list), medium, large (variable-width rects); names left-aligned
# in the fixed cells as the Japanese was
asset("cards_small", 2419, "ptx", 0x110, (0, 0, 128, 351),
      lambda a, t: draw_card_names(a, 0x2c704e, 54, 10, "LiberationSans-Bold.ttf", 1, False))
asset("cards_medium", 2419, "ptx", 0x59b0, (0, 0, 160, 485),
      lambda a, t: draw_card_names(a, 0x2c9b2a, 54, 12, "LiberationSans-Bold.ttf", 1, False))
asset("cards_large", 2419, "ptx", 0xf380, (0, 0, 320, 420),
      lambda a, t: draw_card_names(a, 0x2c9ce2, 39, 19, "LiberationSans-BoldItalic.ttf", 2, True))

# EXTRA card page: the developer's English card names, drawn faded behind the card art (2433 PTX 50 and 51: two columns
# of 161x30 cells, 10 rows, cards 1-39 in order). Yggdra Union (USA) spellings outrank them (glossary), so the cells
# whose name differs from the text's are redrawn in the sheet's style: one gold, sentence case, serif, baseline y 22.
EX_CARD_ART = ["Make doll", "Necro gate", "Medusa eye", "Poison breath", "Gravity chaos", "Item break", "Steal",
               "Bloody claw", "Chariot", "Shield barrier", "Flame", "Blizzard", "Thunder bolt", "Banish",
               "Dragon killer", "Earthquake", "Mind change", "Revolution", "Jihad", "Sanctuary", "Refreshment",
               "Kiss of death", "Fortune", "Mirage", "Banshee's cry", "Ivy whip", "Sand storm", "Mantrap", "Rock fall",
               "Ace guard", "Genocide", "Reincarnation", "Revellion", "Oblivious dawn", "Coma karma", "Judgment zero",
               "Rauher", "Insanity", "Vise"]


def ex_card_redraws(first):
    """{cell: sentence-case English} for the 20 cells of the sheet starting at card `first` (0 or 20)."""
    out = {}
    for i, (old, en) in enumerate(zip(EX_CARD_ART[first:first + 20], card_names()[first:first + 20])):
        en = en[0] + en[1:].lower()
        if en != old:
            out[i] = en
    return out


def draw_ex_card_art(a, first):
    out, ink = a.copy(), tuple(int(v) for v in a[a[..., 3] == 255][0])
    for i, en in ex_card_redraws(first).items():
        x, y = 161 * (i // 10), 30 * (i % 10)
        out[y:y + 30, x:x + 161] = 0
        f = font("LiberationSerif-Regular.ttf", 30)
        w = f.getbbox(en, anchor="ls")[2] + 2
        im = Image.new("RGBA", (w, 30), (0, 0, 0, 0))
        ImageDraw.Draw(im).text((0, 22), en, font=f, fill=ink, anchor="ls")
        if w > 160:   # shortcut: squeeze, no smaller size; fine while the longest is "Angelic thunder"
            im = im.resize((160, 30), Image.LANCZOS)
        lay = np.array(im)
        lay[lay[..., 3] < 24] = 0
        out[y:y + 30, x:x + lay.shape[1]] = lay
    return out


def draw_ex_card_plate(a, text):
    """2430 PTGs 3-50: the faded card name the EXTRA card page shows (grey condensed sans, one alpha ramp, ink from x 1,
    baseline row 31). Sans Regular squeezed to the width the original "Make Doll" has at the same cap height."""
    f = font("LiberationSans-Regular.ttf", 42)
    xs = 114 / f.getbbox("Make Doll", anchor="ls")[2]
    w = int(f.getbbox(text, anchor="ls")[2] * xs) + 3
    im = Image.new("RGBA", (int(w / xs) + 4, a.shape[0]), (0, 0, 0, 0))
    ImageDraw.Draw(im).text((0, 32), text, font=f, fill=(147, 147, 148, 255), anchor="ls")
    lay = np.array(im.resize((w, a.shape[0]), Image.LANCZOS))
    lay[lay[..., 3] < 24] = 0
    out = np.zeros((a.shape[0], max(a.shape[1], w + 1), 4), np.uint8)
    out[:, 1:1 + w] = lay
    return out


# card plates whose art name differs from the text's (Yggdra Union USA spellings): PTG offset in 2430 -> card number
for _o, _c in ((0x11240, 1), (0x172a0, 13), (0x1e490, 29)):
    asset(f"ex_plate{_c}", 2430, "ptg", _o, (0, 0, 512, 512),
          lambda a, t, c=_c: draw_ex_card_plate(a, card_names()[c - 1]), resize=True)

asset("ex_card_art1", 2433, "ptx", 0x1a1330, (0, 0, 322, 300), lambda a, t: draw_ex_card_art(a, 0))
asset("ex_card_art2", 2433, "ptx", 0x1ae750, (0, 0, 322, 300), lambda a, t: draw_ex_card_art(a, 20))


# --- status screen (id 3) -------------------------------------------------------------------------------------------

MOVE_TYPES = {(0, 0): "mv_foot", (1, 1): "mv_slow", (0, 2): "mv_flying", (1, 2): "mv_dragon", (1, 3): "mv_aquatic",
              (0, 4): "mv_teleport", (1, 5): "mv_cavalry"}   # (column, row) of the 48x38 chip cells


def draw_move_types(a, t):
    """The move-type chips (left icon column of the status screen): dark letters at the foot of a light gradient
    chip, under the icon (rows 33-35: a light band, kept). English in the same dark."""
    out = a.copy()
    for c, r in MOVE_TYPES:   # each band row is flat (vertical gradient): fill it with its commonest colour
        for y in range(38 * r + 21, 38 * r + 33):
            row = out[y, 48 * c + 3:48 * c + 39]   # x 39: the chip's light right edge, kept
            light = row[row[:, :3].astype(int).sum(1) >= 500]   # dark letters can outnumber the background
            cols, n = np.unique(light, axis=0, return_counts=True)
            row[:] = cols[n.argmax()]
    dark = (1, 1, 1, 255)
    return draw_fixed(out, [((48 * c + 3, 38 * r + 22, 36, 11), t[k], False) for (c, r), k in MOVE_TYPES.items()],
                      11, stroke=0, ink=(dark, dark), clear=False, center=True)


asset("move_types", 3, "ptx", 0x13cbf0, (0, 0, 96, 304), draw_move_types)


def draw_status_labels(a, t):
    """Status bar sheet: 士気 on the pale yellow label left of the morale bar, 耐久度 before Atk…Hit… (the letters
    are cleared to the label's yellow, the English drawn in the old black)."""
    out = a.copy()
    yellow, dark = (255, 251, 149, 255), (1, 1, 1, 255)
    out[23:34, 50:86] = yellow   # the label's slanted right edge starts at x 86
    out[71:82, 175:204] = yellow   # Atk starts at x 205
    return draw_fixed(out, [((50, 23, 35, 11), t["hud_morale"], False), ((175, 71, 29, 11), t["st_durability"], False)],
                      12, stroke=0, ink=(dark, dark), clear=False)


asset("status_labels", 3, "ptx", 0x10ad90, (50, 23, 154, 59), draw_status_labels)


def draw_condition_chip(a, text, rect=(43, 61, 36, 11)):
    """使用条件 in white on a brown pill (2419 card data: x 41-79, rows 61-71, left of a white triangle)."""
    x, y, w, h = rect
    out = a.copy()
    out[y:y + h, x:x + w] = (77, 67, 53, 255)
    white = (255, 255, 255, 255)
    return draw_fixed(out, [(rect, text, False)], 10, stroke=0, ink=(white, white), clear=False, center=True)


asset("condition_chip", 2419, "ptx", 0x24570, (43, 61, 36, 11), lambda a, t: draw_condition_chip(a, t["cd_condition"]))
asset("card_select_chip", 2426, "ptx", 0x20, (286, 18, 33, 11),   # CARD SELECT header: the same chip, x 281-322
      lambda a, t: draw_condition_chip(a, t["cd_condition"], (286, 18, 33, 11)))
fixed("strategies", 0x3520, 176, 62, [((0, 0, 116, 15), "strat_left", False), ((0, 17, 29, 17), "strat_cards", False),
                                       ((31, 16, 15, 18), "cnt_cards", False)], 14, file=2426,
      ink=((255, 253, 247, 255), (8, 5, 6, 254)))   # あと<n>枚 -> "Left: <n>"
def draw_box_word(a, rect, text, size, fill=(1, 1, 1, 255)):
    """White word on a filled dark box (the box's inside refilled, then the English centred in it)."""
    x, y, w, h = rect
    out = a.copy()
    out[y:y + h, x:x + w] = fill
    white = (255, 255, 255, 255)
    return draw_fixed(out, [(rect, text, False)], size, face=REGULAR, stroke=0, ink=(white, white), clear=False,
                      center=True)


def draw_place(a, text, size=15):
    """Scenario-map place plate (2427): black bold with a white rim on clear, one line per \\n, centred lines, from
    x 0; squeezed (to 0.6, then a smaller font) to the texture's full width (the asset widens `used` to match)."""
    h, w = a.shape[:2]
    lines = text.split("\n")
    ink = ((2, 2, 2, 255), 1, (255, 255, 255, 255))
    while True:
        f = font("LiberationSans-Bold.ttf", size)
        lts = [layer_text(ln, f, *ink, lines=True) for ln in lines]
        xs = min(1.0, (w + 2) / max(lt.width for lt in lts))
        if xs >= 0.6 and sum(lt.height - 4 for lt in lts) <= h + 2:   # narrow beats small: 64-96 px textures
            break
        size -= 1
        assert size >= 9, f"{text!r}: no room in {w}x{h}"
    if xs < 1:
        lts = [layer_text(ln, f, *ink, xs, lines=True) for ln in lines]
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    wide, lh = max(lt.width for lt in lts) - 4, h // len(lts)
    for i, lt in enumerate(lts):
        top = (lt.height - lh) // 2
        im.alpha_composite(lt.crop((2, max(0, top), min(lt.width, w + 2), max(0, top) + min(lh, lt.height))),
                           (max(0, (wide - (lt.width - 4)) // 2), i * lh + max(0, -top)))
    res = np.array(im)
    res[res[..., 3] == 0] = 0
    return res


PLACES = {0xf5c0: "pl_funesto", 0xf9a0: "pl_virulento", 0xff40: "pl_inferia", 0x104e0: "pl_inbat",
          0x10a80: "pl_classicista", 0x111e0: "pl_bordolese", 0x11780: "pl_acquabau", 0x11d50: "pl_comune",
          0x12130: "pl_cannista", 0x126d0: "pl_fantasinia", 0x12c70: "pl_panoramica", 0x13210: "pl_stregatta",
          0x137b0: "pl_nymphetta", 0x13d50: "pl_concer", 0x142f0: "pl_chantier", 0x14ad0: "pl_egente",
          0x15070: "pl_ombra"}
for _o, _k in PLACES.items():
    asset(_k, 2427, "ptx", _o, (0, 0, 128, 40), lambda a, t, k=_k: draw_place(a, t[k]), used=True)
SCEN_TITLES = ["sc_magical_girl", "sc_visitor", "sc_sell_people", "sc_yandere", "sc_euforia", "sc_barrels", "sc_sea_dogs",
               "sc_episode0", "sc_reunion", "sc_blond_boy", "sc_ghost_ship", "sc_summer", "sc_bard", "sc_rotting_sea",
               "sc_rebellion", "sc_ghost_island"]   # two columns of 8 cells, 145x22 (EBOOT table 0x2bc862)
fixed("scen_titles", 0x80, 304, 176, [((145 * (i // 8), 22 * (i % 8), 145, 22), k, False) for i, k in enumerate(SCEN_TITLES)],
      16, file=2427, pad=0, ink=((255, 244, 203, 255), (22, 14, 8, 255)))
asset("difficulty", 2427, "ptx", 0xd220, (19, 13, 32, 15),   # 難易度 on a black box x 18-51 rows 12-28, right of an X icon
      lambda a, t: draw_box_word(a, (19, 13, 32, 15), t["sc_difficulty"], 12))
fixed("opt_battle", 0x60910, 384, 44, [((181, 0, 70, 21), "opt_normal", False), ((301, 0, 71, 21), "opt_hard", False),
                                       ((2, 22, 279, 21), "opt_battle_q", False)], 18, file=4, face=REGULAR, stroke=0)
asset("opt_help", 4, "ptx", 0x64ba0, (0, 0, 304, 96),   # a moon icon at x 266-282 stays
      lambda a, t: draw_fixed(draw_fixed(a, [((0, 1, 284, 11), t["opt_event_voice"], False),
                                             ((0, 14, 274, 11), t["opt_battle_voice"], False),
                                             ((0, 26, 264, 12), t["opt_tutorial"], False),
                                             ((0, 39, 256, 12), t["opt_boost"], False),
                                             ((0, 69, 245, 11), t["opt_install"], False)], 12, face=REGULAR,
                                        ink=((255, 247, 200, 255), (6, 6, 6, 252))),   # rim alpha 252: ink_colours skips it
                              [((83, 52, 85, 16), t["opt_to_title"], False), ((1, 81, 64, 15), t["opt_cancel"], False)],
                              17, face=REGULAR, ink=((255, 255, 255, 255), (6, 6, 6, 252))))
fixed("result_msgs", 0x6fd10, 256, 90, [((1, 63, 236, 14), "res_max_level", False), ((1, 77, 236, 13), "res_no_exp", False)],
      15, file=1581, face=REGULAR, stroke=0, ink=((255, 255, 255, 255),) * 2)   # plain white, no rim   # RESULT above and the black block at x 240-255 stay
for _n, _f, _o, _kw in (("equip_q", 2422, 0x20, dict(size=22)), ("scenario_q", 2427, 0xecc0, dict(size=14))):
    asset(_n, _f, "ptg", _o, (0, 0, 512, 512),
          lambda a, t, n=_n, kw=_kw: draw_label(a, t[n], "LiberationSans-Bold.ttf", dark_fill=False, **kw), resize=True)
SMALL_MOVES = ["mv_foot", "mv_slow", "mv_flying", "mv_aquatic", "mv_dragon", "mv_cavalry", "mv_teleport"]


def draw_small_moves(a, t):
    """2418 small move-type icons (32x30 cells, left column): the dark label under each icon, rows 20-29 of the cell
    (the icon ends above; x 30-31 is the next column's weapon), cleared and redrawn in the same dark."""
    out = a.copy()
    for k in range(len(SMALL_MOVES)):
        out[30 * k + 20:30 * k + 30, 0:30] = 0
    dark = (1, 0, 0, 255)
    return draw_fixed(out, [((0, 30 * k + 20, 30, 10), t[key], False) for k, key in enumerate(SMALL_MOVES)], 9,
                      stroke=0, ink=(dark, dark), clear=False, center=True)


asset("small_moves", 2418, "ptx", 0x229f0, (0, 0, 30, 240), draw_small_moves)


# --- EXTRA (file 2430) ------------------------------------------------------------------------------------------------

fixed("ex_buttons", 0x28f00, 320, 32,   # button bar words; rects from the per-page tables 0x2f89ea..0x2f8d0a (icons,
      # the colon at x 218 and the free x 252-319 stay)
      [((32, 0, 27, 16), "ex_select", False), ((59, 0, 27, 16), "ex_ok", False), ((86, 0, 80, 16), "ex_to_title", False),
       ((166, 0, 58, 16), "ex_replay", False), ((241, 0, 57, 16), "ex_play_drama", False),
       ((32, 16, 69, 16), "ex_switch_view", False), ((101, 16, 58, 16), "ex_play_voice", False),
       ((160, 16, 58, 16), "ex_play_bgm", False), ((225, 16, 27, 16), "ex_stop", False)], 13, file=2430, pad=0)
EX_SUBS = [((100, 1, 82, 14), "ex_sub_scenario", (183, 0, 12, 254)),   # x 96-99: the EXTRA logo's rect reaches it ((0, 44, 79, 12), "ex_sub_character", (1, 57, 152, 254)),
           ((88, 44, 60, 12), "ex_sub_card", (141, 2, 156, 253)), ((0, 57, 70, 13), "ex_sub_item", (2, 108, 81, 253)),
           ((88, 57, 59, 12), "ex_sub_music", (170, 140, 4, 252)), ((0, 70, 87, 12), "ex_sub_drama", (2, 182, 169, 254))]


def draw_ex_menu(a, t):
    """2430 +30b10: each menu row's subtitle in its own colour (bold italic, light rim; the colours are alpha 252-254,
    which ink_colours skips) and the locked-page message in black; EXTRA CONTENTS// stays."""
    rim = (255, 255, 255, 190)
    out = draw_fixed(a, [((0, 29, 186, 13), t["ex_locked"], False)], 12, pad=0, ink=((2, 2, 2, 254), rim))
    for r, k, c in EX_SUBS:
        out = draw_fixed(out, [(r, t[k], False)], 13, face="LiberationSans-BoldItalic.ttf", pad=0, ink=(c, rim))
    return out


asset("ex_menu", 2430, "ptx", 0x30b10, (0, 0, 192, 82), draw_ex_menu)
TABS = ["tab_info", "tab_data", "tab_heal", "tab_normal", "tab_angry", "tab_happy", "tab_grief", "tab_fierce", "tab_stunned",
        "tab_surprised", "tab_smile", "tab_dejected", "tab_glare", "tab_awake",   # left column, then the right one
        "tab_front", "tab_back", "tab_full", "tab_glutton", "tab_hmph", "tab_troubled", "tab_serious", "tab_sad", "tab_wanted",
        "tab_dead", "tab_pain", "tab_roar", "tab_cyborg"]
YELLOW = (255, 215, 1, 253)
fixed("ex_tabs", 0x2e7d0, 96, 182,   # page tab words (item, card, character pictures): yellow, no rim, centred in 34x13
      # cells (the Japanese is centred in them: the game's rects; not found in the EBOOT)
      [((34 * (i // 14), 13 * (i % 14), 34, 13), k, False) for i, k in enumerate(TABS)], 11, file=2430, pad=0, stroke=0,
      center=True, ink=(YELLOW, YELLOW))
EX_NAMES = ["exn_ishut", "exn_gangr", "exn_pinger", "exn_fiebee", "exn_ruru", "exn_anne", "exn_zazarland", "exn_kamuru",
            "exn_elisha", "exn_yggdra", "exn_minesota", "exn_pamela", "exn_locomoco", "exn_eater", "exn_raspberry",
            "exn_gloria"]


def draw_ex_names(a, t):
    """2430 +2aed0: 16 names, black with a white glow, two columns of 52x19 cells on a see-through white plate (x 0-103;
    x 104-127 is opaque black padding). No rect table found: same cells, centred. Screen not found yet."""
    out = a.copy()
    out[:, :104] = (255, 255, 255, 153)
    return draw_fixed(out, [((52 * (i % 2) + 1, 19 * (i // 2), 50, 19), t[k], True) for i, k in enumerate(EX_NAMES)],
                      10, clear=False, center=True, ink=((255, 255, 255, 204), (0, 0, 0, 255)))


asset("ex_names", 2430, "ptx", 0x2aed0, (0, 0, 104, 152), draw_ex_names)
fixed("ex_labels", 0x37bf0, 192, 120,   # card/item page headings; rects: EBOOT 0x2f8b9a.., 0x2f898a, 0x2f8d3a, 0x2f8992
      # minus each heading's red square (11 px); PLAYBACK, No., Track and the circles share the sheet and stay
      [((11, 50, 51, 11), "exl_base", False), ((73, 50, 62, 11), "exl_effect", False),
       ((11, 61, 86, 11), "exl_params", False), ((11, 73, 110, 11), "exl_morale", False),
       ((11, 84, 51, 11), "exl_condition", False), ((73, 84, 51, 11), "exl_equip", False)], 12, file=2430, pad=0,
      ink=((185, 0, 15, 255), (183, 0, 12, 95)))


# --- object list (asset file 1703; rects: EBOOT table 0x2c7374: 0-12 list rows, 14-26 English labels, 27-39 big
# names; each run in list order) --------------------------------------------------------------------------------------

OBJECTS = ["obj_catapult", "obj_cannon", "obj_bridge", "obj_gate_open", "obj_gate_closed", "obj_fence", "obj_village",
           "obj_city", "obj_fortress", "obj_item", "obj_ship", "obj_target"]   # then ?, kept
asset("obj_none", 1703, "ptx", 0x2add0, (0, 0, 128, 71),
      lambda a, t: draw_fixed(a, [((0, 24 * i, 128, 23), line, False) for i, line in enumerate(t["obj_none"].split("\n"))],
                              18, stroke=2))
asset("obj_list", 1703, "ptx", 0x2c070, (0, 0, 88, 288),
      lambda a, t: draw_fixed(a, [(tuple(r), t[k], False) for r, k in zip(table_rects(0x2c7374, 12), OBJECTS)], 18,
                              stroke=2, pad=0))
asset("obj_big", 1703, "ptx", 0x2fb50, (0, 0, 192, 220),   # maroon serif with a pale yellow rim; same rects: the
      # screen draws the word right after the English label, so a wider rect could run off the panel
      lambda a, t: draw_fixed(a, [(tuple(r), t[k], False) for r, k in zip(table_rects(0x2c7374 + 8 * 27, 12), OBJECTS)],
                              22, face="LiberationSerif-Bold.ttf", stroke=2, pad=0,
                              ink=((156, 0, 51, 255), (255, 251, 149, 255))))


# --- unit name plates (id 3 section 4: 87 large, then the small ones; the status screen's red banner shows a large
# one). JP read off the sheets in file order; English from script/eboot/names.json, else PLATE_EN -------------------

PLATES_BIG = """イシュト ピンガー ルルゥ ザザーランド エリーシャ ミネソタ・グレイ ロコモコ ラズベリー ガング フィービー
アンヌ・コーマック カミュル ユグドラ パメラ イータ ベルガス ブラックモア ローガン トレイシー ガルム メラニー ガリオレッド
アシュレイ アジョー・グラフォー ジゼル サイード キーラ エンリエッタ 名無し兵1 ルルゥMk-2 ベルガス改 シンフォニア 名無し兵5
名無し兵6 名無し兵7 海賊 黒い牙 屍兵 商団兵 皇国兵 皇国騎兵 連合兵 探検隊員 騎士団員 賞金稼ぎ 近衛兵 研究団員 子分 ゴロツキ
山賊 民兵 海の犬 悪霊 ゴーレム スケルトン 皇国兵長 連合兵長 支部船長 武装商人 見張り兵 お頭 手下 ナンパ男 砲撃手 海賊船 商団船
連合軍艦 皇国軍艦 戦艦グラム デリット号 ヴァルスィ号 リベラトレ号 戦艦バルトロ 戦艦マリアデ 戦艦ゼウス 戦艦バーチェ アンズ クロ
ローキン トローチ カリン カラメル コルベル アップル ケロッツ グロリア号 ？？？""".split()
PLATES_SMALL = """イシュト ピンガー ルルゥ ザザーランド エリーシャ ミネソタ ロコモコ ラズベリー ガング フィービー アンヌ カミュル
ユグドラ パメラ イータ ベルガス ブラックモア ローガン トレイシー ガルム メラニー ガリオレッド アシュレイ アジョー ジゼル サイード
キーラ エンリエッタ 名無し兵1 ルルゥMk-2 ベルガス改 シンフォニア 名無し兵5 名無し兵6 名無し兵7 海賊 黒い牙 屍兵 商団兵 皇国兵
皇国騎兵 連合兵 探検隊員 騎士団員 賞金稼ぎ 近衛兵 研究団員 子分 ゴロツキ 山賊 民兵 海の犬 悪霊 ゴーレム スケルトン 皇国兵長 連合兵長
支部船長 武装商人 見張り兵 謎の女 手下 ナンパ男 砲撃手 海賊船 商団船 連合軍艦 皇国軍艦 戦艦グラム デリット号 ヴァルスィ号
リベラトレ号 戦艦バルトロ 戦艦マリアデ 戦艦ゼウス 戦艦バーチェ アンズ クロ ローキン トローチ カリン カラメル コルベル アップル
ケロッツ 生贄少女 長老 海ゴブリン 運の悪い男 グロリア号 威圧感のある男 町人""".split()   # then 42 English class names, then 孤高の海賊
PLATE_EN = {"ミネソタ・グレイ": "Minesota Gray", "アンヌ・コーマック": "Anne Cormack", "アジョー・グラフォー": "Ajo-Grafor",
            "名無し兵1": "Nameless 1", "名無し兵5": "Nameless 5", "名無し兵6": "Nameless 6", "名無し兵7": "Nameless 7",
            "ルルゥMk-2": "Ruru Mk-II", "町人": "Townsperson", "孤高の海賊": "Lone Pirate"}
PLATE_DARK = (14, 12, 17, 255)


def plate_offsets():
    b = (FILES / "00003.bin").read_bytes()
    offs, i = [], b.find(b"PTG@", 0x17b580)
    while i != -1 and i < 0x1ab250:   # section 4 ends at 0x1ab250
        offs.append(i)
        i = b.find(b"PTG@", i + 4)
    assert len(offs) == 222, f"{len(offs)} name PTGs"
    return offs


def plate_en(jp):
    import json
    names = {}
    for e in json.loads((ROOT / "script" / "eboot" / "names.json").read_text("utf8")):
        names.setdefault(e["jp"], e["en"])
    return PLATE_EN.get(jp) or names[jp]


def plate_layer(text, big, size, xs):
    """Large: heavy italic, a white-to-gold gradient, a dark rim and drop shadow, tilted up ~6 degrees. Small: white
    italic, dark rim, a soft shadow."""
    f = font("LiberationSans-BoldItalic.ttf", size)
    body = layer_text(text, f, (255, 255, 255, 255), 2 if big else 1, PLATE_DARK, xs, lines=True)
    if big:   # multiply the white fill (and its blends into the rim) by the gradient
        px = np.array(body).astype(float)
        t = np.linspace(0, 1, px.shape[0])[:, None, None]
        grad = (1 - t) * np.array([255, 244, 214]) + t * np.array([243, 184, 58])
        px[..., :3] = px[..., :3] * grad / 255
        body = Image.fromarray(px.clip(0, 255).astype(np.uint8))
    d = 2 if big else 1
    im = Image.new("RGBA", (body.width + d, body.height + d), (0, 0, 0, 0))
    shadow = Image.new("RGBA", body.size, (24, 22, 31, 150))
    im.paste(shadow, (d, d), body.split()[3])
    im.alpha_composite(body)
    return im.rotate(6, Image.BICUBIC, expand=True) if big else im


def draw_plate(a, jp, big):
    """The plate cut to its ink, squeezed (to 0.75, then a smaller font) to fit the old height (40 / 16: the game's
    layouts) and a width cap, centred on a canvas of the old height."""
    text, hmax, wmax = plate_en(jp), a.shape[0], max(a.shape[1], 120 if big else 84)
    size = 22 if big else 12
    while True:
        xs = 1.0
        for _ in range(4):   # the tilt makes the width not quite linear in xs
            lt = plate_layer(text, big, size, xs)
            lt = lt.crop(lt.getbbox())
            if lt.width <= wmax:
                break
            xs *= wmax / lt.width * 0.99
        if xs >= 0.75 and lt.width <= wmax and lt.height <= hmax:
            break
        size -= 1
        assert size >= 8, f"{text!r}: no room in {wmax}x{hmax}"
    w = lt.width + 2 + lt.width % 2
    im = Image.new("RGBA", (w, hmax), (0, 0, 0, 0))
    im.alpha_composite(lt, ((w - lt.width) // 2, (hmax - lt.height) // 2))
    out = np.array(im)
    out[out[..., 3] == 0] = (255, 255, 255, 0)
    return out


for _i, _o in enumerate(plate_offsets()):
    _big = _i < len(PLATES_BIG)
    _j = _i - len(PLATES_BIG)
    if not _big and _j >= len(PLATES_SMALL) and _i != 221:
        continue   # English class names: kept
    _jp = PLATES_BIG[_i] if _big else PLATES_SMALL[_j] if _j < len(PLATES_SMALL) else "孤高の海賊"
    asset(f"plate{_i:03d}", 3, "ptg", _o, (0, 0, 512, 512), lambda a, t, jp=_jp, big=_big: draw_plate(a, jp, big),
          resize=True, section=4)


# --- status popups (id 3 section 16: 250x40 PTGs, white italic, right-aligned over the unit) ---------------------

POPUPS = ["pop_morale_damage", "pop_morale_restored", "pop_ailment_cured", "pop_drowsy", "pop_all_up", "pop_gen_up",
          "pop_atk_up", "pop_tec_up", "pop_luk_up", "pop_gen_down", "pop_atk_down", "pop_tec_down", "pop_luk_down",
          "pop_rise_again"]   # PTP entries in file order from 0x4a6960


def draw_popup(a, text):
    """White bold italic with a black rim and a 2 px black drop shadow, right-aligned at the old ink's right edge
    (x 248) on the same 250x40 canvas, squeezed (to 0.75, then a smaller font) to fit."""
    h, w = a.shape[:2]
    size = 32
    while True:
        f = font("LiberationSans-BoldItalic.ttf", size)
        lt = layer_text(text, f, (255, 255, 255, 255), 2, (1, 1, 1, 255))
        xs = min(1.0, (w - 6) / lt.width)
        if xs >= 0.75 and lt.height + 2 <= h + 4:
            break
        size -= 1
    if xs < 1:
        lt = layer_text(text, f, (255, 255, 255, 255), 2, (1, 1, 1, 255), xs)
    shadow = Image.new("RGBA", lt.size, (1, 1, 1, 255))
    shadow.putalpha(lt.split()[3])
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    x, y = w - 2 - lt.width, (h - 2 - lt.height) // 2
    im.alpha_composite(shadow, (x + 2, y + 2))
    im.alpha_composite(lt, (x, y))
    return np.array(im)


for _k, _o in zip(POPUPS, (0x4a6960, 0x4a76b0, 0x4a81f0, 0x4a9600, 0x4aa0d0, 0x4ab100, 0x4abf60, 0x4acd80, 0x4adb80,
                           0x4ae9b0, 0x4af960, 0x4b08d0, 0x4b1840, 0x4b27c0)):
    asset(_k, 3, "ptg", _o, (0, 0, 250, 40), lambda a, t, k=_k: draw_popup(a, t[k]), resize=True, section=16)


# --- legend panels (id 3 section 14 PTGs on a see-through white panel: symbol + "…" kept, word redrawn) -----------

PANEL = (255, 255, 255, 230)
PILL = (156, 24, 205, 255)


def draw_legend(a, rows, back, t):
    """rows: (y0, y1, text key, ink); the word right of the "…" (x 41-124) cleared to the panel and redrawn there.
    back: the y of the purple "(X) 戻る" pill's text rows, or None: 戻る (x 49-71) is cleared by copying the pill's
    clean column x 100 across x 46-104, then "Back" in white with a purple rim."""
    out = a.copy()
    for y0, y1, _, _ in rows:
        out[y0:y1 + 1, 39:125] = PANEL   # the word's ink starts at x 39-40, the "…" ends at 38
    for y0, y1, k, ink in rows:
        out = draw_fixed(out, [((42, y0, 82, y1 - y0 + 1), t[k], True)], 15, stroke=0, ink=(PANEL, ink), clear=False)
    if back is not None:
        out[back - 6:back + 17, 46:105] = out[back - 6:back + 17, 100:101]
        out = draw_fixed(out, [((49, back, 54, 11), t["btn_back"], False)], 12, ink=((255, 255, 255, 255), PILL),
                         clear=False)
    return out


asset("legend_units", 3, "ptg", 0x400c40, (0, 0, 129, 72),
      lambda a, t: draw_legend(a, [(22, 38, "leg_ally", (52, 65, 165, 255)), (49, 65, "leg_enemy", (205, 63, 63, 255))],
                               None, t), section=14)
asset("legend_terrain", 3, "ptg", 0x401e20, (0, 0, 129, 128),
      lambda a, t: draw_legend(a, [(y, y + 17, k, (2, 2, 2, 255)) for y, k in
                                   ((1, "leg_strong"), (23, "leg_normal"), (44, "leg_weak"), (65, "leg_impassable"),
                                    (86, "leg_pass_only"))], 113, t), section=14)
asset("legend_odds", 3, "ptg", 0x4040d0, (0, 0, 129, 88),
      lambda a, t: draw_legend(a, [(y, y + 17, k, (3, 3, 3, 255)) for y, k in
                                   ((2, "leg_advantage"), (23, "leg_even"), (44, "leg_disadvantage"))], 71, t), section=14)


# --- snow terrain chips (id 3 section 14: big 73x48, small 37x24; white serif kanji with a black rim, bottom left) --

def draw_chip(a, text, big, b3=None):
    """The kanji cleared (big: the same pixels of 0x400080, the same tile art without a label; small: inpainted, no
    clean copy exists), then the English bottom-left in two lines, white serif with a black rim."""
    out = a.copy()
    if big:
        out[14:48, 3:52] = ptx.ptg((FILES / "00003.bin").read_bytes(), 0x400080)[14:48, 3:52]
    else:
        box = np.zeros(a.shape[:2], bool)
        box[2:24, 1:27] = True
        px = a[..., :3].astype(int)
        mask = box & (a[..., 3] > 0) & ((px.min(2) > 170) | (px.max(2) < 60))
        out = inpaint(out, grow(mask, 1))
    size, x0, rim = (13, 3, 2) if big else (8, 1, 1)
    f = font("LiberationSerif-Bold.ttf" if big else "LiberationSans-Bold.ttf", size)   # serif blurs at 8 px
    lines = text.split(" ", 1) if " " in text else [text]
    im = Image.fromarray(out)
    y = a.shape[0] - 2 - len(lines) * (size - 1) - rim
    for ln in lines:
        lt = layer_text(ln, f, (255, 255, 255, 255), rim, (0, 0, 0, 255), min(1.0, (a.shape[1] - x0) / (f.getlength(ln) + 6)),
                        lines=True)
        im.alpha_composite(lt, (x0, y - 2 - f.getbbox("Hgy" + ln, stroke_width=rim)[1] + f.getbbox("H")[1]))
        y += size - 1
    return np.array(im)


for _n, _o, _big, _k in (("chip_snow_road", 0x3f9a20, True, "chip_snow_road"),
                         ("chip_snowfield", 0x3fa5f0, True, "chip_snowfield"),
                         ("chip_snow_road_s", 0x44e910, False, "chip_snow_road"),
                         ("chip_snowfield_s", 0x44ed90, False, "chip_snowfield"),
                         ("chip_deck_s", 0x44fa10, False, "chip_deck")):
    asset(_n, 3, "ptg", _o, (0, 0, 73, 48), lambda a, t, k=_k, big=_big: draw_chip(a, t[k], big), resize=True,
          section=14)   # resize: the English reaches pixels the trimmed atlas has no sprite for


# --- terrain / object / weapon words (id 3 PTX +3e8e70: full map legend, weapon list rows) -------------------------

GLYPH_WORDS = {0: "ter_road", 1: "ter_bridge", 2: "ter_plains", 3: "ter_wasteland", 4: "ter_forest", 5: "ter_desert",
               6: "ter_swamp", 7: "ter_waterside", 8: "ter_ice", 9: "ter_village", 10: "ter_city", 11: "ter_fortress",
               14: "ter_alley", 15: "ter_street", 16: "obj_ship", 18: "ter_beach", 19: "ter_ruins", 20: "ter_sea",
               23: "obj_catapult", 24: "obj_cannon", 26: "obj_gate_open", 27: "obj_gate_closed", 28: "obj_fence",
               32: "obj_treasure", 34: "obj_goal"}   # table 0x2c6a02 x36; 12-13 blank cells, 35 "?" kept
WEAPONS = ["wpn_sword", "wpn_spear", "wpn_axe", "wpn_gun", "wpn_staff", "wpn_club", "wpn_scythe", None, "wpn_harp"]


def draw_pack_shared(a, rects, redraw, size, **kw):
    """draw_pack where several table entries share one rect: the first entry with a word stands for all of them (one
    piece), the others get its new rect."""
    first = {}
    for i, r in enumerate(rects):
        first.setdefault(tuple(r), i)
    rep = {i: first[tuple(rects[i])] for i in range(len(rects))}
    words = {rep[i]: t for i, t in redraw.items()}
    dummy = [r if rep[i] == i or rep[i] not in words else (0, 0, 0, 0) for i, r in enumerate(rects)]
    img, new = draw_pack(a, dummy, words, size, **kw)
    return img, [new[rep[i]] if rep[i] in words else new[i] for i in range(len(rects))]


def draw_glyph_words(a, t):
    rects = table_rects(0x2c6a02, 36) + table_rects(0x2c6b4a, 9)
    a = a.copy()
    a[:, 72:] = 0   # header +used = 72: x 72-95 is unused storage (palette 0, black), free for the longer words
    split = {"Wasteland": "Waste- land", "Waterside": "Water- side"}   # two hyphenated lines: one line won't fit 26 px
    redraw = {i: split.get(t[k], t[k]) for i, k in GLYPH_WORDS.items()}
    redraw.update({36 + i: t[k] for i, k in enumerate(WEAPONS) if k})
    # full map legend: a word sits between two swatches ~26 px apart; weapon list: 24 px before the portraits
    return draw_pack_shared(a, rects, redraw, 9, wmax={i: 24 if i >= 36 else 26 for i in redraw}, smin=7)


asset("glyph_words", 3, "ptx", 0x3e8e70, (0, 0, 96, 272), draw_glyph_words, table=[(0x2c6a02, 36), (0x2c6b4a, 9)],
      section=14)


# --- tutorial plates (file 2023: 45 PTGs 320x150/152, a title top right + yellow/white callouts; +11b660 the header) -
# gfx/tutorial.tsv: plate offset, rect (x,y,w,h, or "title"), align l/c/r (+w: only white lettering is old text, +y:
# only yellow; +s: serif), Japanese, English ("\n" breaks lines).
# A callout rect is loose: the old lettering inside it (light fill + the dark rim around it) is found and inpainted,
# and the English drawn over where it was, using the rect's width if it needs it.

def tutorial_tsv():
    out = {}
    for ln in (GFX / "tutorial.tsv").read_text("utf8").splitlines()[1:]:
        if ln.strip():
            off, rect, align, _jp, en = (ln.split("\t") + [""])[:5]   # no English: cleared only
            out.setdefault(int(off, 16), []).append((rect, align, en.replace("\\n", "\n")))
    return out


def _tut_title(out, text, size=16):
    """Clear the title (the run of white/blue lettering in rows 0-23 ending nearest the right edge, with its black drop
    shadow) and draw the English right-aligned to the same edge: white bold italic, blue rim, black shadow."""
    top = out[:24]
    px = top[..., :3].astype(int)
    m = (top[..., 3] > 0) & ((px[..., 2] > px[..., 0] + 60) | (px.min(2) > 200))
    cols = np.flatnonzero(m.any(0))
    x1 = x0 = cols[-1]
    for c in cols[::-1]:
        if x0 - c > 12:
            break
        x0 = c
    rows = np.flatnonzero(m[:, x0:x1 + 1].any(1))
    y0, y1 = rows[0], rows[-1]
    blue = px[m & (px[..., 2] > px[..., 0] + 60) & (top[..., 3] >= 250)]   # some plates' rim is alpha 253
    vals, counts = np.unique(blue, axis=0, return_counts=True)
    rim = tuple(int(v) for v in vals[counts.argmax()]) + (255,)
    box = np.zeros(out.shape[:2], bool)
    box[max(0, y0 - 1):min(24, y1 + 4), max(0, x0 - 2):min(out.shape[1], x1 + 4)] = True
    p = out[..., :3].astype(int)
    old = box & (out[..., 3] > 0) & ((p[..., 2] > p[..., 0] + 40) | (p.min(2) > 180) | (p.max(2) < 70) | (out[..., 3] < 255))
    out[old] = 0
    f = font("LiberationSans-BoldItalic.ttf", size)
    lt = layer_text(text, f, (255, 255, 255, 255), 2, rim, lines=True)
    room = x1 - 6   # never run into the left edge
    if lt.width > room:
        lt = layer_text(text, f, (255, 255, 255, 255), 2, rim, room / lt.width, lines=True)
    sh = np.array(lt)
    sh[..., :3] = 0
    sh[..., 3] = np.where(sh[..., 3] > 100, 255, 0)
    im = Image.fromarray(out)
    x, y = x1 - 1 - lt.width, (y0 + y1) // 2 - lt.height // 2   # the shadow ends where the old ink did
    im.alpha_composite(Image.fromarray(sh), (x + 2, y + 2))
    im.alpha_composite(lt, (x, y))
    return np.array(im)


def _tut_callout(out, rect, align, text):
    x, y, w, h = rect
    sub = out[y:y + h, x:x + w]
    px, al = sub[..., :3].astype(int), sub[..., 3]
    yellow = (al > 200) & (px[..., 0] > 190) & (px[..., 1] > 140) & (px[..., 2] < 150) & (px[..., 0] - px[..., 2] > 70)
    serif = "s" in align   # the snow plates' Mincho: grey-to-white fill, a thicker black rim
    white = (al > 200) & ((px.min(2) > 140) & (px.max(2) - px.min(2) < 40) if serif else (px.min(2) > 215))
    if "w" in align:   # white lettering on a yellow banner: keep the banner
        yellow = yellow & False
    elif "y" in align:
        white = white & False
    face = "LiberationSerif-Bold.ttf" if serif else "LiberationSans-Bold.ttf"
    align = align[0]
    fill = yellow | white
    dark = (al > 0) & ((px.max(2) < 90) | (al < 255))
    m = grow(fill | (dark & grow(fill, 5 if serif else 3)), 1)
    if not m.any():
        raise ValueError(f"tutorial callout {rect}: no lettering found")
    ink = px[yellow if yellow.sum() > white.sum() else white]
    vals, counts = np.unique(ink, axis=0, return_counts=True)
    fillc = tuple(int(v) for v in vals[counts.argmax()]) + (255,)
    ys, xs = np.nonzero(m)
    by0, by1, bx0, bx1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
    # inpaint in a margin around the rect, then snap alpha: over the clear background the hole stays clear
    mx0, my0 = max(0, x - 4), max(0, y - 4)
    crop = out[my0:y + h + 4, mx0:x + w + 4]
    cm = np.zeros(crop.shape[:2], bool)
    cm[y - my0:y - my0 + h, x - mx0:x - mx0 + w] = m
    fixed = inpaint(crop, cm)
    fixed[cm & (fixed[..., 3] < 128)] = 0
    fixed[cm & (fixed[..., 3] >= 128), 3] = 255
    crop[:] = fixed
    if not text:   # cleared only (a Japanese name the English tag beside it already gives)
        return out
    lines = text.split("\n")
    # room from where the old ink starts (l) or ends (r) to the rect's far edge; the layer has 2 px padding each side
    room = w - bx0 if align == "l" else bx1 if align == "r" else w
    for s in range(15, 7, -1):   # the Japanese is ~14 px; 15 px English has about the same x-height to cap height
        f = font(face, s)
        lts = [layer_text(ln, f, fillc, 2, (0, 0, 0, 255), lines=True) for ln in lines]
        lh = s + 2
        tall = lh * len(lines) + 4
        wide = max(lt.width for lt in lts)
        if tall <= max(by1 - by0, h) + 4 and (wide - 4) * 0.8 <= room:
            break
    xs_ = min(1.0, (room + 4) / wide)
    if xs_ < 1:
        lts = [layer_text(ln, f, fillc, 2, (0, 0, 0, 255), xs_, lines=True) for ln in lines]
    im = Image.fromarray(out)
    cy = y + (by0 + by1) // 2
    ty = max(0, min(out.shape[0] - tall + 2, cy - tall // 2))
    for i, lt in enumerate(lts):
        if align == "l":
            lx = x + bx0 - 2
        elif align == "r":
            lx = x + bx1 + 2 - lt.width
        else:
            lx = x + (bx0 + bx1) // 2 - lt.width // 2
        lx = max(0, min(out.shape[1] - lt.width, lx))
        im.alpha_composite(lt, (lx, ty + i * lh))
    return np.array(im)


def _tut_pill(out, text):
    """The header's blue pill: チュートリアル (x 122-200) cleared by copying the clean column x 120, white English."""
    out[112:132, 121:203] = out[112:132, 120:121]
    im = Image.fromarray(out)
    lt = layer_text(text, font("LiberationSans-Bold.ttf", 11), (255, 255, 255, 255), lines=True)
    im.alpha_composite(lt, (161 - lt.width // 2, 122 - lt.height // 2))
    return np.array(im)


def draw_tutorial(a, items):
    out = a.copy()
    for rect, align, text in items:
        if rect.startswith("title"):   # title[:font size]
            out = _tut_title(out, text, int(rect[6:] or 16))
        elif rect == "pill":
            out = _tut_pill(out, text)
        else:
            out = _tut_callout(out, tuple(map(int, rect.split(","))), align, text)
    out[out[..., 3] == 0] = 0
    return out


if (GFX / "tutorial.tsv").exists():
    for _o, _items in tutorial_tsv().items():
        asset(f"tut{_o:06x}", 2023, "ptg", _o, (0, 0, 320, 152), lambda a, t, it=_items: draw_tutorial(a, it),
              resize=_o != 0xd21b0, trim=True)   # resize: the callouts reach texels the old atlas has no sprite for; d21b0
        # has two palettes (a resize keeps piece 0's), so it is written into its old sprites


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
