import sublime
import sublime_plugin

import itertools as itools
import operator as opr
import bisect

from .containers import Cache


class FTOCmd(sublime_plugin.TextCommand):
    # Fold to outline
    def run(self, edit):

        vw = self.view
        Cache.query_init(vw)
        sym_pts = Cache.views["symbol_point"]

        ab = map(opr.methodcaller("to_tuple"), map(vw.line, sym_pts))
        flat = itools.chain.from_iterable((a - 1, b)  for a, b in ab)
        a_pt = next(flat, None)
        if a_pt is None:
            return
        size = Cache.views["size"]
        bababb = itools.zip_longest(flat, flat, fillvalue=size)
        ba_rgns = itools.starmap(sublime.Region, bababb)
        vw.fold(list(ba_rgns))

        vw.show(a_pt + 1,
                show_surrounds= False,
                animate=        True,
                keep_to_left=   True)


class GTLSCmd(sublime_plugin.TextCommand):
    # Goto top level symbol
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

            vw.show_at_center(symrgn)
            vw.show(symrgn.a,
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
        symlvls = Cache.views["symbol_level"]
        if not symlvls:
            return

        zipped = zip(symlvls,
                     Cache.views["symbol_point"],
                     Cache.views["symbol_end_point"],
                     Cache.views["symbol_name"],
                     itools.zip_longest(*Cache.views["symbol_kind"], fillvalue=""))

        toplvl = min(symlvls)
        sym_infos = (info  for lvl, *info in zipped if lvl == toplvl)

        symrgns, qpitems = [], []

        for a_pt, b_pt, name, kind in sym_infos:

            symrgns.append(sublime.Region(a_pt, b_pt))
            qpitems.append(sublime.QuickPanelItem(trigger=name, kind=kind))

        a_pts, _ = zip(*symrgns)
        index = bisect.bisect_right(a_pts, vw.sel()[0].begin()) - 1

        vw.window().show_quick_panel(
                items=qpitems, 
                on_highlight=lambda idx: focus_symbol(symrgns[idx], qpitems[idx].trigger),
                on_select=lambda idx: commit_symbol(symrgns, idx),
                selected_index=index,
                placeholder="Top level")
