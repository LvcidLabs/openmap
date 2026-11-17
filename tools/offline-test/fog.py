"""The fog (Stitch.lua's Shade.Fog, Data/Forever/Fog.lua, Media/Textures/Forever/MapFog/, render.py --bake-fog): every
piece's file there at its size; whichever of a zone's pieces are unexplored, their shares never come to more than
the one shade (they don't stack darker where pieces overlap); and Shade.Fog.Show draws only the unexplored pieces',
each over its piece's rectangle: python -P tools/offline-test/fog.py."""
from pathlib import Path
import random
import re
import unittest

import numpy as np
from PIL import Image
from lupa.lua51 import LuaRuntime


ADDON = Path(__file__).resolve().parents[2] / "OpenMap"
STITCH = ADDON / "Map" / "Stitch.lua"
FOG = ADDON / "Data" / "Forever" / "Fog.lua"
FILES = ADDON / "Media" / "Textures" / "Forever" / "MapFog"
SHADE = 0.62                    # (Stitch.lua's UNDISCOVERED alpha: render.py's FOG_S)


def zones():
    """{ mapID: [ (w, h, x, y, n, cw, ch, fw, fh) ] } from Fog.lua"""
    out = {}
    for mid, body in re.findall(r"\n\t\[(\d+)\] = \{ (.*) \},   --", FOG.read_text(encoding="utf-8")):
        out[int(mid)] = [tuple(int(v) for v in e) for e in re.findall(
            r'\["(\d+):(\d+):(\d+):(\d+)"\] = \{ (\d+), (\d+), (\d+), (\d+), (\d+) \}', body)]
    return out


def mask(mid, e):
    """a piece's share on its rectangle (art px), as the client draws it"""
    w, h, x, y, n, cw, ch, fw, fh = e
    with Image.open(FILES / ("%d_%d.blp" % (mid, n))) as im:
        a = np.asarray(im.convert("RGBA"))[:ch, :cw, 3]
    return np.asarray(Image.fromarray(a).resize((w, h), Image.BILINEAR)).astype(np.float32) / 255


class FileTests(unittest.TestCase):
    def test_every_piece_has_its_file_at_its_size(self):
        z = zones()
        self.assertGreater(len(z), 30)
        for mid, entries in z.items():
            self.assertGreater(len(entries), 0, mid)
            for e in entries:
                w, h, x, y, n, cw, ch, fw, fh = e
                p = FILES / ("%d_%d.blp" % (mid, n))
                self.assertTrue(p.exists(), p.name)
                with Image.open(p) as im:
                    self.assertEqual(im.size, (fw, fh), p.name)
                self.assertTrue(0 < cw <= fw and 0 < ch <= fh, p.name)


class NeverDarkerTests(unittest.TestCase):
    def test_any_unexplored_set_is_at_most_the_shade(self):
        rng = random.Random(3)
        for mid, entries in zones().items():
            masks = [(e, mask(mid, e)) for e in entries]
            for trial in range(4):
                un = [m for m in masks if trial == 0 or rng.random() < 0.5]   # (the first: all unexplored)
                through = np.ones((900, 1300), np.float32)    # what shows through: prod(1 - share)
                for (w, h, x, y, *_), a in un:
                    through[y:y + h, x:x + w] *= 1 - a
                worst = float((1 - through).max())
                self.assertLessEqual(worst, SHADE + 0.03, "%d: %.3f darker than the shade" % (mid, worst))


class ShowTests(unittest.TestCase):
    def setUp(self):
        src = STITCH.read_text(encoding="utf-8")
        m = re.search(r"\nShade\.Fog = .*?\nfunction Shade\.Fog\.Show\(.*?\nend\n", src, re.S)
        self.assertIsNotNone(m, "Shade.Fog in Stitch.lua")
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        self.lua.execute("""
            NONE, TEX, UNDISCOVERED = {}, "T\\\\", { 0.1, 0.2, 0.3, 0.62 }
            S = { artTop = 50 }
            Shade = { on = true, k = 0.5 }
            ns = { MapFog = { [7] = { ["100:50:10:20"] = { 1, 50, 25, 64, 32 }, ["40:40:0:0"] = { 2, 20, 20, 32, 32 } } } }
            pieces = { [7] = { ["100:50:10:20"] = { unexplored = true }, ["40:40:0:0"] = { unexplored = false } } }
            placed = {}
            function strsplit(sep, s)
                local out = {}
                for part in (s .. sep):gmatch("(.-)" .. sep) do out[#out + 1] = part end
                return unpack(out)
            end
            local function Region()
                local r = { shown = true }
                function r:SetAllPoints() end
                function r:SetFrameLevel() end
                function r:Show() self.shown = true end
                function r:Hide() self.shown = false end
                function r:SetShown(on) self.shown = on end
                function r:SetTexture(f) self.file = f end
                function r:SetTexCoord(...) self.coord = { ... } end
                function r:SetVertexColor(...) self.color = { ... } end
                function r:CreateTexture() return Region() end
                return r
            end
            function CreateFrame() return Region() end
            root = Region()
            function Place(mapID) return { left = 1000, top = 2000, sx = 2, sy = 3 } end
            function Record(tex, x, y, w, h) placed[tex] = { x, y, w, h } end
            function Shade.Collect() return { on = true }, nil end
            function Shade.Anchor(recs, on) recs.on = on end
        """)
        self.lua.execute(m.group(0))

    def test_only_unexplored_pieces_over_their_rectangles(self):
        self.lua.execute("Shade.Fog.Show(7, true)")
        t = self.lua.eval("Shade.Fog.zones[7].tex")
        un, ex = t["100:50:10:20"], t["40:40:0:0"]
        self.assertTrue(un.shown)
        self.assertFalse(ex.shown)
        self.assertEqual(tuple(self.lua.eval("placed")[un].values()), (1000 + 10 * 2, 2000 + 20 * 3, 100 * 2, 50 * 3))
        self.assertEqual(un.file, "T\\MapFog\\7_1")
        self.assertEqual(tuple(un.coord.values()), (0, 50 / 64, 0, 25 / 32))
        self.assertEqual(tuple(un.color.values()), (0.1, 0.2, 0.3, 0.5))   # (the shade's colour, Darkening's strength)

    def test_explored_goes_and_off_hides(self):
        self.lua.execute("Shade.Fog.Show(7, true)")
        self.lua.execute('pieces[7]["100:50:10:20"].unexplored = false Shade.Fog.Show(7, true)')
        self.assertFalse(self.lua.eval("Shade.Fog.zones[7].tex")["100:50:10:20"].shown)
        self.lua.execute("Shade.Fog.Show(7, false)")
        self.assertFalse(self.lua.eval("Shade.Fog.zones[7].frame").shown)

    def test_only_while_darkening(self):
        self.assertTrue(self.lua.eval("Shade.Fog.Has(7)"))
        self.assertFalse(self.lua.eval("Shade.Fog.Has(8)"))
        self.lua.execute("Shade.on = false")
        self.assertFalse(self.lua.eval("Shade.Fog.Has(7)"))


if __name__ == "__main__":
    unittest.main()
