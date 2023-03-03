import sublime
import sublime_plugin

import html
import re
import itertools
import collections
import operator as opr
import dataclasses as dcls
import bisect
import array
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

    def limit_filter(self, limit):
        return {k: v  for k, v in self.items() if v < limit}

    def fill(self, stop):
        # {2: 45, 4: 66}.fill(6) --> {2: 45, 3: -1, 4: 66, 5: -1}
        dct = {i: -1  for i in range(min(self, default=0), stop)}
        cm = ChainMapEx(self)
        cm.appendflat(dct)
        return cm

    def move_to_child(self, pred, init_factory):
        dq = collections.deque(self.maps, maxlen=50)
        # or None
        if not any(pred(dq[0]) or dq.rotate()  for _ in range(len(dq))):
            dq.appendleft(init_factory())

        self.maps = list(dq)


@dcls.dataclass(eq=False)
class Closed:
    # true.maps = [{indentation_level: min(points), ...}]   no parents
    true: ChainMapEx = dcls.field(default_factory=ChainMapEx)
    false: ChainMapEx = dcls.field(default_factory=ChainMapEx)

    def appendflat(self, closed):
        self.true.appendflat(closed.true)
        self.false.appendflat(closed.false)

    def cut(self, visible_point):
        dct_t = self.true.limit_filter(visible_point)
        dct_f = self.false.limit_filter(visible_point)

        ignoredpt = -1
        if (idt := min(dct_f, default=99)) < min(dct_t):
            ignoredpt = dct_f[idt]

        return Closed(ChainMapEx(dct_t), ChainMapEx(dct_f)), ignoredpt


class Cache:
    # views.maps = [{init_dct}, {init_dct}, ...]  masked parents 
    views:  ClassVar[ChainMapEx] = ChainMapEx({"id": -1, "change_counter":-1})
    busy: ClassVar[bool] = False

    @classmethod
    def query_init(cls, view):

        def init_dct():

            def heading_level(point):
                nonlocal view
                pt = view.line(point).begin()
                return view.extract_scope(pt).end() - pt

            nonlocal view
            is_source = "Markdown" not in view.syntax().name
            level = view.indentation_level if is_source else heading_level

            Symbol = collections.namedtuple("Symbol", ["region", "name"])
            syminfos = (Symbol(info.region, info.name)
                                    for info in view.symbol_regions())
            
            rgn_a_pts = array.array("L")
            scanned_pts = array.array("L")
            sym_levels = array.array("B")
            sym_infos = []
            closes = []

            for info in syminfos:
                rgna = info.region.a
                rgn_a_pts.append(rgna)
                scanned_pts.append(rgna)

                idt = level(rgna)
                sym_levels.append(idt)
                sym_infos.append(info)

                clos =  Closed()
                clos.true.appendflat({idt + 1: rgna})
                closes.append(clos)

            rgn_a_pts.append(view.size())

            return {
                "id": view.id(),
                "region_a": rgn_a_pts,
                "scanned_point": scanned_pts,
                "symbol_level": sym_levels,
                "symbol_info": sym_infos,
                "closed": closes,
                "change_counter": view.change_count()
            }

        cls.views.move_to_child(lambda dct: dct["id"] == view.id(), init_dct)

        if cls.views["change_counter"] != view.change_count() or \
                                        not cls.views["symbol_info"]:
            cls.views.maps[0] = init_dct()

    @classmethod
    def sectional_view(cls, visible_point):
        idx = bisect.bisect_left(cls.views["region_a"], visible_point) - 1
        if idx < 0:
            return {}, -1

        reverse = slice(idx, None, -1)
        idtlvls = cls.views["symbol_level"][reverse]
        idtlvls.append(0)
        stopper = range(idtlvls.index(0) + 1)

        sym_infos = cls.views["symbol_info"][reverse]
        closes = cls.views["closed"][reverse]
        if not closes:
            return {}, -1

        sym_dct = ({idt: info}  for idt, info, _ in zip(idtlvls, sym_infos, stopper))

        section, ignoredpt = closes[0].cut(visible_point)
        closes[0] = section
        shutter = (cl.true.fill(12)  for cl in closes)

        hiding = itertools.chain.from_iterable(zip(shutter, sym_dct))

        visible_idtlvl = dict(ChainMapEx(*hiding))
        visible_symbol = {idt: info  for idt, info in visible_idtlvl.items()
                                                if not isinstance(info, int)}
        return visible_symbol, ignoredpt

    @classmethod
    def reset_busy(cls):
        cls.busy = False


class SymbolBalloonListner(sublime_plugin.EventListener):

    def on_activated_async(self, view):
        Cache.query_init(view)

    def on_pre_close(self, view):
        del Cache.views.maps[0]


def scan_manager(scanlines):

    def _scan_manager_(view, region):

        rgn_a, visible_pt = region.to_tuple()
        region_a_pts = Cache.views["region_a"]

        idx = region_a_pts.index(rgn_a)
        rgnas = itertools.takewhile(lambda pt: pt < visible_pt, 
                                                region_a_pts[idx:])
        for rgna in rgnas:
            scpt = Cache.views["scanned_point"][idx]
            delta_rgn = sublime.Region(scpt, region_a_pts[idx + 1])
            start_row = 2 if rgna == scpt else 0
            target_indentlevel = Cache.views["symbol_level"][idx] + 1

            new_scannedpt, closed = scanlines(view, 
                                              delta_rgn,
                                              target_indentlevel,
                                              start_row)

            Cache.views["scanned_point"][idx] = new_scannedpt
            Cache.views["closed"][idx].appendflat(closed)
            idx += 1

    return _scan_manager_


@scan_manager
def scan_lines(view, region, target_indentlevel, start_row=0):

    def indentendpoint(indentlevel, point: 'Linestart point'):
        nonlocal view
        # 1 | 4 | 128   WORD_START | PUNCTUATION_START | LINE_END 
        return view.find_by_class(point, True, 133) if indentlevel else point

    def isnot_ignored(point):
        nonlocal view
        ignr = Pkg.settings.get("ignored_characters", "") + "\n"
        return view.substr(point) not in ignr and \
                not view.match_selector(point, Pkg.settings.get("ignored_scope", "_"))

    closed = Closed()
    linestart_pts = (lrgn.a  for lrgn in view.lines(region)
                        [start_row:Pkg.settings.get("max_scan_lines", 2000)]
                                            if not lrgn.empty())
    pt = region.a
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
        stt = time.perf_counter_ns()
        vw = self.view
        if Cache.busy:
            return
        Cache.busy = True

        sublime.set_timeout(Cache.reset_busy, 5)
        Cache.query_init(vw)
        Pkg.init_settings()

        vpoint = vw.visible_region().begin()
        offset = Pkg.settings.get("row_offset", 0)
        vpoint = vw.text_point(vw.rowcol(vpoint)[0] + offset, 0)

        is_source = "Markdown" not in vw.syntax().name
        rgn_a = opr.attrgetter("region.a")

        # {indentation_level: Symbol, ...}
        visible_symbol, _ = Cache.sectional_view(vpoint + 1)
        if not visible_symbol:
            return

        most_far = min(map(rgn_a, visible_symbol.values())) 
        if is_source:
            scan_lines(vw, sublime.Region(most_far, vpoint + 1))
            visible_symbol, ignoredpt = Cache.sectional_view(vpoint + 1)

        else:
            ignoredpt = -1

        symbol_infos = [*visible_symbol.values()]
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
        