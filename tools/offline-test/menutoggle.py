"""Other addons' switches on OpenMap's tray (API.lua's RegisterMenuToggle, Panel.lua's SetLit), read from their
source: python -P tools/offline-test/menutoggle.py.

A switch's button glows (a gold edge) while its get() is true and its icon greys while it's false; version 5's
lit and grey set those apart (lit = fn, grey = fn or false for never), onRightClick gives it a right-click of its
own, and RefreshMenuToggles draws the buttons again. Without them a switch looks and works as before.
"""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[2] / "OpenMap"
API = (ROOT / "API.lua").read_text(encoding="utf-8")
PANEL = (ROOT / "Map" / "Panel.lua").read_text(encoding="utf-8")


def chunk(src, pattern):
    m = re.search(pattern, src, re.S)
    assert m, pattern
    return m.group(0)


class MenuToggleTests(unittest.TestCase):
    def setUp(self):
        from lupa.lua51 import LuaRuntime
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        register = chunk(API, r"\nfunction API\.RegisterMenuToggle\(owner, spec\)\n.*?\nend\n")
        refresh = chunk(API, r"\nfunction API\.RefreshMenuToggles\(\)\n.*?\nend\n")
        rows = chunk(API, r"\nfunction mod\.ExtraMenuRows\(row\)\n.*?\nend\n")
        setlit = chunk(PANEL, r"\nlocal function SetLit\(b, state\)\n.*?\nend\n").replace("local function SetLit", "function SetLit")
        self.lua.execute("""
            API, toggles, refreshed = {}, {}, 0
            tremove = table.remove
            ns = { L = setmetatable({}, { __index = function(_, k) return k end }) }
            mod = { RefreshPanel = function() refreshed = refreshed + 1 end, RightClickTip = function(t) return "Right-click: " .. t end }
            LIT, BRONZE = { 1, 0.8, 0 }, { 0.5, 0.3, 0.1 }
            function geterrorhandler() return function(e) error(e) end end
            function row(label, id, icon, get, set) return { label, get, set, id = id } end
            -- a tray button: its edge, glow and icon as SetLit leaves them
            function Button(entry)
                local b = { entry = entry, boxed = true, glow = {}, icon = {} }
                function b:SetBackdropBorderColor(r) self.edge = r end
                function b.glow:SetShown(v) self.shown = v end
                function b.icon:SetDesaturated(v) self.grey = v end
                function b.icon:SetAlpha(a) self.alpha = a end
                return b
            end
            function Look(entry, state)
                local b = Button(entry) SetLit(b, state)
                return b.glow.shown, b.icon.grey
            end
        """ + register + refresh + rows + setlit)

    def entry(self):
        return self.lua.eval("mod.ExtraMenuRows(row)")[2]   # (1: its section's heading)

    def look(self, entry, state):
        return self.lua.eval("Look")(entry, state)

    def test_as_before_without_lit_or_grey(self):
        self.lua.execute("on = true API.RegisterMenuToggle('A', { id = 'x', label = 'X', get = function() return on end, set = function() end })")
        e = self.entry()
        self.assertEqual(self.look(e, "on"), (True, False))
        self.assertEqual(self.look(e, "off"), (False, True))

    def test_lit_and_never_grey(self):
        # (Forever Nodes: left-click its panel, right-click its icons; lit while the icons are on, never greyed)
        self.lua.execute("""
            panel, icons = false, true
            API.RegisterMenuToggle('FN', { id = 'panel', label = 'FN', get = function() return panel end,
                set = function() panel = not panel end, lit = function() return icons end, grey = false,
                onRightClick = function() icons = not icons end, rightClickTip = 'map icons' })
        """)
        e = self.entry()
        self.assertEqual(self.look(e, "off"), (True, False))       # (panel closed, icons on: lit, not grey)
        e.onRight()
        self.assertEqual(self.look(e, "off"), (False, False))      # (icons off: not lit, still not grey)
        self.assertEqual(e.rightTip(), "Right-click: map icons")

    def test_grey_of_its_own(self):
        self.lua.execute("dim = true API.RegisterMenuToggle('A', { id = 'x', label = 'X', get = function() return true end, set = function() end, grey = function() return dim end })")
        e = self.entry()
        self.assertEqual(self.look(e, "on"), (True, True))
        self.lua.execute("dim = false")
        self.assertEqual(self.look(e, "on"), (True, False))

    def test_a_broken_lit_neither_lights_nor_breaks(self):
        self.lua.execute("API.RegisterMenuToggle('A', { id = 'x', label = 'X', get = function() return true end, set = function() end, lit = function() error('oops') end })")
        self.assertEqual(self.look(self.entry(), "on"), (False, False))

    def test_wrong_types_refused(self):
        for bad in ("lit = true", "grey = true", "grey = 'no'", "onRightClick = 1", "rightClickTip = 2"):
            with self.subTest(bad=bad):
                ok = self.lua.eval("function() return pcall(API.RegisterMenuToggle, 'A', { id = 'x', label = 'X', "
                                   "get = function() end, set = function() end, %s }) end" % bad)()
                self.assertFalse(ok[0] if isinstance(ok, tuple) else ok)

    def test_refresh_draws_again(self):
        before = self.lua.eval("refreshed")
        self.lua.execute("API.RefreshMenuToggles()")
        self.assertEqual(self.lua.eval("refreshed"), before + 1)

    def test_version_5(self):
        self.assertIn("local API = { major = 1, version = 5 }", API)


if __name__ == "__main__":
    unittest.main()
