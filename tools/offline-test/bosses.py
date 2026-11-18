"""Boss pins' data (Data/Forever/DungeonBosses.lua) against the maps and boss lists it's for:
python -P tools/offline-test/bosses.py

Each boss's place must be on one of its instance's floors (Data/DungeonMaps.lua's, else
Data/DungeonDrawn.lua's, as Map/Dungeons.lua's FloorsOf picks them), inside the picture (0..1),
and a boss the game lists for it (Places.lua) or one placed by hand (tools/map-dungeons/bosses.json).
(The pins themselves, on the dungeon's map, and the placer need the game: the stub has no world map.)
"""
from pathlib import Path
import json
import unittest

from lupa.lua51 import LuaRuntime

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "OpenMap" / "Data" / "Forever"


def load():
    lua = LuaRuntime(unpack_returned_tuples=True)
    ns = lua.eval("{ Media = { tex = '' } }")
    for name in ("Places.lua", "DungeonMaps.lua", "DungeonDrawn.lua", "DungeonMinimap.lua", "DungeonBosses.lua"):
        fn = lua.eval("function(src, ns) return assert(loadstring(src))('OpenMap', ns) end")
        fn((DATA / name).read_text(encoding="utf-8"), ns)
    return ns


class Bosses(unittest.TestCase):
    def test_places(self):
        ns = load()
        places = ns.MapPlaces
        placed = json.loads((ROOT / "tools" / "map-dungeons" / "bosses.json").read_text(encoding="utf-8")) \
            if (ROOT / "tools" / "map-dungeons" / "bosses.json").exists() else {}
        n = 0
        for key, bosses in ns.MapDungeonBosses.items():
            base = int(key[8:]) if isinstance(key, str) and key.startswith("minimap:") else key
            floors = ns.MapDungeonMinimap[base] if base != key else (ns.MapDungeonMaps[key] or ns.MapDungeonDrawn[key])
            self.assertTrue(floors, "%s: bosses for a dungeon with no map" % key)
            listed = set((places.bosses[base] or {}).values()) if isinstance(base, int) else set()
            listed |= set(placed.get(str(key), {}))
            for name, p in bosses.items():
                n += 1
                self.assertIn(name, listed, "%s: %s isn't one of its bosses" % (key, name))
                self.assertTrue(1 <= p[1] <= len(floors), "%s: %s on floor %s of %d" % (key, name, p[1], len(floors)))
                self.assertTrue(0 <= p[2] <= 1 and 0 <= p[3] <= 1, "%s: %s off its picture" % (key, name))
        self.assertGreater(n, 100, "fewer bosses placed than the journals alone give")


class InstanceHereTests(unittest.TestCase):
    """Open the world map against the game's dungeon data and the Journal handoff."""

    def setUp(self):
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        self.lua.execute((ROOT / "tools" / "offline-test" / "stub.lua").read_text(encoding="utf-8"))
        self.addCleanup(self.lua.execute, r'assert(#ERRORS == 0, table.concat(ERRORS, "\n"))')
        ns = self.lua.table()
        run = self.lua.eval("function(src, path, ns) return assert(loadstring(src, '@' .. path))('OpenMap', ns) end")
        addon = ROOT / "OpenMap"
        for path in (DATA / "Client.lua", addon / "Core.lua", DATA / "Places.lua",
                     DATA / "DungeonMaps.lua", DATA / "DungeonDrawn.lua"):
            run(path.read_text(encoding="utf-8"), str(path), ns)
        worldmap = ns.NewModule(ns, "worldmap")
        worldmap.padRoots = self.lua.table()
        worldmap.IsStitched = self.lua.eval("function() return false end")
        ns.MapStitch = self.lua.eval("{ InstanceMap = function() end, InstanceName = function(inst) return inst[2] end }")
        path = addon / "Map" / "Dungeons.lua"
        run(path.read_text(encoding="utf-8"), str(path), ns)
        ns.InitDB(ns)
        self.lua.globals().worldmap = worldmap
        self.lua.execute("""
            local here, lfg, subzone, minimapZone, zone
            lfgNames = {}
            C_LFGInfo = { GetDungeonInfo = function(id) return { name = lfgNames[id] } end }
            C_Map = { GetBestMapForUnit = function() if not here then return 1444 end end,
                      GetMapInfo = function() end }
            function IsInInstance() return here ~= nil end
            function GetInstanceInfo() return "x", "party", 1, "", 5, 0, false, here, nil, lfg end
            function GetSubZoneText() return subzone end
            function GetMinimapZoneText() return minimapZone end
            function GetZoneText() return zone end

            -- UIPanelButtonTemplate supplies this font string in the game.
            local create = CreateFrame
            function CreateFrame(kind, name, parent, template)
                local frame = create(kind, name, parent, template)
                if template == "UIPanelButtonTemplate" then
                    local text = frame:CreateFontString()
                    function frame:GetFontString() return text end
                end
                return frame
            end

            NIL_GLOBALS.ForeverDungeonJournal_NS = true
            local map = CreateFrame("Frame")
            map:Hide()
            map.ScrollContainer = CreateFrame("Frame", nil, map)
            function map:GetMapID() return 1444 end
            function map:OnMapChanged() end
            worldmap:SetupDungeons(map)

            function SetLocation(id, lfgID, sub, minimap, zoneText)
                here, lfg, subzone, minimapZone, zone = id, lfgID, sub, minimap, zoneText
            end
            function Find(...)
                SetLocation(...)
                if map:IsShown() then map:Hide() end
                RunTimers(0.3)  -- Reopen after the brief hide-and-show shortcut.
                map:Show()
                RunTimers(0.15)
                if worldmap.DungeonViewShown() then return OpenMapDungeonView.inst[2] end
            end
            function ShownFloor()
                local view = OpenMapDungeonView
                local floor = view.floors[view.floor]
                return floor.name or floor.wing
            end
        """)

    def test_by_map_id(self):
        self.assertEqual(self.lua.eval("Find(36)"), "Deadmines")

    def test_lfg_identifies_wing_before_indoor_text(self):
        find = self.lua.globals().Find
        for instance, lfg, subzone, expected in (
            (429, 33, "Capital Gardens", "Dire Maul - East"),
            (429, 35, "Gordok Commons", "Dire Maul - West"),
            (429, 37, "Warpwood Quarter", "Dire Maul - North"),
            (229, 31, None, "Lower Blackrock Spire"),
            (229, 43, "Skitterweb Tunnels", "Upper Blackrock Spire"),
        ):
            with self.subTest(instance=instance, lfg=lfg):
                self.assertEqual(find(instance, lfg, subzone), expected)
        self.assertEqual(self.lua.eval("ShownFloor()"), "Upper Blackrock Spire")

    def test_indoor_zone_names(self):
        find = self.lua.globals().Find
        for wing in ("Graveyard", "Library", "Armory", "Cathedral"):
            with self.subTest(wing=wing):
                self.assertEqual(find(189, 0, wing), f"Scarlet Monastery - {wing}")
                self.assertEqual(self.lua.eval("ShownFloor()"), wing)
        self.assertEqual(find(429, 0, "Dire Maul", "Gordok Commons"), "Dire Maul - North")
        self.assertEqual(find(429, 0, None, None, "The Shrine of Eldretharr"), "Dire Maul - East")

    def test_localized_lfg_name_as_indoor_text(self):
        self.lua.execute('lfgNames[35] = "Düsterbruch: West"')
        self.assertEqual(self.lua.eval('Find(429, 0, "Düsterbruch: West")'), "Dire Maul - West")

    def test_live_evidence_is_saved_before_opening_the_map(self):
        self.lua.execute("""
            SetLocation(429, 35)
            worldmap.NoteDungeonWing()
            assert(worldmap.char.dungeonWing[1] == 429)
            assert(worldmap.char.dungeonWing[2] == "Dire Maul - West")
        """)
        self.assertEqual(self.lua.eval("Find(429)"), "Dire Maul - West")
        self.assertEqual(self.lua.eval('Find(429, 0, "Gordok Commons")'), "Dire Maul - North")
        self.assertEqual(self.lua.eval("worldmap.char.dungeonWing[2]"), "Dire Maul - North")

    def test_saved_wing_is_validated_and_default_is_not_saved(self):
        self.assertEqual(self.lua.eval("Find(429)"), "Dire Maul - East")
        self.assertIsNone(self.lua.eval("worldmap.char.dungeonWing"))
        self.lua.execute('worldmap.char.dungeonWing = { 429, "Dire Maul - West" }')
        self.assertEqual(self.lua.eval("Find(189)"), "Scarlet Monastery - Graveyard")
        self.assertEqual(self.lua.eval("Find(429)"), "Dire Maul - West")
        self.lua.execute('worldmap.char.dungeonWing = { 429, "Scarlet Monastery - Armory" }')
        self.assertEqual(self.lua.eval("Find(429)"), "Dire Maul - East")

    def test_journal_owns_the_map_for_the_resolved_wing(self):
        self.lua.execute("""
            local current = function() return "Dire Maul: West" end
            ForeverDungeonJournal_NS = {
                DB = { ["Dire Maul: West"] = {} },
                CurrentDungeon = current,
                OpenBossPage = function() error("opened a Journal page") end,
                RefreshWorldMapOverlay = function() error("refreshed the Journal overlay") end,
            }
            assert(Find(429, 35) == nil, "OpenMap covered Journal's map")
            assert(ForeverDungeonJournal_NS.CurrentDungeon == current, "replaced Journal's lookup")
            assert(Find(429, 37) == "Dire Maul - North", "Journal has no page for this wing")
        """)

    def test_game_map_button_keeps_inside_maps_off(self):
        self.lua.execute("""
            assert(Find(429, 35) == "Dire Maul - West")
            local button = OpenMapDungeonView.gameMap
            assert(button:IsShown(), "The game's map button is missing inside the dungeon")
            button:GetScript("OnClick")(button)
            assert(worldmap.db.dungeonInside == false, "the button did not save the preference")
            assert(not worldmap.DungeonViewShown(), "the button did not give back the game's map")
            assert(Find(429, 35) == nil, "reopening covered the game's map again")
        """)

    def test_no_portal_ticker(self):
        self.lua.execute("""
            FireEvent("ZONE_CHANGED_NEW_AREA")
            FireEvent("PLAYER_LEAVING_WORLD")
            SetLocation(429, 35)
            FireEvent("PLAYER_ENTERING_WORLD")
            worldmap.NoteDungeonWing()
            for _, timer in ipairs(TIMERS) do
                assert(not timer.every, "created a recurring dungeon timer")
            end
        """)

    def test_forevers_own(self):
        self.assertEqual(self.lua.eval("Find(2970)"), "The Drowned City")
        self.assertEqual(self.lua.eval("Find(3039)"), "Krol'dok Stronghold")
        self.assertEqual(self.lua.eval("Find(3001)"), "Shaper's Terrace")

    def test_not_in_one(self):
        self.assertIsNone(self.lua.eval("Find(nil)"))
        self.assertIsNone(self.lua.eval("Find(0)"))                              # (0: never one, not even a 0 left in the data)

    def test_every_drawn_map_is_found_inside_its_dungeon(self):
        ns = load()
        for key in ns.MapDungeonDrawn.keys():
            self.assertIsInstance(key, int, "%s: a drawn map by name: the map opened inside it can't find it" % key)
            self.assertIsNotNone(self.lua.eval("Find(%d)" % key), "%s: a drawn map no dungeon in Places.lua has" % key)


class ByMapIDTests(unittest.TestCase):
    """what was kept per dungeon by name (the quill's drawings, the bosses placed) for WoW Forever's own
    goes to its mapID once they have one (Dungeons.lua's ByMapID, #149), never over what's there already"""

    def setUp(self):
        import re
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        src = (ROOT / "OpenMap" / "Map" / "Dungeons.lua").read_text(encoding="utf-8")
        m = re.search(r"\nlocal function ByMapID\(all, inst\).*?\nend\n", src, re.S)
        self.assertIsNotNone(m, "ByMapID in Dungeons.lua")
        self.lua.execute(m.group(0) + "\n Move = ByMapID")

    def test_moved_once(self):
        self.lua.execute("""
            all = { ["The Drowned City"] = { "lines" } }
            Move(all, { 2970, "The Drowned City" })
            assert(all[2970][1] == "lines" and all["The Drowned City"] == nil)
            Move(all, { 2970, "The Drowned City" })
            assert(all[2970][1] == "lines")
        """)

    def test_never_over_whats_there(self):
        self.lua.execute("""
            all = { ["The Drowned City"] = { "old" }, [2970] = { "new" } }
            Move(all, { 2970, "The Drowned City" })
            assert(all[2970][1] == "new" and all["The Drowned City"][1] == "old")
            Move(nil, { 2970, "x" })                    -- (nothing kept yet)
            local none = {}
            Move(none, { 0, "Somewhere" })              -- (no mapID: stays by name)
            assert(next(none) == nil)
        """)

if __name__ == "__main__":
    unittest.main()
