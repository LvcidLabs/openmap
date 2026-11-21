"""Zooming and panning in a fight (WorldMap.lua's combat view, Stitch.lua's S.ViewAt) in Lua 5.1:
python -P tools/offline-test/combatview.py.

In combat nothing of Blizzard's map may be written from OpenMap's code (the game's code reads its fields,
and the quest log's protected calls were blocked: #345 #347 #368), so the view moves OpenMap's own art
instead. This checks that SetView's combat branch touches nothing of Blizzard's map, and that S.ViewAt puts
the point asked for at the view's centre, at the scale asked for, whatever the canvas is at, and back again.
"""
from pathlib import Path
import re
import unittest

from lupa.lua51 import LuaRuntime


ROOT = Path(__file__).resolve().parents[2] / "OpenMap"
WORLDMAP = (ROOT / "Map" / "WorldMap.lua").read_text(encoding="utf-8")
STITCH = (ROOT / "Map" / "Stitch.lua").read_text(encoding="utf-8")


def chunk(src, name):
    m = re.search(r"\nfunction %s\(.*?\nend\n" % re.escape(name), src, re.S)
    assert m, name
    return m.group(0)


class CombatBranchTests(unittest.TestCase):
    """SetView in combat: the view kept and OpenMap's art moved, nothing of Blizzard's touched"""

    def setUp(self):
        m = re.search(r"\nlocal function SetView\(scale, x, y\)\n(.*?)\nend\n", WORLDMAP, re.S)
        self.assertIsNotNone(m, "SetView in WorldMap.lua")
        b = re.search(r"\tif InCombatLockdown\(\) then\n(.*?)\n\t\treturn\n\tend", m.group(1), re.S)
        self.assertIsNotNone(b, "SetView's combat branch")
        self.branch = b.group(1)

    def test_nothing_of_blizzards_written_or_called(self):
        # (reading the map's ID is all: no field of the scroll container or the map, no method of theirs)
        for line in self.branch.splitlines():
            code = line.split("--")[0]
            self.assertNotRegex(code, r"\bsc\s*[.:\[]", line)
            self.assertIsNone(re.search(r"\bmap\s*[.:](?!GetMapID\(\))", code), line)

    def test_the_art_moved_and_the_view_kept(self):
        self.assertIn("S.ViewAt(scale, x, y)", self.branch)
        self.assertIn("waitingView", self.branch)

    def test_combat_over_puts_the_art_back(self):
        over = chunk(WORLDMAP, "mod.CombatOver")
        self.assertIn("CombatViewOff()", over)
        off = re.search(r"\nlocal function CombatViewOff\(\)\n(.*?)\nend\n", WORLDMAP, re.S).group(1)
        self.assertIn("S.ViewAt(nil)", off)
        self.assertIn("FadeCanvas(false)", off)

    def test_icons_press_handlers_not_called_in_combat(self):
        # (Blizzard's own press handlers write its fields: not run from OpenMap's code in a fight)
        for name in ("OnPinMouseDown", "OnPinMouseUp"):
            body = re.search(r"\nlocal function %s\(.*?\n(.*?)\nend\n" % name, WORLDMAP, re.S).group(1)
            fight = re.search(r"if InCombatLockdown\(\) then\n(.*?)\n\t\treturn\n\tend", body, re.S)
            self.assertIsNotNone(fight, name)
            self.assertNotRegex(fight.group(1), r"\bsc\s*[.:]", name)


class ArrowInCombatTests(unittest.TestCase):
    """In a fight your arrow is OpenMap's own, placed in the art: Blizzard's (its group members pin) is
    protected then, can't be lifted over the art again as Blizzard reuses it, and stays where the canvas has
    it while the combat view moves the art (the arrow went missing in combat)"""

    def test_openmaps_arrow_in_combat_and_in_the_combat_view(self):
        m = re.search(r"local _, mx, my = ns\.Safe\.PlayerPos\(mapID\)\n\tif (.*?) then\n\t\tS\.SetPlayer\(nil\)", WORLDMAP)
        self.assertIsNotNone(m, "the ticker's arrow choice")
        self.assertIn("not InCombatLockdown()", m.group(1))
        self.assertIn("not combatView", m.group(1))

    def test_arrow_placed_on_the_art_at_the_views_scale(self):
        # (on root's corner, which S.ViewAt moves, at the scale ApplyZoom gives: the combat view's in a fight)
        body = chunk(STITCH, "S.PlacePlayer")
        self.assertIn('arrow:SetPoint("CENTER", root, "TOPLEFT"', body)
        self.assertIn("scaleNow", body)
        apply = re.search(r"\nApplyZoom = function\(\)\n(.*?)\nend\n", WORLDMAP, re.S).group(1)
        self.assertIn("CanvasScale()", apply)


class ViewAtTests(unittest.TestCase):
    """S.ViewAt: the host map's point (x, y) at the view's centre at canvas scale `scale`"""

    def setUp(self):
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        self.lua.execute("""
            S = {}
            host = { l = 1000, t = 400, k = 0.5 }
            local function Frame(t)
                t = t or {}
                function t:GetScale() return self.scale or 1 end
                function t:SetScale(s) self.scale = s end
                function t:GetEffectiveScale() return (self.scale or 1) * (self.parent and self.parent:GetEffectiveScale() or 1) end
                function t:GetParent() return self.parent end
                function t:ClearAllPoints() self.point = nil end
                function t:SetPoint(p, rel, rp, x, y) self.point = { p, rel, rp, x, y } end
                return t
            end
            -- the view: 800 x 600 on screen, its centre at (400, 300) in its own units (y up)
            view = Frame({})
            function view:GetCenter() return 400, 300 end
            -- Blizzard's canvas at scale 2, scrolled so its corner is 1000 px left and 500 px above the view's
            canvas = Frame({ parent = view, scale = 2, w = 3000, h = 2000 })
            function canvas:GetLeft() return -1000 / 2 end      -- (its own units: screen px / its scale)
            function canvas:GetTop() return (600 + 500) / 2 end
            function canvas:GetWidth() return self.w end
            function canvas:GetHeight() return self.h end
            root = Frame({ parent = canvas, scale = host.k })
        """)
        self.lua.execute(chunk(STITCH, "S.ViewAt"))

    def screen_of(self, wx, wy):
        """where a world point (world px) in root lands on screen, (x, y down from the view's top)"""
        L = self.lua
        k = L.eval("root.scale")
        ox, oy = L.eval("root.point[4]"), L.eval("root.point[5]")
        s0 = L.eval("canvas.scale")
        # root's coordinates are scaled by its scale within the canvas, the canvas by s0 on screen
        cx, cy = (ox + wx) * k, (-oy + wy) * k
        # the canvas corner on screen (y down): x = GetLeft * s0, y = 600 - GetTop * s0
        left, top = L.eval("canvas:GetLeft()") * s0, 600 - L.eval("canvas:GetTop()") * s0
        return left + cx * s0, top + cy * s0

    def test_the_point_asked_for_is_at_the_centre(self):
        # (the host map's point at 0.25, 0.75 of the canvas, at canvas scale 3)
        self.lua.eval("S.ViewAt")(3, 0.25, 0.75)
        # (that canvas point's world px: canvas = (world - host corner) * k)
        wx = 0.25 * 3000 / 0.5 + 1000
        wy = 0.75 * 2000 / 0.5 + 400
        x, y = self.screen_of(wx, wy)
        self.assertAlmostEqual(x, 400, places=6)
        self.assertAlmostEqual(y, 300, places=6)

    def test_at_the_scale_asked_for(self):
        self.lua.eval("S.ViewAt")(3, 0.25, 0.75)
        x0, _ = self.screen_of(2000, 1000)
        x1, _ = self.screen_of(2010, 1000)
        # (10 world px: 10 * k canvas units, at canvas scale 3 on screen)
        self.assertAlmostEqual(x1 - x0, 10 * 0.5 * 3, places=6)

    def test_back_where_layout_put_it(self):
        self.lua.eval("S.ViewAt")(3, 0.25, 0.75)
        self.lua.eval("S.ViewAt")(None)
        self.assertEqual(self.lua.eval("root.scale"), 0.5)
        self.assertEqual((self.lua.eval("root.point[4]"), self.lua.eval("root.point[5]")), (-1000, 400))
        self.assertIsNone(self.lua.eval("S.viewAt"))


if __name__ == "__main__":
    unittest.main()
