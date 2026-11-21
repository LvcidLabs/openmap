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


if __name__ == "__main__":
    unittest.main()
