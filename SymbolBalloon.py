import sublime
import sublime_plugin

import html
import re
import itertools
import collections
import operator as opr
import dataclasses as dcls
from typing import ClassVar


@dcls.dataclass(init=False, eq=False, frozen=True)
class Const:

    KEY_ID: ClassVar[str] = "SymbolBalloon"


class Pkg:

    settings: ClassVar[object] = None

    @classmethod
    def init_settings(cls):
        if cls.settings is None:
            cls.settings = sublime.load_settings("SymbolBalloon.sublime-settings")
            cls.settings.add_on_change(Const.KEY_ID, cls.init_settings)


class ChainMapEx(collections.ChainMap):

    def appendflat(self, mapping):
        self.maps.append(mapping)     # setdefault
        self.maps = [dict(self.items())]

    def limit_max(self, limit):
        # {3:10, 2:40, 1:70}.limit_max(50) --> (2, 40)
        val = opr.itemgetter(1)
        return max((kv  for kv in self.items() if val(kv) < limit), key=val)

    def move_to_child(self, pred, init_factory):
        dq = collections.deque(self.maps, 80)
        # or None
        if not any(pred(dq[0]) or dq.rotate()  for _ in range(len(dq))):
            dq.appendleft(init_factory())

        self.maps = list(dq)


@dcls.dataclass(eq=False)
class Closed:
    # true.maps = [{indentation_level: min(points), ...}]   no parents
    true: ChainMapEx = dcls.field(default_factory=ChainMapEx)
    false: ChainMapEx = dcls.field(default_factory=ChainMapEx)

    def append(self, closed):
        self.true.appendflat(closed.true)
        self.false.appendflat(closed.false)

    def query(self, visible_point):
        min_idt, _ = self.true.limit_max(visible_point)
        idt, pt = self.false.limit_max(visible_point)

        ignoredpt = -1
        if (idt < min_idt) or (idt == min_idt == 0):
            ignoredpt = pt

        return min_idt, ignoredpt


class Cache:
    # views.maps = [{init_dct}, {init_dct}, ...]  masked parents 
    views:  ClassVar[ChainMapEx] = ChainMapEx({"id": -1, "change_counter":-1})
    busy = False

    @classmethod
    def query_init(cls, view):

        def filtered(symbol_regions):
            Symbol = collections.namedtuple("Symbol", ["name", "region"])
            return [Symbol(sym.name, sym.region)  for sym in symbol_regions]

        init_dct = lambda: {
            "id": view.id(),
            "symbol_regions": filtered(view.symbol_regions()),
            "symbol": {},       # {symbol_region_a: [scannedpt, Closed], ...}
            "change_counter": view.change_count()
        }
        cls.views.move_to_child(lambda dct: dct["id"] == view.id(), init_dct)

        if cls.views["change_counter"] < view.change_count() or \
                                        not cls.views["symbol_regions"]:
            cls.views.maps[0] = init_dct()

    @classmethod
    def reset_busy(cls):
        cls.busy = False


class SymbolBalloonListner(sublime_plugin.EventListener):

    def on_activated_async(self, view):
        Cache.query_init(view)

    def on_pre_close(self, view):
        del Cache.views.maps[0]


def cache_manager(scanlines):

    def _cache_manager_(view, region, target_indentlevel):

        rgn_a, visible_pt = region.to_tuple()

        symbol_region_a = Cache.views["symbol"].get(rgn_a, [-1, -1])

        if symbol_region_a[0] == -1:    # scannedpt == -1

            scannedpt, closed = scanlines(view, region, target_indentlevel, 2)
            Cache.views["symbol"][rgn_a] = [scannedpt, closed]

        else:
            scannedpt = symbol_region_a[0]

            if scannedpt < visible_pt:
                delta_rgn = sublime.Region(scannedpt, visible_pt)
                new_scannedpt, closed = scanlines(view,
                                                    delta_rgn,
                                                    target_indentlevel)
                Cache.views["symbol"][rgn_a][0] = new_scannedpt
                Cache.views["symbol"][rgn_a][1].append(closed)

        return dcls.replace(Cache.views["symbol"][rgn_a][1])  # copied Closed

    return _cache_manager_


@cache_manager
def scan_lines(view, region, target_indentlevel, start_row=0):

    def indentendpoint(indentlevel, point: 'Linestart point'):
        # 1 | 4 | 128   WORD_START | PUNCTUATION_START | LINE_END 
        return view.find_by_class(point, True, 133) if indentlevel else point

    def isnot_ignored(point):
        ignr = Pkg.settings.get("ignored_characters", "") + "\n"
        return view.substr(point) not in ignr and \
                not view.match_selector(point, Pkg.settings.get("ignored_scope", "_"))

    closed = Closed()
    if start_row == 2:
        closed.true.update({target_indentlevel: region.a})
        closed.false.update({target_indentlevel: -1})

    linestart_pts = (lrgn.a  for lrgn in view.lines(region)
                        [start_row:Pkg.settings.get("max_scan_lines", 3000)]
                                            if not lrgn.empty())
    pt = -1
    for pt in linestart_pts:
        if (idt := view.indentation_level(pt)) < target_indentlevel:
            if isnot_ignored(indentendpoint(idt, pt)):
                closed.true.setdefault(idt, pt)
            else:
                closed.false.setdefault(idt, pt)

    return pt, closed


class RaiseSymbolBalloonCommand(sublime_plugin.TextCommand):

    def run(self, edit):
        
        def navigate(href):
            self.view.show(int(href),
                            show_surrounds=False,
                            animate=True,
                            keep_to_left=True)

        def annotation_navigate(href):
            self.view.erase_regions(Const.KEY_ID)

        def heading_level(point: "Linestart point"):
            return self.view.extract_scope(point).b - point

        vw = self.view
        if Cache.busy:
            return
        Cache.busy = True
        sublime.set_timeout(Cache.reset_busy, 0.3)  # seconds
        Cache.query_init(vw)
        Pkg.init_settings()

        vpoint = vw.visible_region().begin()
        offset = Pkg.settings.get("row_offset", 0)
        vpoint = vw.text_point(vw.rowcol(vpoint)[0] + offset, 0)

        is_source = "Markdown" not in vw.syntax().name
        level = vw.indentation_level if is_source else heading_level
        rgn_a = opr.attrgetter("region.a")

        symbol_infos = itertools.takewhile(lambda sym: rgn_a(sym) < vpoint,
                                                Cache.views["symbol_regions"])
        symbol_dct = {(lastlvl := level(rgn_a(sym))): sym
                                        for sym in symbol_infos}
        if not symbol_dct:
            return

        if is_source:
            rgn = sublime.Region(rgn_a(symbol_dct[lastlvl]), vpoint + 1)
            closed = scan_lines(vw, rgn, target_indentlevel=lastlvl + 1)
            threshold, ignoredpt = closed.query(vpoint + 1)

        else:
            is_heading = vw.match_selector(vpoint, "markup.heading")
            target_idt = level(vpoint) if is_heading else 99
            threshold, ignoredpt = min(lastlvl + 1, target_idt), -1

        symbol_infos = [sym  for idt, sym in symbol_dct.items() if idt < threshold]
        if not symbol_infos:
            return

        vw.run_command("break_symbol_balloon")
        symbol_infos.sort(key=rgn_a)
        markup = ""
        is_param = ("meta.function.parameters | meta.class.parameters "
                    "| meta.class.inheritance | meta.method.parameters")
        tabsize = int(vw.settings().get('tab_size', 8))
        
        for symbol in symbol_infos:

            symbolpt = rgn_a(symbol)
            symbolpt_b = symbol.region.b
            prm_max = symbolpt_b + 1500

            prm_a = itertools.dropwhile(lambda pnt:
                        opr.xor(
                            vw.match_selector(pnt, is_param),
                            vw.match_selector(pnt, "meta.function | meta.class")
                        ), range(symbolpt_b, prm_max))
            try:
                prm_begin = next(prm_a)
                prm_b = itertools.dropwhile(lambda pnt:
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

        symcolor = Pkg.settings.get("symbol_color", "foreground")

        con = (f'<body id="symbolballoon">{_stylesheet(symcolor)}'
                    '<div class="arrow"></div>'
                f'<div class="balloon">{markup}</div></body>')

        if Pkg.settings.get("popup_mode", False):
            vw.show_popup(con,
                          max_width=800,
                          location=vpoint,
                          on_hide=True,
                          on_navigate=navigate)
        else:
            vw.add_phantom(Const.KEY_ID,
                           sublime.Region(vpoint),
                           con,
                           sublime.LAYOUT_BELOW,
                           on_navigate=navigate)

        if 0 < ignoredpt and Pkg.settings.get("show_ignored_indentation", False):
            vw.add_regions(Const.KEY_ID,
                           [sublime.Region(ignoredpt)],
                           annotations=[_annotation_html()],
                           annotation_color="#aa0",
                           on_navigate=annotation_navigate)


def _annotation_html():
    return ('<body><a style="text-decoration: none" href="">x</a>'
            '　ignored indentation</body>')


def _stylesheet(symbol_color):
    return f'''
        <style>
            .noline{{
                text-decoration: none;
                font-size: 0.95rem;
            }}
            .symbol{{
                color: color(var(--{symbol_color}) a(1.0));
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
                border-left: 0.4rem solid color(#dcf blend(var(--background) 18%));
                width: 0;
                height: 0;
                .balloon {{
                    position:absolute;
                    display: block;
                    text-decoration: none;
                    background-color: color(#dcf blend(var(--background) 18%));
                    padding: 0.1rem 1.2rem 0.1rem 0.4rem;
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
        Cache.views = ChainMapEx({"id": -1, "change_counter":-1})
        