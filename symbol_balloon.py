import sublime
import sublime_plugin

import html
import re
import itertools as itools
import operator as opr
import time
import math

from .containers import Const, Pkg, ChainMapEx, Closed, Cache
from .byproducts import *


class SymbolBalloonListner(sublime_plugin.EventListener):
    is_panel = False

    def on_activated_async(self, view):
        if view.element() is None:
            if not self.is_panel:
                Cache.query_init(view)
            self.is_panel = False
        else:
            self.is_panel = True

    def on_pre_close(self, view):
        del Cache.views.maps[0]


def scan_manager(scanlines):

    def _scan_manager_(view, start_point, end_point):

        stopper = iter(range(1, Pkg.settings.get("max_scan_lines", 20000)))

        sym_pts = Cache.views["symbol_point"]
        index = sym_pts.index(start_point)
        sympts = itools.takewhile(lambda pt: pt < end_point, sym_pts[index:])
        
        zipped = zip(Cache.views["scanned_point"][index:], 
                     sym_pts[index + 1:],
                     sympts,
                     Cache.views["symbol_level"][index:],
                     itools.count(start=index))

        for scanpt, nextsym, sympt, symlvl, idx in zipped:

            if sympt < end_point < scanpt:
                continue
            delta_rgn = view.full_line(sublime.Region(scanpt, min(nextsym, end_point)))
            fulllines = view.substr(delta_rgn).splitlines(True)

            linestart_pts = itools.accumulate(map(len, fulllines), initial=delta_rgn.a)

            start_row = 2 if scanpt == sympt else 0
            zp = itools.islice(zip(linestart_pts, fulllines, stopper), start_row, None)
            line_tpls = ((pt, fline)  for pt, fline, _ in zp if not fline.isspace())

            new_scannedpt, closed = scanlines(view, line_tpls, symlvl)

            if new_scannedpt is not None:
                Cache.views["scanned_point"][idx] = new_scannedpt
                Cache.views["closed"][idx].appendflat(closed)

        return next(stopper, False)

    return _scan_manager_


@scan_manager
def scan_lines(view, line_tuples, target_indentlevel):

    ignrchr = Pkg.settings.get("ignored_characters", "")
    ignrscope = Pkg.settings.get("ignored_scope", "_")
    tabsize = int(view.settings().get('tab_size', 8))
    if Cache.views["using_tab"]:
        tabsize = 1

    tgtlvl = target_indentlevel
    pt = None
    closed = Closed()

    for pt, fullline in line_tuples:

        if tgtlvl == 0:
            topchr = fullline[0:1]
            if topchr.isspace():
                continue
            idtwidth = idtlvl = 0

        else:
            topchr = fullline.lstrip()[0:1]
            idtwidth = fullline.index(topchr)
            idtlvl = math.ceil(idtwidth / tabsize)
            if tgtlvl < idtlvl:
                continue

        if topchr in ignrchr or view.match_selector(pt + idtwidth, ignrscope):
            closed.false.setdefault(idtlvl, pt)

        else:
            closed.true.setdefault(idtlvl, pt)
            tgtlvl = idtlvl - 1
            if tgtlvl < 0:
                break

    return pt, closed


class RaiseSymbolBalloonCommand(sublime_plugin.TextCommand):

    def run(self, edit):
        
        def navigate(href):
            nonlocal vw
            vw.show(int(href),
                    show_surrounds=False,
                    animate=True,
                    keep_to_left=True)

        def annotation_navigate(href):
            nonlocal vw
            vw.erase_regions(Const.KEY_ID)

        vw = self.view
        Cache.query_init(vw)
        Pkg.init_settings()

        vpoint = vw.visible_region().begin()
        offset = Pkg.settings.get("row_offset", 0)
        vpoint = vw.text_point(vw.rowcol(vpoint)[0] + offset, 0)

        sym_pts = itools.takewhile(lambda pt: pt < vpoint, Cache.views["symbol_point"])
        nearly_symbol = dict(zip(Cache.views["symbol_level"], sym_pts))
        if not nearly_symbol:
            return

        top_level_pt = nearly_symbol[min(nearly_symbol)]
        is_source = "Markdown" not in vw.syntax().name

        if is_source:
            completed = scan_lines(vw, top_level_pt, vpoint + 1)
            visible_symbol, ignoredpt = Cache.sectional_view(vpoint + 1)

        else:
            visible_symbol, _ = Cache.sectional_view(vpoint + 1)
            ignoredpt = None
            completed = True

        symbol_infos = [*visible_symbol.values()]
        if not symbol_infos:
            return
        
        vw.run_command("break_symbol_balloon")
        symbol_infos.sort(key=opr.attrgetter("region.a"))
        markup = ""
        is_param = ("meta.function.parameters | meta.class.parameters "
                    "| meta.class.inheritance | meta.method.parameters")
        tabsize = int(vw.settings().get('tab_size', 8))
        
        for symbol in symbol_infos:

            symbolpt = symbol.region.a
            symbolpt_b = symbol.region.b
            prm_max = symbolpt_b + 1500

            prm_a = itools.dropwhile(lambda pnt:
                        opr.xor(
                            vw.match_selector(pnt, is_param),
                            vw.match_selector(pnt, "meta.function | meta.class")
                        ), range(symbolpt_b, prm_max))
            try:
                prm_begin = next(prm_a)
                prm_b = itools.dropwhile(lambda pnt:
                                    vw.match_selector(pnt, is_param), prm_a)
                prm_end = next(prm_b, prm_max)
                param = vw.substr(sublime.Region(prm_begin, prm_end))
                param = re.sub(r'^[ \t]+', ' ', param, flags=re.MULTILINE)

            except StopIteration:
                param = ""

            row = vw.rowcol(symbolpt)[0] + 1

            symbolline = vw.substr(vw.line(symbolpt))
            kwd, sym, prm = symbolline.partition(symbol.name.strip())

            kwd, sym, prm, param = map(lambda st:
                html.escape(st).expandtabs(tabsize).replace(" ",  "&nbsp;"),
                (kwd, sym, prm, param))
            
            markup += (f'<a class="noline" href="{symbolpt}" title="{param}">'
                            f'<span class="symbolline">{kwd}</span>'
                            f'<span class="symbol">{sym}</span>'
                            f'<span class="symbolline">{prm}</span>'
                            f'<span class="row">&nbsp;..{row}</span>'
                        '</a><br>')

        symcolor = Pkg.settings.get("symbol_color", "var(--foreground)")
        fontsize = Pkg.settings.get("font_size", 0.95)
        ballooncolor = "#dcf" if completed else "#d77"

        con = (f'<body id="symbolballoon">{_stylesheet(symcolor, fontsize, ballooncolor)}'
                    '<div class="arrow"></div>'
                f'<div class="balloon">{markup}</div></body>')

        vw.add_phantom(Const.KEY_ID,
                       sublime.Region(vpoint),
                       con,
                       sublime.LAYOUT_BELOW,
                       on_navigate=navigate)

        if ignoredpt is not None and Pkg.settings.get("show_ignored_indentation", False):
            vw.add_regions(Const.KEY_ID,
                           [sublime.Region(ignoredpt)],
                           annotations=[_annotation_html()],
                           annotation_color="#aa0",
                           on_navigate=annotation_navigate)


def _annotation_html():
    return ('<body><a style="text-decoration: none" href="">x</a>'
            '　ignored indentation</body>')


def _stylesheet(symbol_color, font_size, balloon_color):
    return f'''
        <style>
            .noline{{
                text-decoration: none;
                font-size: {font_size}rem;
            }}
            .symbol{{
                color: color({symbol_color} a(1.0));
            }}
            .symbolline{{
                color: color(var(--foreground) a(0.7));
            }}
            .row{{
                font-style: italic;
            }}
            .arrow {{
                position: relative;
                    top: 0px;
                border-top: 0.2rem solid transparent;
                border-left: 0.4rem solid color({balloon_color} blend(var(--background) 18%));
                width: 0;
                height: 0;
                .balloon {{
                    position:absolute;
                    display: block;
                    text-decoration: none;
                    background-color: color({balloon_color} blend(var(--background) 18%));
                    padding: 0.1rem 1.2rem 0.1rem 0.3rem;
                    border-radius: 0 0.3rem 0.3rem 0.2rem;
                }}
            }}
        </style>
    '''


class BreakSymbolBalloonCommand(sublime_plugin.TextCommand):

    def run(self, edit):
        self.view.erase_phantoms(Const.KEY_ID)
        if self.view.is_popup_visible():
            self.view.hide_popup()
        if len(self.view.get_regions(Const.KEY_ID)) != 0:
            self.view.erase_regions(Const.KEY_ID)


class ClearCacheCommand(sublime_plugin.TextCommand):

    def run(self, edit):
        Cache.views = ChainMapEx({"id": -1, "change_counter": -1})
