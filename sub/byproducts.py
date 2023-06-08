import sublime
import sublime_plugin

import itertools as itools
import operator as opr
import functools as ftools

from .containers import Cache


class FTOCmd(sublime_plugin.TextCommand):
    # Fold to outline
    def run(self, edit):

        vw = self.view
        Cache.query_init(vw)
        sym_pts = Cache.views["symbol_point"]
        if not sym_pts:
            return

        ab = map(opr.methodcaller("to_tuple"), map(vw.line, sym_pts))
        flat = itools.chain.from_iterable((a - 1, b)  for a, b in ab)
        a_pt = next(flat, -1)
        
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
            vw.window().run_command("show_overlay", 
                                    args={"overlay": "goto", "text": "@"})
            return

        zipped = zip(symlvls,
                     Cache.views["symbol_point"],
                     Cache.views["symbol_end_point"],
                     Cache.views["symbol_name"],
                     itools.zip_longest(*Cache.views["symbol_kind"], fillvalue=""))

        toplvl = min(symlvls)
        sym_infos = (info  for lvl, *info in zipped if lvl == toplvl)

        symrgns, qpitems = [], []
        index = itools.count(-1)
        tgtpt = vw.sel()[0].begin()

        for a_pt, b_pt, name, kind in sym_infos:

            symrgns.append(sublime.Region(a_pt, b_pt))
            qpitems.append(sublime.QuickPanelItem(trigger=name, kind=kind))
            (a_pt <= tgtpt) and next(index)

        vw.window().show_quick_panel(
                items=qpitems, 
                on_highlight=lambda idx: focus_symbol(symrgns[idx], qpitems[idx].trigger),
                on_select=lambda idx: commit_symbol(symrgns, idx),
                selected_index=next(index),
                placeholder="Top level")


class MOCmd(sublime_plugin.TextCommand):
    # Mini outline
    def do(self, current_point):

        def navigate(href):
            nonlocal vw
            vw.show(vw.size())
            vw.show(int(href),
                    show_surrounds=False,
                    keep_to_left=True)
            vw.erase_regions("MiniOutline")

        vw = self.view
        sym_pts = Cache.views["symbol_point"]
        to_html = ftools.partial(vw.export_to_html, 
                                 minihtml=True, enclosing_tags=False, font_size=False)
        htmls = map(to_html, map(vw.line, sym_pts))
        hrefs = map('<a href="{}">{}</a><br>'.format, sym_pts, htmls)

        visible_symbol, _ = Cache.sectional_view(current_point)
        vsrgns = map(opr.attrgetter("region"), visible_symbol.values())
        flatten = (rgn.contains(pt)  for pt, rgn in itools.product(sym_pts, vsrgns))
        selector = map(any, zip(*[flatten] * len(visible_symbol)))
        if not visible_symbol:
            selector = itools.repeat(False)

        indicated = (f'<div class="indicate">{href}</div>' if sel else href 
                                                 for href, sel in zip(hrefs, selector))
        astyle = 'a{text-decoration: none; font-size: 0.9rem;}'
        indicator = '.indicate{border-left: 0.25rem solid var(--greenish);}'

        con = (f'<body id="minioutline"><style>{astyle}{indicator}</style>'
                   f'<div style="margin: 0.3rem, 0.8rem">{"".join(indicated)}</div>'
                '</body>')

        vw.erase_regions("MiniOutline")
        vw.add_regions(key="MiniOutline", 
                       regions=[sublime.Region(current_point)], 
                       annotations=[con],
                       annotation_color="#36c",
                       on_navigate=navigate)
