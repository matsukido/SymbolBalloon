import sublime

import itertools as itools
import operator as opr
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
        if (idt := min(cm_f, default=99)) < min(cm_t, default=99):
            ignoredpt = cm_f[idt]

        return (Closed(cm_t, cm_f), ignoredpt)


class Cache:
    # views.maps = [{init_dct}, {init_dct}, ...]  masked parents 
    views: ClassVar[ChainMapEx] = ChainMapEx({"id": -1, "change_counter": -1})

    @classmethod
    def query_init(cls, view):

        def init_dct():

            def heading_level(point):
                nonlocal view, syntax

                if syntax == "Markdown":
                    pt = view.line(point).begin()
                    return view.extract_scope(pt).end() - pt

                elif "LaTeX" in syntax:
                    titledct = {"\\part": 0, "\\chapter": 1, "\\section": 2, "\\subsection": 3,
                                "\\subsubsection": 4, "\\paragraph": 5, "\\subparagraph": 6}
                    symline = view.substr(view.line(point)).lstrip()
                    lvl = 0
                    for title, lvl in titledct.items():
                        if title in symline:
                            break
                    else:
                        lvl = 9
                    return lvl
                else:
                    return view.indentation_level(point)

            nonlocal view
            syntax = view.syntax().name
            is_source = view.scope_name(0).startswith("source")

            ignr_symscope = Pkg.settings.get("ignored_symbols", {}).get(syntax, "")

            level = view.indentation_level if is_source else heading_level
            sr = view.symbol_regions()
            
            if sr is None:
                return {"id": view.id(), "change_counter": -1,
                        "symbol_point": (), "symbol_level": ()}
            elif sr == []:
                return {"id": view.id(), "change_counter": view.change_count(), 
                        "symbol_point": (), "symbol_level": ()}

            tpls = map(opr.attrgetter("name", "region", "kind"), sr)
            if ignr_symscope:                    
                tpls = (tpl  for tpl in tpls  
                                if not view.match_selector(tpl[1].begin(), ignr_symscope))

            names, regions, kinds = zip(*tpls)
            a_pts, b_pts = zip(*regions)
            ids, letters, _ = zip(*kinds)

            levels = array.array("B", map(level, a_pts))

            dcts = ({lvl + 1: pt}  for lvl, pt in zip(levels, a_pts))
            closes = map(Closed, map(ChainMapEx, dcts))
            # closed.false=ChainMapEx({})
            
            return {
                "id": view.id(),
                "symbol_point": tuple(a_pts),
                "symbol_end_point": tuple(b_pts),
                "scanned_point": list(a_pts),
                "symbol_level": levels,
                "symbol_name": tuple(names),
                "closed": list(closes),
                "symbol_kind": (array.array("B", ids), tuple(letters), ("", )),

                "size": view.size(),
                "change_counter": view.change_count(),
            }

        cls.views.move_to_child(lambda dct: dct["id"] == view.id(), init_dct)

        if cls.views["change_counter"] != view.change_count():
            cls.views.update(init_dct())
            return True
            
        return False

    @classmethod
    def sectional_view(cls, visible_point):

        def to_symbol_region(tpl, syntax="", typ=1, kind=(0, "", "")):
            name, a_pt, b_pt = tpl
            sr = sublime.SymbolRegion(name, sublime.Region(a_pt, b_pt), syntax, typ, kind)
            return sr


        curr_idx = bisect.bisect_left(cls.views["symbol_point"], visible_point) - 1
        if curr_idx < 0:
            return ({}, None)

        reverse = slice(curr_idx, None, -1)
        idtlvls = cls.views["symbol_level"][reverse]

        closes = cls.views["closed"][reverse]
        if not closes:
            return ({}, None)

        section, ignoredpt = closes[0].cut(visible_point)
        closes[0] = section

        cl_lvls = (min(cl.true.keys())  for cl in closes)
        ac_sym = itools.accumulate(idtlvls, func=min)
        ac_cls = itools.accumulate(cl_lvls, func=min)

        zp = zip(ac_sym, ac_cls, range(curr_idx, -1, -1))
        grp = itools.groupby(zp, key=opr.itemgetter(0))

        tpls = (next(itr)  for _lvl, itr in grp)
        indices = [idx  for symlvl, closelvl, idx in tpls  if symlvl < closelvl]

        visible_symbol = {}
        for idx in reversed(indices):
            symrgn = to_symbol_region((cls.views["symbol_name"][idx],
                                       cls.views["symbol_point"][idx], 
                                       cls.views["symbol_end_point"][idx]))

            visible_symbol.update({cls.views["symbol_level"][idx]: symrgn})
      
        return (visible_symbol, ignoredpt)