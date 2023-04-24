import sublime

import itertools as itools
import collections
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
            cls.settings = sublime.load_settings("symbol_balloon.sublime-settings")
            cls.settings.add_on_change(Const.KEY_ID, cls.init_settings)


class ChainMapEx(collections.ChainMap):

    def appendflat(self, mapping):
        self.maps.append(mapping)     # setdefault
        self.maps = [dict(self.items())]

    def limit_filter(self, limit):
        return ChainMapEx({k: v  for k, v in self.items() if v < limit})

    def fill(self, stop):
        # {3: 44, 1: 77}.fill(6) --> {2: -1, 3: 44, 4: -1, 5: -1, 1: 77}
        dct = {i: -1  for i in range(min(self, default=99) + 1, stop)}
        cm = ChainMapEx(self)
        cm.appendflat(dct)
        return cm

    def move_to_child(self, pred, init_factory):
        dq = collections.deque(self.maps[:50], maxlen=50)
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
        cm_t = self.true.limit_filter(visible_point)
        cm_f = self.false.limit_filter(visible_point)

        ignoredpt = None
        if (idt := min(cm_f, default=99)) < min(cm_t):
            ignoredpt = cm_f[idt]

        return Closed(cm_t, cm_f), ignoredpt


class Cache:
    # views.maps = [{init_dct}, {init_dct}, ...]  masked parents 
    views: ClassVar[ChainMapEx] = ChainMapEx({"id": -1, "change_counter": -1})

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

            Symbol = collections.namedtuple("Symbol", ["region", "name", "kind"])
            syminfos = (Symbol(info.region, info.name, info.kind)
                                    for info in view.symbol_regions())
            
            rgn_a_pts = array.array("L")
            scanned_pts = array.array("L")
            sym_levels = array.array("B")
            sym_infos = []
            closes = []
            using_tab = False

            for info in syminfos:
                rgna = info.region.a
                rgn_a_pts.append(rgna)
                scanned_pts.append(rgna)

                idt = level(rgna)
                if 0 < idt:
                    if view.substr(view.line(rgna))[0] == "\t":
                        using_tab = True 
                sym_levels.append(idt)
                sym_infos.append(info)

                clos = Closed()
                clos.true.appendflat({idt + 1: rgna})
                closes.append(clos)

            rgn_a_pts.append(view.size())

            return {
                "id": view.id(),
                "symbol_point": rgn_a_pts,
                "scanned_point": scanned_pts,
                "symbol_level": sym_levels,
                "symbol_info": sym_infos,
                "closed": closes,
                "change_counter": view.change_count(),
                "using_tab": using_tab
            }

        cls.views.move_to_child(lambda dct: dct["id"] == view.id(), init_dct)

        if cls.views["change_counter"] != view.change_count() or \
                                        not cls.views["symbol_info"]:
            cls.views.maps[0] = init_dct()

    @classmethod
    def sectional_view(cls, visible_point):
        idx = bisect.bisect_left(cls.views["symbol_point"], visible_point) - 1
        if idx < 0:
            return ({}, None)

        reverse = slice(idx, None, -1)
        idtlvls = cls.views["symbol_level"][reverse]
        toplvl = min(idtlvls)
        stopper = range(idtlvls.index(toplvl) + 1)

        sym_infos = cls.views["symbol_info"][reverse]
        closes = cls.views["closed"][reverse]
        if not closes:
            return ({}, None)

        sym_dcts = ({idt: info}  for idt, info, _ in zip(idtlvls, sym_infos, stopper))

        section, ignoredpt = closes[0].cut(visible_point)
        closes[0] = section
        shutters = (cl.true.fill(15)  for cl in closes)

        hiding = itools.chain.from_iterable(zip(shutters, sym_dcts))

        visible_idtlvl = dict(ChainMapEx(*hiding))
        visible_symbol = {idt: info  for idt, info in visible_idtlvl.items()
                                                if not isinstance(info, int)}
        return visible_symbol, ignoredpt

