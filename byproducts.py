import sublime
import sublime_plugin

import itertools
import operator as opr

from .containers import Cache


class FoldToOutlineCommand(sublime_plugin.TextCommand):

    def run(self, edit):

        vw = self.view
        Cache.query_init(vw)
        rgn_a = Cache.views["region_a"]

        ab = map(opr.methodcaller("to_tuple"), map(vw.line, rgn_a[:-1]))
        flat = itertools.chain.from_iterable((a - 1, b)  for a, b in ab)
        a_pt = next(flat, None)
        if a_pt is None:
            return

        bababb = itertools.zip_longest(flat, flat, fillvalue=rgn_a[-1])
        ba_rgns = itertools.starmap(sublime.Region, bababb)
        vw.fold(list(ba_rgns))

        self.view.show(a_pt + 1,
                show_surrounds= False,
                animate=        True,
                keep_to_left=   True)


class GotoTopLevelSymbolCommand(sublime_plugin.TextCommand):

    def run(self, edit):

        def focus_symbol(symrgn, word):
            nonlocal vw
            vw.add_regions(key="GotoTopLevelSymbol", 
                           regions=[symrgn], 
                           flags=sublime.DRAW_NO_FILL,
                           scope="invalid",
                           icon="circle",
                           annotations=[word],
                           annotation_color="#0a0")

            self.view.show_at_center(symrgn)
            self.view.show(symrgn.a,
                    show_surrounds= True,
                    animate=        True,
                    keep_to_left=   True)

        def commit_symbol(symrgns, idx):
            nonlocal vw
            vw.erase_regions("GotoTopLevelSymbol")
            if idx < 0:
                vw.show_at_center(vw.sel()[0])  # cancel
            else:
                vw.sel().clear()
                vw.sel().add(symrgns[idx])

        vw = self.view
        Cache.query_init(vw)
        symlvl = Cache.views["symbol_level"]
        if not symlvl:
            return

        toplvl = min(symlvl)
        lvl_info = zip(symlvl, Cache.views["symbol_info"])
        infos = (info  for lvl, info in lvl_info if lvl == toplvl)

        ref_begin = vw.sel()[0].begin()
        symrgns = []
        qpitems = []
        index = -1
        for info in infos:

            index += (1 if info.region.begin() < ref_begin else 0)
            symrgns.append(info.region)
            qpitems.append(sublime.QuickPanelItem(
                      trigger=info.name, 
                      kind=info.kind))

        vw.window().show_quick_panel(
                items=qpitems, 
                on_highlight=lambda idx: focus_symbol(symrgns[idx], qpitems[idx].trigger),
                on_select=lambda idx: commit_symbol(symrgns, idx),
                selected_index=index,
                placeholder="Top level")
