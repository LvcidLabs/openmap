"""The map in a fight (WorldMap.lua), read from its source: python -P tools/offline-test/combatmap.py.

In combat nothing of Blizzard's map is written from OpenMap's code (#345 #347 #368), so the map stays as it is
then. Two things follow from that and are checked here: your arrow is OpenMap's own in a fight (Blizzard's,
protected then, can't be lifted over the art again and went under it), and a view Blizzard reset in a fight
(the quest log opened from the tracker: the whole map) is put back to OpenMap's as combat ends. And Blizzard's
own scale changes wait a frame for OpenMap's view out of combat, so an opening lays the icons out once (#293).
"""
from pathlib import Path
import re
import unittest


WORLDMAP = (Path(__file__).resolve().parents[2] / "OpenMap" / "Map" / "WorldMap.lua").read_text(encoding="utf-8")


def function(name):
    m = re.search(r"\nfunction %s\(.*?\nend\n" % re.escape(name), WORLDMAP, re.S)
    assert m, name
    return m.group(0)


class CombatMapTests(unittest.TestCase):
    def test_openmaps_arrow_in_combat(self):
        m = re.search(r"local _, mx, my = ns\.Safe\.PlayerPos\(mapID\)\n\tif (.*?) then\n\t\tS\.SetPlayer\(nil\)", WORLDMAP)
        self.assertIsNotNone(m, "the ticker's arrow choice")
        self.assertIn("not InCombatLockdown()", m.group(1))

    def test_a_reset_in_combat_waits_for_its_end(self):
        hook = re.search(r'hooksecurefunc\(sc, "ResetZoom", function\(self\)\n(.*?)\n\tend\)', WORLDMAP, re.S)
        self.assertIsNotNone(hook, "the ResetZoom hook")
        body = hook.group(1)
        # (in combat: into the own view where it can come up, OwnView.lua, else noted for combat's end;
        # nothing of Blizzard's written either way)
        fight = re.search(r"if InCombatLockdown\(\) then\n(.*?)\n\t\t\treturn\n\t\tend", body, re.S)
        self.assertIsNotNone(fight)
        self.assertIn("mod.OwnViewStart()", fight.group(1))
        self.assertIn("resetDue = true", fight.group(1))
        self.assertIn("mod.ResetDue()", function("mod.CombatOver"))

    def test_nothing_of_blizzards_map_set_in_combat(self):
        # (SetView keeps the view for combat's end: the canvas isn't touched then)
        m = re.search(r"\nlocal function SetView\(scale, x, y\)\n(.*?)\nend\n", WORLDMAP, re.S)
        branch = re.search(r"\tif InCombatLockdown\(\) then\n(.*?)\n\t\treturn\n\tend", m.group(1), re.S).group(1)
        for line in branch.splitlines():
            self.assertNotRegex(line.split("--")[0], r"\bsc\s*[.:\[]", line)

    def test_blizzards_scale_change_laid_out_once(self):
        # (#293: its reset as the map opens laid the icon sets out for the whole world, then for OpenMap's view
        # again: Blizzard's own change waits a frame for OpenMap's; in combat, or before the map is up, at once)
        m = re.search(r'dp\.OnCanvasScaleChanged = Ours\("scale changed", function\(\)\n(.*?)\n\tend\)', WORLDMAP, re.S)
        self.assertIsNotNone(m)
        self.assertIn("if viewSetting or InCombatLockdown() or not active then return ApplyZoom() end", m.group(1))
        self.assertIn("C_Timer.After(0", m.group(1))
        sv = re.search(r"\nlocal function SetView\(scale, x, y\)\n(.*?)\nend\n", WORLDMAP, re.S).group(1)
        self.assertIn("viewSetting = true\n\tmap:OnCanvasScaleChanged()\n\tviewSetting, scaleWaiting = false, false", sv)


    def test_opened_in_a_fight_the_own_view_comes_up(self):
        # (not only once zoomed or dragged: its icons were never moved onto it before that)
        m = re.search(r'local shown = Ours\("map shown", function\(\)\n(.*?)\n\tend\)', WORLDMAP, re.S)
        self.assertIsNotNone(m)
        self.assertIn("if InCombatLockdown() and mod.OwnViewStart then", m.group(1))


class CombatEndTests(unittest.TestCase):
    """the combat view's view kept as combat ends, through what follows it in mod.CombatOver: OpenMap's zoom
    levels put in (Blizzard resets its view, OpenMap's reset follows) and a reset noted in the fight (the zoom
    jumped as the fight ended, test16)"""

    def setUp(self):
        from lupa.lua51 import LuaRuntime
        over = function("mod.CombatOver")
        flush = function("mod.FlushWaitingView")
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        self.lua.execute("""
            fight, active, anim, afterCombat, resetDue, waitingView = false, true, nil, true, false, nil
            function InCombatLockdown() return fight end
            view = { scale = 1, x = 0.5, y = 0.5 }
            function SetView(scale, x, y) view = { scale = scale, x = x, y = y } end
            own = { on = true, scale = 3, x = 0.2, y = 0.7 }
            map = { GetMapID = function() return 1429 end, IsShown = function() return true end }
            mod = {}
            -- (as OwnView.lua: the view on Blizzard's canvas, then the art back)
            function mod.OwnViewStop() own.on = false SetView(3, 0.2, 0.7) end
            -- (Blizzard's reset as the zoom levels come in, OpenMap's reset following it: "When reopening the map")
            sc = { OnCanvasSizeChanged = function() SetView(1, 0.5, 0.5) end }
            function KeepPadCursor(fn, ...) return fn(...) end
            function mod.ResetDue() end
        """ + flush + over)

    def test_the_view_kept(self):
        self.lua.execute("mod.CombatOver()")
        v = self.lua.eval("view")
        self.assertEqual((v.scale, v.x, v.y), (3, 0.2, 0.7))

    def test_without_the_own_view_as_before(self):
        self.lua.execute("own.on = false afterCombat = false mod.CombatOver()")
        v = self.lua.eval("view")
        self.assertEqual((v.scale, v.x, v.y), (1, 0.5, 0.5))

if __name__ == "__main__":
    unittest.main()
