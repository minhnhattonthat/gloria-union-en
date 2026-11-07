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
SAVEPTR = 0x8804000 + 0x2B75F0   # RAM: pointer to the save/work struct


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
            self.ws.call('cpu.runUntilTime', us=target)
            ev = self.ws.wait('cpu.stepping')
            r = self.regs()
            fn = self.hooks.get(r['pc'])
            if fn: fn(self, r)

    def rd(self, addr, size): return self.ws.mem(addr, size)

    def rd32(self, addr): return struct.unpack('<I', self.rd(addr, 4))[0]

    def wr(self, addr, data):
        self.ws.call('memory.write', address=addr, base64=base64.b64encode(data).decode())

    def wr32(self, addr, v): self.wr(addr, struct.pack('<I', v))

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

    def new_game(self):
        """Cold boot to the end of the prologue is about 8500 frames; Start or Circle skips nothing in it."""
        self.run(2700); self.tap('circle', 6, 120)

    def tap(self, keys, hold=6, gap=30):
        self.press(set(keys.split('+'))); self.run(hold); self.press(set()); self.run(gap)
