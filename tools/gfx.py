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
    return ptx.decode(bytes(b), ptx.parse(b, a["off"])) if a["kind"] == "ptx" else ptx.ptg(bytes(b), a["off"])


def write(b, a, img):
    """Write the RGBA array img (palette colours only) into bytearray b; fail if it can't be shown exactly."""
    if a["kind"] == "ptx":
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


def original(name):
    a = ASSETS[name]
    return read((FILES / f"{a['file']:05d}.bin").read_bytes(), a)


def apply(repl):
    """build.py: write every gfx/*.png into its file; repl is {file id: bytes} and is updated in place."""
    for name, a in ASSETS.items():
        png = GFX / f"{name}.png"
        if not png.exists():
            continue
        i = a["file"]
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


# --- registry ---------------------------------------------------------------------------------------------------

ASSETS = {}


def asset(name, file, kind, off, rect, draw):
    ASSETS[name] = dict(name=name, file=file, kind=kind, off=off, rect=rect, draw=draw)


for _n in range(1, 8):
    asset(f"card{_n}", 1581 + _n, "ptg", 0x20, (0, 0, 440, 66), lambda a, t, n=_n: draw_card(a, n, t[f"card{n}"]))
asset("gameover", 1758, "ptx", 0x3310, (0, 0, 272, 54), lambda a, t: draw_gameover_title(a, t["gameover"]))
asset("gameover_menu", 1758, "ptx", 0x16b0, (0, 0, 256, 16),
      lambda a, t: draw_gameover_menu(a, t["gameover_retry"], t["gameover_title"]))


def gen(names=None):
    t = text_tsv()
    GFX.mkdir(exist_ok=True)
    for name in names or ASSETS:
        a = ASSETS[name]
        b = (FILES / f"{a['file']:05d}.bin").read_bytes()
        orig = read(b, a)
        new = quantize(a["draw"](orig, t), palette(b, a))
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
