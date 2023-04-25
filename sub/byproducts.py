import sublime
import sublime_plugin

import itertools as itools
import operator as opr

from .containers import Cache


class FTOCmd(sublime_plugin.TextCommand):
    # Fold to outline
    def run(self, edit):

        vw = self.view
        Cache.query_init(vw)
        sym_pts = Cache.views["symbol_point"]

        ab = map(opr.methodcaller("to_tuple"), map(vw.line, sym_pts[:-1]))
        flat = itools.chain.from_iterable((a - 1, b)  for a, b in ab)
        a_pt = next(flat, None)
        if a_pt is None:
            return
        # fillvalue=view.size()
        bababb = itools.zip_longest(flat, flat, fillvalue=sym_pts[-1])
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

        toplvl = min(symlvls)
        kind_tpls = map(opr.attrgetter("kind"), vw.symbol_regions())
        zipped = zip(symlvls, Cache.views["symbol_info"], kind_tpls)
        tpls = ((info, kind)  for lvl, info, kind in zipped if lvl == toplvl)

        ref_begin = vw.sel()[0].begin()
        symrgns = []
        qpitems = []
        index = -1
        for info, kind in tpls:

            index += (1 if info.region.begin() < ref_begin else 0)
            symrgns.append(info.region)
            qpitems.append(sublime.QuickPanelItem(
                      trigger=info.name, 
                      kind=kind))

        vw.window().show_quick_panel(
                items=qpitems, 
                on_highlight=lambda idx: focus_symbol(symrgns[idx], qpitems[idx].trigger),
                on_select=lambda idx: commit_symbol(symrgns, idx),
                selected_index=index,
                placeholder="Top level")
