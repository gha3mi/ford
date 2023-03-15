# -*- coding: utf-8 -*-
#
#  graphs.py
#  This file is part of FORD.
#
#  Copyright 2015 Christopher MacMackin <cmacmackin@gmail.com>
#
#  This program is free software; you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation; either version 3 of the License, or
#  (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software
#  Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston,
#  MA 02110-1301, USA.
#
#

import os
import shutil
import re
import copy
import colorsys
import itertools

from graphviz import Digraph

from ford.sourceform import (
    FortranFunction,
    ExternalFunction,
    FortranSubroutine,
    ExternalSubroutine,
    FortranInterface,
    ExternalInterface,
    FortranProgram,
    FortranType,
    ExternalType,
    FortranModule,
    ExternalModule,
    FortranSubmodule,
    FortranSubmoduleProcedure,
    FortranSourceFile,
    FortranBlockData,
)

_coloured_edges = False


def set_coloured_edges(val):
    """
    Public accessor to set whether to use coloured edges in graph or just
    use black ones.
    """
    global _coloured_edges
    _coloured_edges = val


_parentdir = ""


def set_graphs_parentdir(val):
    """
    Public accessor to set the parent directory of the graphs.
    Needed for relative paths.
    """
    global _parentdir
    _parentdir = val


def rainbowcolour(depth, maxd):
    if not _coloured_edges:
        return "#000000"
    (r, g, b) = colorsys.hsv_to_rgb(float(depth) / maxd, 1.0, 1.0)
    return f"#{int(255 * r)}{int(255 * g)}{int(255 * b)}"


HYPERLINK_RE = re.compile(
    r"^\s*<\s*a\s+.*href=(\"[^\"]+\"|'[^']+').*>(.*)</\s*a\s*>\s*$", re.IGNORECASE
)
WIDTH_RE = re.compile('width="(.*?)pt"', re.IGNORECASE)
HEIGHT_RE = re.compile('height="(.*?)pt"', re.IGNORECASE)
EM_RE = re.compile("<em>(.*)</em>", re.IGNORECASE)

graphviz_installed = True


def newdict(old, key, val):
    new = copy.copy(old)
    new[key] = val
    return new


def is_module(obj, cls):
    return isinstance(obj, (FortranModule, ExternalModule)) or issubclass(
        cls, (FortranModule, ExternalModule)
    )


def is_submodule(obj, cls):
    return isinstance(obj, FortranSubmodule) or issubclass(cls, FortranSubmodule)


def is_type(obj, cls):
    return isinstance(obj, (FortranType, ExternalType)) or issubclass(
        cls, (FortranType, ExternalType)
    )


def is_proc(obj, cls):
    return isinstance(
        obj,
        (
            FortranFunction,
            ExternalFunction,
            FortranSubroutine,
            ExternalSubroutine,
            FortranInterface,
            ExternalInterface,
            FortranSubmoduleProcedure,
        ),
    ) or issubclass(
        cls,
        (
            FortranFunction,
            ExternalFunction,
            FortranSubroutine,
            ExternalSubroutine,
            FortranInterface,
            ExternalInterface,
            FortranSubmoduleProcedure,
        ),
    )


def is_program(obj, cls):
    return isinstance(obj, FortranProgram) or issubclass(cls, FortranProgram)


def is_sourcefile(obj, cls):
    return isinstance(obj, FortranSourceFile) or issubclass(cls, FortranSourceFile)


def is_blockdata(obj, cls):
    return isinstance(obj, FortranBlockData) or issubclass(cls, FortranBlockData)


class GraphData(object):
    """
    Contains all of the nodes which may be displayed on a graph.
    """

    def __init__(self):
        self.submodules = {}
        self.modules = {}
        self.types = {}
        self.procedures = {}
        self.programs = {}
        self.sourcefiles = {}
        self.blockdata = {}

    def register(self, obj, cls=type(None), hist=None):
        """
        Takes a FortranObject and adds it to the appropriate list, if
        not already present.
        """
        hist = hist or {}

        if is_submodule(obj, cls):
            if obj not in self.submodules:
                self.submodules[obj] = SubmodNode(obj, self)
        elif is_module(obj, cls):
            if obj not in self.modules:
                self.modules[obj] = ModNode(obj, self)
        elif is_type(obj, cls):
            if obj not in self.types:
                self.types[obj] = TypeNode(obj, self, hist)
        elif is_proc(obj, cls):
            if obj not in self.procedures:
                self.procedures[obj] = ProcNode(obj, self, hist)
        elif is_program(obj, cls):
            if obj not in self.programs:
                self.programs[obj] = ProgNode(obj, self)
        elif is_sourcefile(obj, cls):
            if obj not in self.sourcefiles:
                self.sourcefiles[obj] = FileNode(obj, self)
        elif is_blockdata(obj, cls):
            if obj not in self.blockdata:
                self.blockdata[obj] = BlockNode(obj, self)
        else:
            raise BadType(
                "Object type {} not recognized by GraphData".format(type(obj).__name__)
            )

    def get_node(self, obj, cls=type(None), hist=None):
        """
        Returns the node corresponding to obj. If does not already exist
        then it will create it.
        """
        hist = hist or {}

        if obj in self.modules and is_module(obj, cls):
            return self.modules[obj]
        elif obj in self.submodules and is_submodule(obj, cls):
            return self.submodules[obj]
        elif obj in self.types and is_type(obj, cls):
            return self.types[obj]
        elif obj in self.procedures and is_proc(obj, cls):
            return self.procedures[obj]
        elif obj in self.programs and is_program(obj, cls):
            return self.programs[obj]
        elif obj in self.sourcefiles and is_sourcefile(obj, cls):
            return self.sourcefiles[obj]
        elif obj in self.blockdata and is_blockdata(obj, cls):
            return self.blockdata[obj]
        else:
            self.register(obj, cls, hist)
            return self.get_node(obj, cls, hist)


class BaseNode:
    colour = "#777777"

    def __init__(self, obj):
        self.attribs = {"color": self.colour, "fontcolor": "white", "style": "filled"}
        self.fromstr = type(obj) is str
        self.url = None
        if self.fromstr:
            m = HYPERLINK_RE.match(obj)
            if m:
                self.url = m.group(1)[1:-1]
                self.name = m.group(2)
            else:
                self.name = obj
            self.ident = self.name
        else:
            d = obj.get_dir()
            if not d:
                d = "none"
            self.ident = d + "~" + obj.ident
            self.name = obj.name
            m = EM_RE.search(self.name)
            if m:
                self.name = "<<i>" + m.group(1).strip() + "</i>>"
            self.url = obj.get_url()
        self.attribs["label"] = self.name
        if self.url and getattr(obj, "visible", True):
            if self.fromstr or hasattr(obj, "external_url"):
                self.attribs["URL"] = self.url
            else:
                self.attribs["URL"] = _parentdir + self.url
        self.afferent = 0
        self.efferent = 0

    def __eq__(self, other):
        return self.ident == other.ident

    def __lt__(self, other):
        return self.ident < other.ident

    def __hash__(self):
        """Hash required to insert into dict"""
        return id(self)


class ModNode(BaseNode):
    colour = "#337AB7"

    def __init__(self, obj, gd):
        super().__init__(obj)
        self.uses = set()
        self.used_by = set()
        self.children = set()
        if self.fromstr:
            return
        for u in obj.uses:
            n = gd.get_node(u, FortranModule)
            n.used_by.add(self)
            n.afferent += 1
            self.uses.add(n)
            self.efferent += n.efferent


class SubmodNode(ModNode):
    colour = "#5bc0de"

    def __init__(self, obj, gd):
        super().__init__(obj, gd)
        del self.used_by
        if self.fromstr:
            return
        if obj.parent_submodule:
            self.ancestor = gd.get_node(obj.parent_submodule, FortranSubmodule)
        else:
            self.ancestor = gd.get_node(obj.ancestor_module, FortranModule)
        self.ancestor.children.add(self)
        self.efferent += 1
        self.ancestor.afferent += 1


class TypeNode(BaseNode):
    colour = "#5cb85c"

    def __init__(self, obj, gd, hist=None):
        super().__init__(obj)
        self.ancestor = None
        self.children = set()
        self.comp_types = dict()
        self.comp_of = dict()
        hist = hist or {}
        if self.fromstr:
            return
        if hasattr(obj, "external_url"):
            # Stop following chain, as this object is in an external project
            return

        if obj.extends:
            if obj.extends in hist:
                self.ancestor = hist[obj.extends]
            else:
                self.ancestor = gd.get_node(
                    obj.extends, FortranType, newdict(hist, obj, self)
                )
            self.ancestor.children.add(self)
            self.ancestor.visible = getattr(obj.extends, "visible", True)

        for var in obj.local_variables:
            if (var.vartype == "type" or var.vartype == "class") and var.proto[
                0
            ] != "*":
                if var.proto[0] == obj:
                    n = self
                elif var.proto[0] in hist:
                    n = hist[var.proto[0]]
                else:
                    n = gd.get_node(var.proto[0], FortranType, newdict(hist, obj, self))
                n.visible = getattr(var.proto[0], "visible", True)
                if self in n.comp_of:
                    n.comp_of[self] += ", " + var.name
                else:
                    n.comp_of[self] = var.name
                if n in self.comp_types:
                    self.comp_types[n] += ", " + var.name
                else:
                    self.comp_types[n] = var.name


class ProcNode(BaseNode):
    COLOURS = {"subroutine": "#d9534f", "function": "#d94e8f", "interface": "#A7506F"}

    @property
    def colour(self):
        return ProcNode.COLOURS.get(self.proctype.lower(), super().colour)

    def __init__(self, obj, gd, hist=None):
        # ToDo: Figure out appropriate way to handle interfaces to routines in submodules.
        self.proctype = getattr(obj, "proctype", "")
        super().__init__(obj)
        self.uses = set()
        self.calls = set()
        self.called_by = set()
        self.interfaces = set()
        self.interfaced_by = set()

        hist = hist or {}

        if self.fromstr:
            return
        for u in getattr(obj, "uses", []):
            n = gd.get_node(u, FortranModule)
            n.used_by.add(self)
            self.uses.add(n)
        for c in getattr(obj, "calls", []):
            if getattr(c, "visible", True):
                if c == obj:
                    n = self
                elif c in hist:
                    n = hist[c]
                else:
                    n = gd.get_node(c, FortranSubroutine, newdict(hist, obj, self))
                n.called_by.add(self)
                self.calls.add(n)
        if obj.proctype.lower() == "interface":
            for m in getattr(obj, "modprocs", []):
                if m.procedure and getattr(m.procedure, "visible", True):
                    if m.procedure in hist:
                        n = hist[m.procedure]
                    else:
                        n = gd.get_node(
                            m.procedure, FortranSubroutine, newdict(hist, obj, self)
                        )
                    n.interfaced_by.add(self)
                    self.interfaces.add(n)
            if (
                hasattr(obj, "procedure")
                and obj.procedure.module
                and obj.procedure.module is not True
                and getattr(obj.procedure.module, "visible", True)
            ):
                if obj.procedure.module in hist:
                    n = hist[obj.procedure.module]
                else:
                    n = gd.get_node(
                        obj.procedure.module,
                        FortranSubroutine,
                        newdict(hist, obj, self),
                    )
                n.interfaced_by.add(self)
                self.interfaces.add(n)


class ProgNode(BaseNode):
    colour = "#f0ad4e"

    def __init__(self, obj, gd):
        super().__init__(obj)
        self.uses = set()
        self.calls = set()
        if self.fromstr:
            return
        for u in obj.uses:
            n = gd.get_node(u, FortranModule)
            n.used_by.add(self)
            self.uses.add(n)
        for c in obj.calls:
            if getattr(c, "visible", True):
                n = gd.get_node(c, FortranSubroutine)
                n.called_by.add(self)
                self.calls.add(n)


class BlockNode(BaseNode):
    colour = "#5cb85c"

    def __init__(self, obj, gd):
        super().__init__(obj)
        self.uses = set()
        if self.fromstr:
            return
        for u in obj.uses:
            n = gd.get_node(u, FortranModule)
            n.used_by.add(self)
            self.uses.add(n)


class FileNode(BaseNode):
    colour = "#f0ad4e"

    def __init__(self, obj, gd, hist=None):
        super().__init__(obj)
        self.afferent = set()  # Things depending on this file
        self.efferent = set()  # Things this file depends on
        hist = hist or {}
        if self.fromstr:
            return

        for mod in itertools.chain(
            obj.modules,
            obj.submodules,
            obj.functions,
            obj.subroutines,
            obj.programs,
            obj.blockdata,
        ):
            for dep in mod.deplist:
                if dep.hierarchy[0] == obj:
                    continue
                if dep.hierarchy[0] in hist:
                    n = hist[dep.hierarchy[0]]
                else:
                    n = gd.get_node(
                        dep.hierarchy[0],
                        FortranSourceFile,
                        newdict(hist, obj, self),
                    )
                n.afferent.add(self)
                self.efferent.add(n)


class FortranGraph:
    """
    Object used to construct the graph for some particular entity in the code.
    """

    data = GraphData()
    RANKDIR = "RL"
    _should_add_nested_nodes = False

    def __init__(self, root, webdir="", ident=None):
        """
        Initialize the graph, root is the object or list of objects,
        for which the graph is to be constructed.
        The webdir is the url where the graph should be stored, and
        ident can be provided to override the default identifacation
        of the graph that will be used to construct the name of the
        imagefile. It has to be provided if there are multiple root
        nodes.
        """
        self.root = []  # root nodes
        self.hop_nodes = []  # nodes of the hop which exceeded the maximum
        self.hop_edges = []  # edges of the hop which exceeded the maximum
        self.added = set()  # nodes added to the graph
        self.max_nesting = 0  # maximum numbers of hops allowed
        self.max_nodes = 1  # maximum numbers of nodes allowed
        self.warn = False  # should warnings be written?
        self.truncated = -1  # nesting where the graph was truncated
        try:
            for r in sorted(root):
                self.root.append(self.data.get_node(r))
                self.max_nesting = max(self.max_nesting, int(r.meta["graph_maxdepth"]))
                self.max_nodes = max(self.max_nodes, int(r.meta["graph_maxnodes"]))
                self.warn = self.warn or (r.settings["warn"])
        except TypeError:
            self.root.append(self.data.get_node(root))
            self.max_nesting = int(root.meta["graph_maxdepth"])
            self.max_nodes = max(self.max_nodes, int(root.meta["graph_maxnodes"]))
            self.warn = root.settings["warn"]
        self.webdir = webdir
        if ident:
            self.ident = f"{ident}~~{self.__class__.__name__}"
        else:
            self.ident = f"{root.get_dir()}~~{root.ident}~~{self.__class__.__name__}"
        self.imgfile = self.ident
        self.dot = Digraph(
            self.ident,
            graph_attr={
                "size": "8.90625,1000.0",
                "rankdir": self.RANKDIR,
                "concentrate": "true",
                "id": self.ident,
            },
            node_attr={
                "shape": "box",
                "height": "0.0",
                "margin": "0.08",
                "fontname": "Helvetica",
                "fontsize": "10.5",
            },
            edge_attr={"fontname": "Helvetica", "fontsize": "9.5"},
            format="svg",
            engine="dot",
        )
        # add root nodes to the graph
        for n in self.root:
            if len(self.root) == 1:
                self.dot.node(n.ident, label=n.name)
            else:
                self.dot.node(n.ident, **n.attribs)
            self.added.add(n)
        # add nodes and edges depending on the root nodes to the graph
        self.add_nodes(self.root)

        if graphviz_installed:
            self.svg_src = self.dot.pipe().decode("utf-8")
            self.svg_src = self.svg_src.replace(
                "<svg ", '<svg id="' + re.sub(r"[^\w]", "", self.ident) + '" '
            )
            w = int(WIDTH_RE.search(self.svg_src).group(1))
            if isinstance(self, (ModuleGraph, CallGraph, TypeGraph)):
                self.scaled = w >= 855
            else:
                self.scaled = w >= 641
        else:
            self.svg_src = ""
            self.scaled = False

    def add_to_graph(self, nodes, edges, nesting):
        """
        Adds nodes and edges to the graph as long as the maximum number
        of nodes is not exceeded.
        All edges are expected to have a reference to an entry in nodes.
        If the list of nodes is not added in the first hop due to graph
        size limitations, they are stored in hop_nodes.
        If the graph was extended the function returns True, otherwise the
        result will be False.
        """
        if (len(nodes) + len(self.added)) > self.max_nodes:
            if nesting < 2:
                self.hop_nodes = nodes
                self.hop_edges = edges
            self.truncated = nesting
            return False

        for n in nodes:
            strattribs = {key: str(a) for key, a in n.attribs.items()}
            self.dot.node(n.ident, **strattribs)
        for e in edges:
            if len(e) == 5:
                self.dot.edge(
                    e[0].ident, e[1].ident, style=e[2], color=e[3], label=e[4]
                )
            else:
                self.dot.edge(e[0].ident, e[1].ident, style=e[2], color=e[3])
        self.added.update(nodes)
        return True

    def __str__(self):
        """
        The string of the graph is its HTML representation.
        It will only be created if it is not too large.
        If the graph is overly large but can represented by a single node
        with many dependencies it will be shown as a table instead to ease
        the rendering in browsers.
        """

        graph_as_table = len(self.hop_nodes) > 0 and len(self.root) == 1

        # Do not render empty graphs
        if len(self.added) <= 1 and not graph_as_table:
            return ""

        # Do not render overly large graphs.
        if len(self.added) > self.max_nodes:
            if self.warn:
                print(
                    "Warning: Not showing graph {0} as it would exceed the maximal number of {1} nodes.".format(
                        self.ident, self.max_nodes
                    )
                )
                # Only warn once about this
                self.warn = False
            return ""
        # Do not render incomplete graphs.
        if len(self.added) < len(self.root):
            if self.warn:
                print(
                    "Warning: Not showing graph {0} as it would be incomplete.".format(
                        self.ident
                    )
                )
                # Only warn once about this
                self.warn = False
            return ""

        if self.warn and self.truncated > 0:
            print(
                "Warning: Graph {0} is truncated after {1} hops.".format(
                    self.ident, self.truncated
                )
            )
            # Only warn once about this
            self.warn = False

        zoomName = ""
        svgGraph = ""
        rettext = ""
        if graph_as_table:
            # generate a table graph if maximum number of nodes gets exceeded in
            # the first hop and there is only one root node.
            root = '<td class="root" rowspan="{0}">{1}</td>'.format(
                len(self.hop_nodes) * 2 + 1, self.root[0].attribs["label"]
            )
            if self.hop_edges[0][0].ident == self.root[0].ident:
                key = 1
                root_on_left = self.RANKDIR == "LR"
                if root_on_left:
                    arrowtemp = (
                        '<td class="{0}{1}">{2}</td><td rowspan="2"'
                        + 'class="triangle-right"></td>'
                    )
                else:
                    arrowtemp = (
                        '<td rowspan="2" class="triangle-left">'
                        + '</td><td class="{0}{1}">{2}</td>'
                    )
            else:
                key = 0
                root_on_left = self.RANKDIR == "RL"
                if root_on_left:
                    arrowtemp = (
                        '<td rowspan="2" class="triangle-left">'
                        + '</td><td class="{0}{1}">{2}</td>'
                    )
                else:
                    arrowtemp = (
                        '<td class="{0}{1}">{2}</td><td rowspan="2"'
                        + 'class="triangle-right"></td>'
                    )
            # sort nodes in alphabetical order
            self.hop_edges.sort(key=lambda x: x[key].attribs["label"].lower())
            rows = ""
            for i in range(len(self.hop_edges)):
                e = self.hop_edges[i]
                n = e[key]
                if len(e) == 5:
                    arrow = arrowtemp.format(e[2], "Text", e[4])
                else:
                    arrow = arrowtemp.format(e[2], "Bottom", "w")
                node = '<td rowspan="2" class="node" bgcolor="{0}">'.format(
                    n.attribs["color"]
                )
                try:
                    node += '<a href="{0}">{1}</a></td>'.format(
                        n.attribs["URL"], n.attribs["label"]
                    )
                except KeyError:
                    node += n.attribs["label"] + "</td>"
                if root_on_left:
                    rows += "<tr>" + root + arrow + node + "</tr>\n"
                else:
                    rows += "<tr>" + node + arrow + root + "</tr>\n"
                rows += '<tr><td class="{0}Top">w</td></tr>\n'.format(e[2])
                root = ""
            rettext += '<table class="graph">\n' + rows + "</table>\n"

        # generate svg graph
        else:
            rettext += '<div class="depgraph">{0}</div>'
            svgGraph = self.svg_src
            # add zoom ability for big graphs
            if self.scaled:
                zoomName = re.sub(r"[^\w]", "", self.ident)
                rettext += (
                    "<script>var pan{1} = svgPanZoom('#{1}', "
                    "{{zoomEnabled: true,controlIconsEnabled: true, "
                    "fit: true, center: true,}}); </script>"
                )
        rettext += (
            '<div><a type="button" class="graph-help" '
            'data-toggle="modal" href="#graph-help-text">Help</a>'
            '</div><div class="modal fade" id="graph-help-text" '
            'tabindex="-1" role="dialog"><div class="modal-dialog '
            'modal-lg" role="document"><div class="modal-content">'
            '<div class="modal-header"><button type="button" '
            'class="close" data-dismiss="modal" aria-label="Close">'
            '<span aria-hidden="true">&times;</span></button><h4 class'
            '="modal-title" id="-graph-help-label">Graph Key</h4>'
            '</div><div class="modal-body">{2}</div></div></div>'
            "</div>"
        )
        return rettext.format(svgGraph, zoomName, self.get_key())

    def __nonzero__(self):
        return self.__bool__()

    def __bool__(self):
        return bool(self.__str__())

    @classmethod
    def reset(cls):
        cls.data = GraphData()

    def create_svg(self, out_location):
        if len(self.added) > len(self.root):
            self._create_image_file(os.path.join(out_location, self.imgfile))

    def _create_image_file(self, filename):
        if graphviz_installed:
            self.dot.render(filename, cleanup=False)
            shutil.move(
                filename,
                os.path.join(
                    os.path.dirname(filename), os.path.basename(filename) + ".gv"
                ),
            )

    def add_nodes(self, nodes, nesting=1):
        """Add nodes and edges to this graph, based on the collection ``nodes``

        Subclasses should implement `_add_node`, and optionally
        `_extra_attributes`

        """
        hop_nodes = set()  # nodes in this hop
        hop_edges = []  # edges in this hop

        total_len = len(nodes)

        for i, node in enumerate(nodes):
            colour = rainbowcolour(i, total_len)

            self._add_node(hop_nodes, hop_edges, node, colour)

        if not self.add_to_graph(hop_nodes, hop_edges, nesting):
            return

        self._extra_attributes()

        if self._should_add_nested_nodes:
            self._add_nested_nodes(hop_nodes, nesting)

    def _add_nested_nodes(self, hop_nodes, nesting):
        """Handles nested nodes"""
        if len(hop_nodes) == 0:
            return

        if nesting < self.max_nesting:
            self.add_nodes(hop_nodes, nesting=nesting + 1)
        else:
            self.truncated = nesting

    def _add_node(self, hop_nodes, hop_edges, node, colour):
        """Add a single node and its edges to this graph, typically by
        iterating over parents/children

        """

        raise NotImplementedError

    def _extra_attributes(self):
        """Add any extra attributes to the graph"""
        pass


class ModuleGraph(FortranGraph):
    """Shows the relationship between modules and submodules"""

    def get_key(self):
        colour_notice = COLOURED_NOTICE if _coloured_edges else ""
        return MOD_GRAPH_KEY.format(colour_notice)

    def _add_node(self, hop_nodes, hop_edges, node, colour):
        for nu in node.uses:
            if nu not in self.added:
                hop_nodes.add(nu)
            hop_edges.append((node, nu, "dashed", colour))

        if hasattr(node, "ancestor"):
            if node.ancestor not in self.added:
                hop_nodes.add(node.ancestor)
            hop_edges.append((node, node.ancestor, "solid", colour))

    def _extra_attributes(self):
        self.dot.attr("graph", size="11.875,1000.0")


class UsesGraph(FortranGraph):
    """Graphs how modules use other modules, including ancestor (sub)modules"""

    _should_add_nested_nodes = True

    def get_key(self):
        colour_notice = COLOURED_NOTICE if _coloured_edges else ""
        return MOD_GRAPH_KEY.format(colour_notice)

    def _add_node(self, hop_nodes, hop_edges, node, colour):
        for nu in node.uses:
            if nu not in self.added:
                hop_nodes.add(nu)
            hop_edges.append((node, nu, "dashed", colour))
        if hasattr(node, "ancestor"):
            if node.ancestor not in self.added:
                hop_nodes.add(node.ancestor)
            hop_edges.append((node, node.ancestor, "solid", colour))


class UsedByGraph(FortranGraph):
    """Graphs how modules are used by other modules"""

    _should_add_nested_nodes = True

    def get_key(self):
        colour_notice = COLOURED_NOTICE if _coloured_edges else ""
        return MOD_GRAPH_KEY.format(colour_notice)

    def _add_node(self, hop_nodes, hop_edges, node, colour):
        for nu in getattr(node, "used_by", []):
            if nu not in self.added:
                hop_nodes.add(nu)
            hop_edges.append((nu, node, "dashed", colour))
        for c in getattr(node, "children", []):
            if c not in self.added:
                hop_nodes.add(c)
            hop_edges.append((c, node, "solid", colour))


class FileGraph(FortranGraph):
    """Graphs relationships between source files"""

    def get_key(self):
        colour_notice = COLOURED_NOTICE if _coloured_edges else ""
        return FILE_GRAPH_KEY.format(colour_notice)

    def _add_node(self, hop_nodes, hop_edges, node, colour):
        for ne in node.efferent:
            if ne not in self.added:
                hop_nodes.add(ne)
            hop_edges.append((ne, node, "solid", colour))


class EfferentGraph(FortranGraph):
    """Shows the relationship between the files which this one depends on"""

    _should_add_nested_nodes = True

    def get_key(self):
        colour_notice = COLOURED_NOTICE if _coloured_edges else ""
        return FILE_GRAPH_KEY.format(colour_notice)

    def _add_node(self, hop_nodes, hop_edges, node, colour):
        for ne in node.efferent:
            if ne not in self.added:
                hop_nodes.add(ne)
            hop_edges.append((node, ne, "dashed", colour))


class AfferentGraph(FortranGraph):
    """Shows the relationship between files which depend upon this one"""

    _should_add_nested_nodes = True

    def get_key(self):
        colour_notice = COLOURED_NOTICE if _coloured_edges else ""
        return FILE_GRAPH_KEY.format(colour_notice)

    def _add_node(self, hop_nodes, hop_edges, node, colour):
        for na in node.afferent:
            if na not in self.added:
                hop_nodes.add(na)
            hop_edges.append((na, node, "dashed", colour))


class TypeGraph(FortranGraph):
    """Graphs inheritance and composition relationships between derived types"""

    def get_key(self):
        colour_notice = COLOURED_NOTICE if _coloured_edges else ""
        return TYPE_GRAPH_KEY.format(colour_notice)

    def _add_node(self, hop_nodes, hop_edges, node, colour):
        for keys in node.comp_types.keys():
            if keys not in self.added:
                hop_nodes.add(keys)
        for c in node.comp_types:
            if c not in self.added:
                hop_nodes.add(c)
            hop_edges.append((node, c, "dashed", colour, node.comp_types[c]))
        if node.ancestor:
            if node.ancestor not in self.added:
                hop_nodes.add(node.ancestor)
            hop_edges.append((node, node.ancestor, "solid", colour))

    def _extra_attributes(self):
        self.dot.attr("graph", size="11.875,1000.0")


class InheritsGraph(FortranGraph):
    """Graphs types that this type inherits from"""

    _should_add_nested_nodes = True

    def get_key(self):
        colour_notice = COLOURED_NOTICE if _coloured_edges else ""
        return TYPE_GRAPH_KEY.format(colour_notice)

    def _add_node(self, hop_nodes, hop_edges, node, colour):
        for c in node.comp_types:
            if c not in self.added:
                hop_nodes.add(c)
            hop_edges.append((node, c, "dashed", colour, node.comp_types[c]))
        if node.ancestor:
            if node.ancestor not in self.added:
                hop_nodes.add(node.ancestor)
            hop_edges.append((node, node.ancestor, "solid", colour))


class InheritedByGraph(FortranGraph):
    """Graphs types that inherit this type"""

    _should_add_nested_nodes = True

    def get_key(self):
        colour_notice = COLOURED_NOTICE if _coloured_edges else ""
        return TYPE_GRAPH_KEY.format(colour_notice)

    def _add_node(self, hop_nodes, hop_edges, node, colour):
        for c in node.comp_of:
            if c not in self.added:
                hop_nodes.add(c)
            hop_edges.append((c, node, "dashed", colour, node.comp_of[c]))
        for c in node.children:
            if c not in self.added:
                hop_nodes.add(c)
            hop_edges.append((c, node, "solid", colour))


class CallGraph(FortranGraph):
    """
    Adds edges indicating the call-tree for the procedures listed in
    the nodes.
    """

    RANKDIR = "LR"

    def get_key(self):
        colour_notice = COLOURED_NOTICE if _coloured_edges else ""
        return CALL_GRAPH_KEY.format(colour_notice)

    def _add_node(self, hop_nodes, hop_edges, node, colour):
        for p in node.calls:
            if p not in hop_nodes:
                hop_nodes.add(p)
            hop_edges.append((node, p, "solid", colour))
        for p in getattr(node, "interfaces", []):
            if p not in hop_nodes:
                hop_nodes.add(p)
            hop_edges.append((node, p, "dashed", colour))

    def _extra_attributes(self):
        self.dot.attr("graph", size="11.875,1000.0")
        self.dot.attr("graph", concentrate="false")


class CallsGraph(FortranGraph):
    """Graphs procedures that this procedure calls"""

    RANKDIR = "LR"
    _should_add_nested_nodes = True

    def get_key(self):
        colour_notice = COLOURED_NOTICE if _coloured_edges else ""
        return CALL_GRAPH_KEY.format(colour_notice)

    def _add_node(self, hop_nodes, hop_edges, node, colour):
        for p in node.calls:
            if p not in self.added:
                hop_nodes.add(p)
            hop_edges.append((node, p, "solid", colour))
        for p in getattr(node, "interfaces", []):
            if p not in self.added:
                hop_nodes.add(p)
            hop_edges.append((node, p, "dashed", colour))

    def _extra_attributes(self):
        self.dot.attr("graph", concentrate="false")


class CalledByGraph(FortranGraph):
    """Graphs procedures called by this procedure"""

    RANKDIR = "LR"
    _should_add_nested_nodes = True

    def get_key(self):
        colour_notice = COLOURED_NOTICE if _coloured_edges else ""
        return CALL_GRAPH_KEY.format(colour_notice)

    def _add_node(self, hop_nodes, hop_edges, node, colour):
        if isinstance(node, ProgNode):
            return
        for p in node.called_by:
            if p not in self.added:
                hop_nodes.add(p)
            hop_edges.append((p, node, "solid", colour))
        for p in getattr(node, "interfaced_by", []):
            if p not in self.added:
                hop_nodes.add(p)
            hop_edges.append((p, node, "dashed", colour))

    def _extra_attributes(self):
        self.dot.attr("graph", concentrate="false")


class BadType(Exception):
    """
    Raised when a type is passed to GraphData.register() which is not
    accepted.
    """

    def __init__(self, value):
        self.value = value

    def __str__(self):
        return repr(self.value)


# Generate graph keys
gd = GraphData()


class Proc(object):
    def __init__(self, name, proctype):
        self.name = name
        self.proctype = proctype
        self.ident = ""

    def get_url(self):
        return ""

    def get_dir(self):
        return ""


sub = Proc("Subroutine", "Subroutine")
func = Proc("Function", "Function")
intr = Proc("Interface", "Interface")
gd.register("Module", FortranModule)
gd.register("Submodule", FortranSubmodule)
gd.register("Type", FortranType)
gd.register(sub, FortranSubroutine)
gd.register(func, FortranFunction)
gd.register(intr, FortranInterface)
gd.register("Unknown Procedure Type", FortranSubroutine)
gd.register("Program", FortranProgram)
gd.register("Source File", FortranSourceFile)

try:
    # Generate key for module graph
    dot = Digraph(
        "Graph Key",
        graph_attr={"size": "8.90625,1000.0", "concentrate": "false"},
        node_attr={
            "shape": "box",
            "height": "0.0",
            "margin": "0.08",
            "fontname": "Helvetica",
            "fontsize": "10.5",
        },
        edge_attr={"fontname": "Helvetica", "fontsize": "9.5"},
        format="svg",
        engine="dot",
    )
    for n in [
        ("Module", FortranModule),
        ("Submodule", FortranSubmodule),
        (sub, FortranSubroutine),
        (func, FortranFunction),
        ("Program", FortranProgram),
    ]:
        dot.node(getattr(n[0], "name", n[0]), **gd.get_node(n[0], cls=n[1]).attribs)
    dot.node("This Page's Entity")
    mod_svg = dot.pipe().decode("utf-8")

    # Generate key for type graph
    dot = Digraph(
        "Graph Key",
        graph_attr={"size": "8.90625,1000.0", "concentrate": "false"},
        node_attr={
            "shape": "box",
            "height": "0.0",
            "margin": "0.08",
            "fontname": "Helvetica",
            "fontsize": "10.5",
        },
        edge_attr={"fontname": "Helvetica", "fontsize": "9.5"},
        format="svg",
        engine="dot",
    )
    dot.node("Type", **gd.get_node("Type", cls=FortranType).attribs)
    dot.node("This Page's Entity")
    type_svg = dot.pipe().decode("utf-8")

    # Generate key for call graph
    dot = Digraph(
        "Graph Key",
        graph_attr={"size": "8.90625,1000.0", "concentrate": "false"},
        node_attr={
            "shape": "box",
            "height": "0.0",
            "margin": "0.08",
            "fontname": "Helvetica",
            "fontsize": "10.5",
        },
        edge_attr={"fontname": "Helvetica", "fontsize": "9.5"},
        format="svg",
        engine="dot",
    )
    for n in [
        (sub, FortranSubroutine),
        (func, FortranFunction),
        (intr, FortranInterface),
        ("Unknown Procedure Type", FortranFunction),
        ("Program", FortranProgram),
    ]:
        dot.node(getattr(n[0], "name", n[0]), **gd.get_node(n[0], cls=n[1]).attribs)
    dot.node("This Page's Entity")
    call_svg = dot.pipe().decode("utf-8")

    # Generate key for file graph
    dot = Digraph(
        "Graph Key",
        graph_attr={"size": "8.90625,1000.0", "concentrate": "false"},
        node_attr={
            "shape": "box",
            "height": "0.0",
            "margin": "0.08",
            "fontname": "Helvetica",
            "fontsize": "10.5",
        },
        edge_attr={"fontname": "Helvetica", "fontsize": "9.5"},
        format="svg",
        engine="dot",
    )
    dot.node("Source File", **gd.get_node("Source File", cls=FortranSourceFile).attribs)
    dot.node("This Page's Entity")
    file_svg = dot.pipe().decode("utf-8")

except RuntimeError:
    graphviz_installed = False


if graphviz_installed:
    NODE_DIAGRAM = """
    <p>Nodes of different colours represent the following: </p>
    {}
    """

    MOD_GRAPH_KEY = (
        NODE_DIAGRAM
        + """
    <p>Solid arrows point from a submodule to the (sub)module which it is
    descended from. Dashed arrows point from a module or program unit to 
    modules which it uses.{{}}
    </p>
    """  # noqa W291
    ).format(mod_svg)

    TYPE_GRAPH_KEY = (
        NODE_DIAGRAM
        + """
    <p>Solid arrows point from a derived type to the parent type which it
    extends. Dashed arrows point from a derived type to the other
    types it contains as a components, with a label listing the name(s) of
    said component(s).{{}}
    </p>
    """
    ).format(type_svg)

    CALL_GRAPH_KEY = (
        NODE_DIAGRAM
        + """
    <p>Solid arrows point from a procedure to one which it calls. Dashed 
    arrows point from an interface to procedures which implement that interface.
    This could include the module procedures in a generic interface or the
    implementation in a submodule of an interface in a parent module.{{}}
    </p>
    """  # noqa W291
    ).format(call_svg)

    FILE_GRAPH_KEY = (
        NODE_DIAGRAM
        + """
    <p>Solid arrows point from a file to a file which it depends on. A file
    is dependent upon another if the latter must be compiled before the former
    can be.{{}}
    </p>
    """
    ).format(file_svg)

    COLOURED_NOTICE = (
        " Where possible, edges connecting nodes are given "
        "different colours to make them easier to distinguish "
        "in large graphs."
    )

    del call_svg
    del file_svg
    del type_svg
    del mod_svg
    del dot
    del sub
    del func
    del intr
