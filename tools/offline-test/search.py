"""The map's search on its title bar (Map/Nav.lua): left of the window's buttons, as wide as the title leaves it,
shown only with OpenMap's map, made out of combat, nothing of Blizzard's written, and the key binding typing into
it: python -P tools/offline-test/search.py."""
from pathlib import Path
import re
import unittest

from lupa.lua51 import LuaRuntime


ROOT = Path(__file__).resolve().parents[2] / "OpenMap"
NAV = (ROOT / "Map" / "Nav.lua").read_text(encoding="utf-8")
PANEL = (ROOT / "Map" / "Panel.lua").read_text(encoding="utf-8")
BINDINGS = (ROOT / "Bindings.xml").read_text(encoding="utf-8")


class TitleSearchTests(unittest.TestCase):
    def setUp(self):
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        self.lua.execute("""
            fighting, stitched, padView = false, false, false
            function InCombatLockdown() return fighting end
            events, timers = {}, {}
            ns = { L = setmetatable({}, { __index = function(_, k) return k end }) }
            function ns.RegisterEvent(owner, event, fn) events[event] = fn end
            function ns.UnregisterEvent(owner, event) events[event] = nil end
            C_Timer = { After = function(_, fn) timers[#timers + 1] = fn end }
            function Flush() local t = timers timers = {} for _, fn in ipairs(t) do fn() end end
            Look = { Dropdown = function() return 4, 4, 4, 4 end }
            mod = { enabled = true }
            function mod.IsStitched() return stitched end
            function mod.PadViewOn() return padView end

            -- frames that remember what was done to them
            local F = {}
            F.__index = F
            made = {}
            function CreateFrame(kind, _, parent, template)
                local f = setmetatable({ kind = kind, parent = parent, template = template, shown = true,
                    w = 0, h = 0, level = parent and (parent.level or 0) + 1 or 0, scripts = {}, hooks = {} }, F)
                made[#made + 1] = f
                if template == "SearchBoxTemplate" then f.Instructions = setmetatable({}, F) end
                return f
            end
            function F:SetSize(w, h) self.w, self.h = w, h end
            function F:SetWidth(w) self.w = w end
            function F:SetHeight(h) self.h = h end
            function F:GetWidth() return self.w end
            function F:GetHeight() return self.h end
            function F:SetAllPoints(t) self.all = t end
            function F:ClearAllPoints() self.points = {} end
            function F:SetPoint(...) self.points = self.points or {} table.insert(self.points, { ... }) end
            function F:SetFrameLevel(l) self.level = l end
            function F:GetFrameLevel() return self.level end
            function F:SetFrameStrata(s) self.strata = s end
            function F:EnableMouse(on) self.mouse = on end
            function F:Show() self.shown = true end
            function F:Hide() self.shown = false if self.scripts.OnHide then self.scripts.OnHide(self) end end
            function F:SetShown(on) if on then self:Show() else self:Hide() end end
            function F:IsShown() return self.shown end
            function F:SetAutoFocus() end
            function F:SetText(t) self.text = t end
            function F:GetText() return self.text or "" end
            function F:SetScript(name, fn) self.scripts[name] = fn end
            function F:HookScript(name, fn) self.hooks[name] = fn end
            function F:SetFocus() self.focus = true end
            function F:ClearFocus() self.focus = false end
            function F:HasFocus() return self.focus or false end
            function F:HighlightText() self.highlighted = true end

            -- Blizzard's map: locked, so a write from OpenMap's code errors
            local function Locked(t)
                return setmetatable(t, { __index = F, __newindex = function(_, k) error("wrote Blizzard's " .. tostring(k)) end })
            end
            title = Locked({ cx = 500, sw = 120 })
            rawset(title, 'GetCenter', function(self) return self.cx end)
            rawset(title, 'GetStringWidth', function(self) return self.sw end)
            buttons = Locked({ shown = true, left = 900 })
            rawset(buttons, 'GetLeft', function(self) return self.left end)
            close = Locked({ shown = true, left = 950 })
            rawset(close, 'GetLeft', function(self) return self.left end)
            border = Locked({ TitleContainer = Locked({ TitleText = title }), MaximizeMinimizeFrame = buttons, CloseButton = close, level = 30 })
            map = Locked({ shown = true, w = 1000, h = 700, level = 10, scripts = {}, hooks = {} })
            rawset(map, "BorderFrame", border)
            opened = 0
            function ToggleWorldMap() opened = opened + 1 rawset(map, "shown", true) end
            WorldMapFrame = map
        """)
        chunk = NAV[NAV.index("local places                    --"):NAV.index("-- Group members")]
        chunk = chunk[:chunk.rindex("--------")]
        self.lua.execute("local S, Safe = {}, {}\nlocal L, map = ns.L\n" + chunk.replace("local Look, Safe, L", "") +
                         "\n_G.Refresh = mod.RefreshTitleSearch\n_G.Box = function() return box end\n_G.List = function() return list end\n")
        self.g = self.lua.globals()

    def setup(self):
        self.lua.execute("mod.SetupTitleSearch(map)")

    def box(self):
        return self.lua.eval("Box()")

    def holder(self):
        return self.box().parent

    def test_left_of_the_window_buttons_as_wide_as_the_title_leaves(self):
        self.setup()
        self.lua.execute("stitched = true Refresh()")
        box = self.box()
        p = box.points[1]
        self.assertEqual((p[1], p[3]), ("RIGHT", "LEFT"))
        self.assertTrue(self.lua.eval("function(t) return t == buttons end")(p[2]))
        self.assertLess(p[4], 0)
        # (from the title's right end, 560, to the buttons, 900, less a gap each side)
        self.assertEqual(box.w, 190)
        # a narrow window: only the room there is, down to the least
        self.lua.execute("rawset(buttons, 'left', 700) rawset(map, 'w', 600) Refresh()")
        self.assertEqual(self.box().w, 120)
        self.lua.execute("rawset(buttons, 'left', 600) rawset(map, 'w', 500) Refresh()")
        self.assertEqual(self.box().w, 90)
        # full screen's buttons hidden: by the close button
        self.lua.execute("rawset(buttons, 'shown', false) rawset(map, 'w', 1900) Refresh()")
        self.assertTrue(self.lua.eval("function(t) return t == close end")(self.box().points[1][2]))
        # the results drop down under it, their right edge under its
        lst = self.lua.eval("List()")
        self.assertEqual((lst.points[1][1], lst.points[1][3]), ("TOPRIGHT", "BOTTOMRIGHT"))

    def test_above_the_title_bar(self):
        self.setup()
        self.assertGreater(self.holder().level, self.lua.eval("border.level"))
        self.assertGreater(self.holder().level, self.lua.eval("map.level") + 5)   # (Window.lua's drag strip)

    def test_only_with_openmaps_map(self):
        self.setup()
        self.assertFalse(self.holder().shown)
        self.lua.execute("stitched = true Refresh()")
        self.assertTrue(self.holder().shown)
        # Blizzard's own map (a battleground's, a dungeon's): gone, and what was typed put down
        self.lua.execute("Box():SetFocus() List():Show() stitched = false Refresh()")
        self.assertFalse(self.holder().shown)
        self.assertFalse(self.box().focus)
        self.assertFalse(self.lua.eval("List()").shown)
        # the Gamepad UI's own view, and OpenMap off
        self.lua.execute("stitched = true padView = true Refresh()")
        self.assertFalse(self.holder().shown)
        self.lua.execute("padView = false mod.enabled = false Refresh()")
        self.assertFalse(self.holder().shown)

    def test_made_out_of_combat(self):
        self.lua.execute("fighting = true")
        self.setup()
        self.assertIsNone(self.box())
        self.lua.execute("fighting = false events.PLAYER_REGEN_ENABLED()")
        self.assertIsNotNone(self.box())
        self.assertIsNone(self.lua.eval("events.PLAYER_REGEN_ENABLED"))

    def test_key_binding_types_into_it(self):
        self.setup()
        self.lua.execute("stitched = true mod.FocusSearch()")
        self.assertTrue(self.box().focus)
        # the map closed: opened first
        self.lua.execute("Box():ClearFocus() rawset(map, 'shown', false) mod.FocusSearch() Flush()")
        self.assertEqual(self.lua.eval("opened"), 1)
        self.assertTrue(self.box().focus)
        # ... not in combat
        self.lua.execute("Box():ClearFocus() rawset(map, 'shown', false) fighting = true mod.FocusSearch() Flush()")
        self.assertEqual(self.lua.eval("opened"), 1)
        self.assertFalse(self.box().focus)

    def test_bound_and_named(self):
        self.assertIn('OpenMap_Binding("search")', BINDINGS)
        self.assertIn('SEARCH = L["Find a place"]', PANEL)
        self.assertIn('if id == "search"', PANEL)
        # (not in the menu as well: one search box, Nav.lua's)
        self.assertNotIn("mod.CreateSearch(", PANEL)


if __name__ == "__main__":
    unittest.main()
