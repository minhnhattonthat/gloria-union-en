"""Runs of (u,v,w,h) s16 rects in the EBOOT, each fitting a W x H sheet with h in [hmin,hmax] (word-sheet rect tables;
printed addresses are vaddrs, gfx.table_rects form): python tools/find_rects.py W H hmin hmax minrun"""
import sys
from pathlib import Path
import numpy as np
d = (Path(__file__).resolve().parents[1] / "work" / "re" / "eboot.elf").read_bytes()
W, H, hmin, hmax, minrun = map(int, sys.argv[1:6])
a = np.frombuffer(d[: len(d) // 2 * 2], "<i2")
for phase in range(4):
    r = a[phase: phase + (len(a) - phase) // 4 * 4].reshape(-1, 4).astype(int)
    u, v, w, h = r.T
    ok = (u >= 0) & (v >= 0) & (w >= 8) & (h >= hmin) & (h <= hmax) & (u + w <= W) & (v + h <= H)
    i = 0
    while i < len(ok):
        if ok[i]:
            j = i
            while j < len(ok) and ok[j]: j += 1
            run = r[i:j]
            if j - i >= minrun and len(set(run[:, 1])) > 1 and len(set(run[:, 0])) > 1:
                print(hex((phase + 4 * i) * 2 - 0xA0), j - i, [tuple(x) for x in run.tolist()][:40])
            i = j
        else:
            i += 1
