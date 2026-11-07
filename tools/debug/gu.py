"""Gloria Union debug driver: PPSSPPHeadless session with RAM reads/writes and breakpoint callbacks.

    from gu import Game
    g = Game('rom/Gloria Union (Japan).iso', 'work/qa/x'); g.hook(0x191680, fn); g.run(600); g.shot('a.png')

Addresses given to hook() are EBOOT vaddrs (docs/re/engine.md); g.base is added.
"""
import base64, json, os, shutil, struct, sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from skill import SKILL
sys.path.insert(0, os.path.join(SKILL, 'scripts'))
import psp  # noqa: E402

ORIG = 'rom/Gloria Union (Japan).iso'
LOADSTAGE = 0xADC7C        # vaddr: void loadStage(stage, ?, ?)
GETFILEINFO = 0x191680     # vaddr: criFs lookup by id, a1 = CPK id
SAVEPTR = 0x8804000 + 0x2B75F0   # RAM: pointer to the save/work struct
MODE = 0x8B851BC           # RAM: top-level mode (docs/re/engine.md)
CARD = 0x8B8C218           # RAM: Card Select work (seg1 +0x87C90)


class _Json:
    """The game printf()s Shift-JIS, which reaches the debugger as a `log` event that is not valid UTF-8."""
    dumps = staticmethod(json.dumps)

    @staticmethod
    def loads(data):
        try: return json.loads(data.decode('utf-8', 'replace'))
        except ValueError: return {'event': 'garbled'}


psp.json = _Json


class Game(psp.Run):
    def __init__(self, iso=ORIG, out='work/qa/gu', state=None):
        ms = os.path.abspath(os.path.join(out, 'memstick'))
        shutil.rmtree(ms, ignore_errors=True)
        super().__init__(psp.find_emu(None), iso, out, state, memstick=ms)
        self.ws.s.settimeout(120)
        self.hooks = {}
        self.base = self.ws.call('cpu.status')['us']   # psp.Run's clock base
        self.load = self.ws.call('hle.module.list')['modules'][-1]['address']   # the EBOOT module; 0x8804000
        self.f = 0

    def hook(self, vaddr, fn):
        a = self.load + vaddr
        self.hooks[a] = fn
        self.ws.call('cpu.breakpoint.add', address=a, enabled=True)

    def regs(self):
        cats = self.ws.call('cpu.getAllRegs')['categories']
        r = cats[0]
        return dict(zip(r['registerNames'], r['uintValues']))

    def setreg(self, name, v):
        self.ws.call('cpu.setReg', name=name, value=v)

    def run(self, frames):
        """Run FRAMES frames, calling hooks as breakpoints hit."""
        self.f += frames
        target = self.base + round(self.f * psp.FRAME_US)
        while True:
            us = self.ws.call('cpu.status')['us']
            if us >= target - 100: return
            try: self.ws.call('cpu.runUntilTime', us=target)
            except RuntimeError: continue   # the clock moved past target after a state load
            ev = self.ws.wait('cpu.stepping')
            r = self.regs()
            fn = self.hooks.get(r['pc'])
            if fn: fn(self, r)

    def rd(self, addr, size): return self.ws.mem(addr, size)

    def rd32(self, addr): return struct.unpack('<I', self.rd(addr, 4))[0]

    def wr(self, addr, data):
        self.ws.call('memory.write', address=addr, base64=base64.b64encode(data).decode())

    def wr32(self, addr, v): self.wr(addr, struct.pack('<I', v))

    def watch_files(self):
        """Record CPK ids as the game opens them, in self.files."""
        self.files = []
        self.hook(GETFILEINFO, lambda g, r: g.files.append(r['a1'] & 0xffff))

    def until(self, pred, limit=3000, key='circle'):
        """Mash KEY (None: just wait) until PRED(self) or LIMIT frames; returns whether PRED held."""
        end = self.f + limit
        while self.f < end:
            if pred(self): return True
            if key: self.tap(key, 6, 54)
            else: self.run(30)
        return pred(self)

    def mode(self): return self.rd32(MODE)

    def save(self): return self.rd32(SAVEPTR)

    def setflag(self, i, v):
        """Story flag I (see 0x5408: < 0x61 at save+0x20, 0x61-0x7F at +0x81, 0x80-0x8A at +0xA0)."""
        off = 0x20 + i if i < 0x61 else 0x81 + i - 0x61 if i < 0x80 else 0xA0 + i - 0x80
        self.wr(self.save() + off, bytes([v]))

    def warp(self, stage):
        """After the next loadStage(0, ...) (the one New Game makes), load STAGE instead."""
        def ls(g, r):
            if r['a0'] != 0: return
            g.setreg('a0', stage)
            # scenario select lists options whose flag 0x21+i is 1 or 3; without one it reads a null entry
            for i in range(17): g.setflag(0x21 + i, 1)
        self.hook(LOADSTAGE, ls)

    def title(self):
        self.run(2700)   # logos and opening movie; mode 2 is set well before the menu takes input

    def new_game(self):
        """GAME START from the title; the prologue scrolls on its own to about frame 8450, then loadStage(0)."""
        self.title(); self.tap('circle', 6, 120)

    def pick_cards(self):
        """Card Select (mode 26): take selectable cards in list order until the game moves on."""
        order = self.rd(CARD + 0x5C8, 41)
        rows = [i for i, o in enumerate(order) if self.rd(CARD + 0x20 + o * 0x18, 1)[0] & 1]
        for t in rows:
            for _ in range(60):
                cur = self.rd(CARD + 4, 1)[0]
                if cur == t: break
                self.tap('down' if t - cur >= 2 else 'right', 6, 24)
            self.tap('circle', 6, 40)
            if self.rd(CARD + 1, 1)[0] != 1: return True   # state 0x67: the game counted enough cards
        return False

    def need(self, mode, limit=600, key=None):
        if not self.until(lambda g: g.mode() == mode, limit, key): raise RuntimeError(f'no mode {mode}, at {self.mode()}')

    def to_select(self):
        """From a warp: story up to Character Select."""
        self.need(20, 24000, 'circle')
        self.run(300)   # mode 20 is set before the screen fades in and takes input

    def to_ready(self):
        self.to_select()
        self.tap('down', 6, 90); self.tap('circle', 6, 90)
        self.need(26); self.run(120)
        if not self.pick_cards(): raise RuntimeError('too few selectable cards')
        self.need(27); self.run(120)

    def to_field(self):
        """Ready, then the opening script up to the first player turn."""
        self.to_ready()
        self.tap('circle', 6, 60)
        self.need(15, 24000, 'circle'); self.run(120)

    def to_union(self):
        """Stage 1 only: walk the first unit to an enemy, sit through the tutorial, open the Union screen (mode 33)."""
        for k in ('circle', 'right', 'up', 'up', 'up', 'up', 'circle'): self.tap(k, 6, 40)
        self.need(7, 120, None)
        self.need(15, 4000, 'circle')
        # Square opens the Union only with no unit in hand, and Circle toggles that, so alternate until it opens
        for i in range(8):
            self.tap('square' if i % 2 else 'circle', 6, 60)
            if self.mode() == 33: break
        self.need(33)
        self.run(120)

    def end_turn(self, stop=None):
        """Field: end the turn, ride out the enemy phase (it runs in mode 15, its fights need Circle), reach the next
        Tactics Card pick. Returns False early if STOP(self) holds, for catching something in the enemy phase."""
        for k in ('cross', 'ltrigger', 'circle', 'circle'): self.tap(k, 6, 60)
        for _ in range(400):
            if stop and stop(self): return False
            m = self.mode()
            if m == 32: break
            if m in (33, 35, 36): self.tap('circle', 6, 24)
            else: self.run(30)
        for _ in range(30):
            if self.mode() == 15: break
            self.tap('circle', 6, 54)
        self.run(120)
        return True

    def outcome(self, v):
        """Field to a stage result: flag 0xA is read by mode 7 (2 game over, 3 next stage, 4 clear, 5 chapter, 8 credits)."""
        self.setflag(0xA, v); self.wr32(MODE, 7)

    def tap(self, keys, hold=6, gap=30):
        self.press(set(keys.split('+'))); self.run(hold); self.press(set()); self.run(gap)
