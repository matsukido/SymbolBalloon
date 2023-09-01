import sublime
import sublime_plugin

import itertools as itools
import operator as opr
import functools as ftools
import bisect

from .containers import Cache


class FTOCmd(sublime_plugin.TextCommand):
    # Fold to outline
    def run(self, edit):

        def focus_level(target_level):
            nonlocal vw, sym_pts, sym_lvls

            size = Cache.views["size"]
            vw.unfold(sublime.Region(0, size))

            selectors = map(opr.le, sym_lvls, itools.repeat(int(target_level)))
            selected_pts = itools.compress(sym_pts, selectors)

            ab = map(opr.methodcaller("to_tuple"), map(vw.line, selected_pts))
            flat = itools.chain.from_iterable((a - 1, b)  for a, b in ab)
            a_pt = next(flat, -1)
            
            bababb = itools.zip_longest(flat, flat, fillvalue=size)
            ba_rgns = itools.starmap(sublime.Region, bababb)
            vw.fold(list(ba_rgns))

            vw.show_at_center(a_pt + 1)

        def commit_level():
            nonlocal vw
            vw.show(vw.sel()[0].begin(),
                    show_surrounds= True,
                    animate=        True,
                    keep_to_left=   True)

        vw = self.view
        Cache.query_init(vw)
        sym_pts = Cache.views["symbol_point"]
        if not sym_pts:
            return

        sym_lvls = Cache.views["symbol_level"]
        lvls = sorted(set(sym_lvls), reverse=True)
        qpitems = [*map(str, lvls)]
        
        if len(qpitems) == 1:
            focus_level(qpitems[0])
            return

        vw.window().show_quick_panel(
                items=qpitems, 
                on_highlight=lambda idx: focus_level(qpitems[idx]),
                on_select=lambda idx: commit_level(),
                selected_index=0,
                placeholder="Folding level")


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
    def do(self, current_point, mode, completed):

        def navigate(href):
            nonlocal vw
            vw.show(vw.size())
            vw.show(int(href),
                    show_surrounds=False,
                    keep_to_left=True)
            vw.erase_regions("MiniOutline")

        def unfold_selector(current_index, symbol_levels):

            symcnt = len(symbol_levels)
            if symcnt < 35:
                return itools.repeat(True)

            toplvl = min(symbol_levels)
            unfolds = map(opr.eq, symbol_levels, itools.repeat(toplvl))
            topcnt = symbol_levels.count(toplvl)
            foldcnt = (topcnt - 10) // 2

            ch = itools.chain(itools.repeat(True, 5), 
                              itools.repeat((), foldcnt),
                              [True], 
                              itools.repeat((), foldcnt), 
                              itools.repeat(True, 5 + 2))

            unfolds = ((istop and next(ch))  for istop in unfolds)

            surrounds = itools.chain(itools.repeat(False, current_index - 8), 
                                     itools.repeat(True, 14), 
                                     itools.repeat(False, symcnt))

            return ((srd or uf)  for srd, uf in zip(surrounds, unfolds))

        vw = self.view
        sym_pts = Cache.views["symbol_point"]
        to_html = ftools.partial(vw.export_to_html, 
                                 minihtml=True, enclosing_tags=False, 
                                 font_size=False, font_family=False)
        regions = map(vw.line, sym_pts)

        if mode == "symbol":
            regions = (sublime.Region(line.a, pt) if line.contains(pt) else line  
                               for line, pt in zip(regions, Cache.views["symbol_end_point"]))

        htmls = map(to_html, regions)
        hrefs = map('<a href="{}">{}</a><br>'.format, sym_pts, htmls)

        visible_symbol, _ = Cache.sectional_view(current_point)
        idx = bisect.bisect_left(sym_pts, current_point)
        uf_selectors = unfold_selector(idx, Cache.views["symbol_level"])
        
        if not visible_symbol:
            selectors = itools.repeat(False)
        else:
            vsrgns = map(opr.attrgetter("region"), visible_symbol.values())
            rotated = itools.chain(vsrgns, (rgn := next(vsrgns), ))   # repeat False
            selectors = ((rgn.contains(pt) and (rgn := next(rotated)))  for pt in sym_pts)

        indicated = (f'<div class="indicate">{href}</div>' if sel else (uf and href)
                                for href, sel, uf in zip(hrefs, selectors, uf_selectors))

        arrowed = itools.chain(itools.islice(indicated, idx), 
                               ['<div class="arrow"></div>'], 
                               indicated)

        dct = {True: ['<div class="topfold"></div>'],
               False: ['<div class="foldline"></div>']}

        grp = itools.groupby(arrowed, key=bool)
        folded = itools.chain.from_iterable(itr if bln else dct[() in itr] 
                                                            for bln, itr in grp)

        color = "var(--greenish)" if completed else "var(--redish)"
        astyle = 'a{text-decoration: none; font-size: 0.9rem;}'
        indicator = (f'.indicate{{margin: -0.1rem; padding-left: -0.12rem;'
                                f'border-left: 0.22rem solid {color};}}')

        arrow = ('.arrow{height: 0; margin: -0.1rem -0.6rem; '
                        'border-right: 0.4rem solid var(--yellowish);' 
                        'border-top: 0.3rem solid transparent;'
                        'border-bottom: 0.3rem solid transparent;}')

        foldline = ('.foldline{height: 0px; width: 3rem; margin: 0.25rem 0rem 0.25rem 3rem;'
                              'border-bottom: 1.2px solid var(--redish);}') 

        topfold = ('.topfold{height: 0; margin: -0.1rem -0.1rem; '
                            'border-left: 0.3rem solid var(--redish);' 
                            'border-top: 0.25rem solid transparent;'
                            'border-bottom: 0.25rem solid transparent;}')

        con = ('<body id="minioutline">'
                    f'<style>{astyle}{indicator}{arrow}{foldline}{topfold}</style>'
                    f'<div style="margin: 0.3rem 0.8rem">{"".join(folded)}</div>'
                '</body>')

        vw.erase_regions("MiniOutline")
        vw.add_regions(key="MiniOutline", 
                       regions=[sublime.Region(current_point)], 
                       annotations=[con],
                       annotation_color="#36c",
                       on_navigate=navigate)