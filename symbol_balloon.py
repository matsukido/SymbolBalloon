import sublime
import sublime_plugin

import html
import re
import itertools as itools
import functools as ftools
import operator as opr
import math

from .sub.containers import Const, Pkg, ChainMapEx, Closed, Cache
from .sub.byproducts import FTOCmd, GTLSCmd, MOCmd


def plugin_loaded():
    Pkg.init_settings()


class SymbolBalloonListner(sublime_plugin.ViewEventListener):
    is_panel = False

    def on_activated_async(self):
        if self.view.syntax() is None:
            return
        if self.view.element() is None:
            if not self.is_panel:
                Cache.query_init(self.view)
            self.is_panel = False
        else:
            self.is_panel = True

    def on_pre_close(self):
        Cache.views.move_to_child(lambda dct: dct["id"] == self.view.id(),
                                  lambda: {"id": -1})
        del Cache.views.maps[0]

    def on_hover(self, point, hover_zone):
        if (hover_zone == sublime.HOVER_GUTTER or 
                        Pkg.settings.get("mini_outline", "none") == "none"):
            return
        vw = self.view
        vrgn = vw.visible_region()
        _, vis = vw.text_to_layout(vrgn.begin())
        lh = vw.line_height()

        _, viewport = vw.viewport_extent()
        _, mouse = vw.text_to_layout(point)

        if vis - lh < mouse < vis + viewport * 0.18:
            curr = vw.layout_to_text((0, vis + max(lh, viewport * 0.13)))
            tgt = vw.layout_to_text((0, vis + viewport * 0.18))

            vw.run_command("mini_outline", args={ "current": curr, "target": tgt })


def scan_manager(scanlines):

    def _scan_manager_(view, start_point, end_point):

        stopper = itools.repeat(True, Pkg.settings.get("max_scan_lines", 20000))

        sym_pts = Cache.views["symbol_point"] + (Cache.views["size"], )
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
            fline = fullline.expandtabs(tabsize)
            topchr = fline.lstrip()[0:1]
            idtwidth = fline.index(topchr)
            idtlvl = math.ceil(idtwidth / tabsize)
            if tgtlvl < idtlvl:
                continue
            idtwidth = fullline.index(topchr)

        if topchr in ignrchr or view.match_selector(pt + idtwidth, ignrscope):
            closed.false.setdefault(idtlvl, pt)

        else:
            closed.true.setdefault(idtlvl, pt)
            tgtlvl = idtlvl - 1
            if tgtlvl < 0:
                break

    return (pt, closed)


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
        is_source = vw.scope_name(0).startswith("source")

        if is_source:
            completed = scan_lines(vw, top_level_pt, vpoint + 1)
            visible_symbol, ignoredpt = Cache.sectional_view(vpoint + 1)

        else:
            visible_symbol, _ = Cache.sectional_view(vpoint + 1)
            ignoredpt = None
            completed = True

        if not visible_symbol:
            return
        symbol_infos = [*visible_symbol.values()]

        vw.run_command("break_symbol_balloon")
        markup = ""
        is_param = ("meta.function.parameters | meta.class.parameters "
                    "| meta.class.inheritance | meta.method.parameters")
        is_def = "meta.function | meta.class | meta.section.latex"
        
        tabsize = int(vw.settings().get('tab_size', 8))
        symcolor = Pkg.settings.get("symbol_color", "var(--foreground)")
        to_html = ftools.partial(vw.export_to_html, 
                                 minihtml=True, enclosing_tags=False, 
                                 font_size=False, font_family=False)
        preds = [
            lambda pt: vw.match_selector(pt, is_param) ^ vw.match_selector(pt, is_def),
            lambda pt: vw.match_selector(pt, is_param)]

        for symbol in symbol_infos:

            symbolpt = symbol.region.a
            symbolpt_b = symbol.region.b
            prm_max = symbolpt_b + 1500
            itrng = iter(range(symbolpt_b, prm_max))

            drops = map(itools.dropwhile, preds, [itrng] * 2)
            param = vw.substr(sublime.Region(*map(next, drops, [prm_max] * 2)))
            param = re.sub(r'^[ \t]+', ' ', param, flags=re.MULTILINE)
            param = html.escape(param, quote=True).expandtabs(tabsize).replace(" ",  "&nbsp;")

            row = vw.rowcol(symbolpt)[0] + 1
            
            linergn = vw.line(symbolpt)

            if is_source:
                symname = symbol.name
            else:
                rgns, scps = zip(*vw.extract_tokens_with_scopes(linergn))
                nmrgns = itools.compress(rgns, map(lambda scp: "entity.name" in scp, scps))
                symname = "".join(map(vw.substr, nmrgns))

            if symcolor == "color_scheme":
                kwd, sym, prm = to_html(linergn), "", ""
            else:
                kwd, sym, prm = vw.substr(linergn).partition(symname or "---")

                kwd, sym, prm, param = map(lambda st:
                    html.escape(st).expandtabs(tabsize).replace(" ",  "&nbsp;"),
                    (kwd, sym, prm, param))
            
            markup += (f'<a class="noline" href="{symbolpt}" title="{param}">'
                            f'<span class="symbolline">{kwd}</span>'
                            f'<span class="symbol">{sym}</span>'
                            f'<span class="symbolline">{prm}</span>'
                            f'<span class="row">&nbsp;..{row}</span>'
                        '</a><br>')

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


class FoldToOutlineCommand(FTOCmd):
    pass


class GotoTopLevelSymbolCommand(GTLSCmd):
    pass


class MiniOutlineCommand(MOCmd):

    def run(self, edit, current, target):

        vw = self.view
        update = Cache.query_init(vw)
        if not Cache.views["symbol_point"]:
            return
        vpt = vw.full_line(vw.visible_region().begin()).end()
        tgtrgn = sublime.Region(vpt, target)
        rgns = vw.get_regions("MiniOutline")

        if update or not (rgns and tgtrgn.contains(rgns[0])):

            completed = True
            if vw.scope_name(0).startswith("source"):
                completed = scan_lines(vw, Cache.views["symbol_point"][0], current)

            self.do(current, Pkg.settings.get("mini_outline", "symbol"), completed)