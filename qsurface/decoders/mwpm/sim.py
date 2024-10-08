from typing import List, Tuple
from qsurface.codes.elements import AncillaQubit
from .._template import Sim
import networkx as nx
from numpy.ctypeslib import ndpointer
import ctypes
import os
import matplotlib.pyplot as plt
import numpy as np
from itertools import chain

LA = List[AncillaQubit]


class Toric(Sim):
    """Minimum-Weight Perfect Matching decoder for the toric lattice.

    Parameters
    ----------
    args, kwargs
        Positional and keyword arguments are passed on to `.decoders._template.Sim`.
    """

    name = "Minimum-Weight Perfect Matching"
    short = "mwpm"

    compatibility_measurements = dict(
        PerfectMeasurements=True,
        FaultyMeasurements=False,
    )
    compatibility_errors = dict(
        pauli=True,
        erasure=True,
    )

    def decode(self, **kwargs):
        # Inherited docstring
        plaqs, stars = self.get_syndrome()
        self.correct_matching(plaqs, self.match_syndromes(plaqs, **kwargs))
        self.correct_matching(stars, self.match_syndromes(stars, **kwargs))

    def match_syndromes(self, syndromes: LA, use_blossomv: bool = False, **kwargs) -> list:
        """Decodes a list of syndromes of the same type.

        A graph is constructed with the syndromes in ``syndromes`` as nodes and the distances between each of the syndromes as the edges. The distances are dependent on the boundary conditions of the code and is calculated by `get_qubit_distances`. A minimum-weight matching is then found by either `match_networkx` or `match_blossomv`.

        Parameters
        ----------
        syndromes
            Syndromes of the code.
        use_blossomv
            Use external C++ Blossom V library for minimum-weight matching. Needs to be downloaded and compiled by calling `.get_blossomv`.

        Returns
        -------
        list of `~.codes.elements.AncillaQubit`
            Minimum-weight matched ancilla-qubits.

        """
        matching_graph = self.match_blossomv if use_blossomv else self.match_networkx
        edges = self.get_qubit_distances(syndromes, self.code.size)
        matching = matching_graph(
            edges,
            maxcardinality=self.config["max_cardinality"],
            num_nodes=len(syndromes),
            **kwargs,
        )
        return matching

    def correct_matching(self, syndromes: LA, matching: list, **kwargs):
        """Applies the matchings as a correction to the code."""
        weight = 0
        for i0, i1 in matching:
            weight += self._correct_matched_qubits(syndromes[i0], syndromes[i1])
        return weight

    @staticmethod
    def match_networkx(edges: list, maxcardinality: float, **kwargs) -> list:
        """Finds the minimum-weight matching of a list of ``edges`` using `networkx.algorithms.matching.max_weight_matching`.

        Parameters
        ----------
        edges :  [[nodeA, nodeB, distance(nodeA,nodeB)],...]
            A graph defined by a list of edges.
        maxcardinality
            See `networkx.algorithms.matching.max_weight_matching`.

        Returns
        -------
        list
            Minimum weight matching in the form of [[nodeA, nodeB],..].
        """
        nxgraph = nx.Graph()
        for i0, i1, weight in edges:
            nxgraph.add_edge(i0, i1, weight=-weight)

        # # visualize for debugging
        # plt.figure()
        # pos = nx.spring_layout(nxgraph)
        # nx.draw(nxgraph, pos, with_labels=True)
        # labels = nx.get_edge_attributes(nxgraph, 'weight')
        # nx.draw_networkx_edge_labels(nxgraph, pos, edge_labels=labels)
        # plt.show()

        return nx.algorithms.matching.max_weight_matching(nxgraph, maxcardinality=maxcardinality)
        # return nx.algorithms.matching.min_weight_matching(nxgraph, maxcardinality=maxcardinality)

    @staticmethod
    def match_blossomv(edges: list, num_nodes: float = 0, **kwargs) -> list:
        """Finds the minimum-weight matching of a list of ``edges`` using `Blossom V <https://pub.ist.ac.at/~vnk/software.html>`_.

        Parameters
        ----------
        edges : [[nodeA, nodeB, distance(nodeA,nodeB)],...]
            A graph defined by a list of edges.

        Returns
        -------
        list
            Minimum weight matching in the form of [[nodeA, nodeB],..].
        """

        if num_nodes == 0:
            return []
        try:
            folder = os.path.dirname(os.path.abspath(__file__))
            PMlib = ctypes.CDLL(folder + "/blossom5-v2.05.src/PMlib.so")
        except:
            raise FileNotFoundError("Blossom5 library not found. See docs.")

        PMlib.pyMatching.argtypes = [
            ctypes.c_int,
            ctypes.c_int,
            ctypes.POINTER(ctypes.c_int),
            ctypes.POINTER(ctypes.c_int),
            ctypes.POINTER(ctypes.c_int),
        ]
        PMlib.pyMatching.restype = ndpointer(dtype=ctypes.c_int, shape=(num_nodes,))

        # initialize ctypes array and fill with edge data
        numEdges = len(edges)
        nodes1 = (ctypes.c_int * numEdges)()
        nodes2 = (ctypes.c_int * numEdges)()
        weights = (ctypes.c_int * numEdges)()

        for i in range(numEdges):
            nodes1[i] = edges[i][0]
            nodes2[i] = edges[i][1]
            weights[i] = edges[i][2]

        matching = PMlib.pyMatching(ctypes.c_int(num_nodes), ctypes.c_int(numEdges), nodes1, nodes2, weights)
        return [[i0, i1] for i0, i1 in enumerate(matching) if i0 > i1]

    @staticmethod
    def get_qubit_distances(qubits: LA, size: Tuple[float, float]):
        """Computes the distance between a list of qubits.

        On a toric lattice, the shortest distance between two qubits may be one in four directions due to the periodic boundary conditions. The ``size`` parameters indicates the length in both x and y directions to find the shortest distance in all directions.
        """
        edges = []
        for i0, q0 in enumerate(qubits[:-1]):
            (x0, y0), z0 = q0.loc, q0.z
            for i1, q1 in enumerate(qubits[i0 + 1 :]):
                (x1, y1), z1 = q1.loc, q1.z
                wx = int(x0 - x1) % (size[0])
                wy = int(y0 - y1) % (size[1])
                wz = int(abs(z0 - z1))
                weight = min([wy, size[1] - wy]) + min([wx, size[0] - wx]) + wz
                edges.append([i0, i1 + i0 + 1, weight])
        return edges

    def _correct_matched_qubits(self, aq0: AncillaQubit, aq1: AncillaQubit) -> float:
        """Flips the values of edges between two matched qubits by doing a walk in between."""
        ancillas = self.code.ancilla_qubits[self.code.decode_layer]
        pseudos = self.code.pseudo_qubits[self.code.decode_layer]
        dq0 = ancillas[aq0.loc] if aq0.loc in ancillas else pseudos[aq0.loc]
        dq1 = ancillas[aq1.loc] if aq1.loc in ancillas else pseudos[aq1.loc]
        dx, dy, xd, yd = self._walk_direction(aq0, aq1, self.code.size)
        xv = self._walk_and_correct(dq0, dy, yd)
        self._walk_and_correct(dq1, dx, xd)
        return dy + dx + abs(aq0.z - aq1.z)

    @staticmethod
    def _walk_direction(q0: AncillaQubit, q1: AncillaQubit, size: Tuple[float, float]):
        """Finds the closest walking distance and direction."""
        (x0, y0) = q0.loc
        (x1, y1) = q1.loc
        dx0 = int(x0 - x1) % size[0]
        dx1 = int(x1 - x0) % size[0]
        dy0 = int(y0 - y1) % size[1]
        dy1 = int(y1 - y0) % size[1]
        dx, xd = (dx0, (0.5, 0)) if dx0 < dx1 else (dx1, (-0.5, 0))
        dy, yd = (dy0, (0, -0.5)) if dy0 < dy1 else (dy1, (0, 0.5))
        return dx, dy, xd, yd

    def _walk_and_correct(self, qubit: AncillaQubit, length: float, key: str):
        """Corrects the state of a qubit as it traversed during a walk."""
        for _ in range(length):
            try:
                qubit = self.correct_edge(qubit, key)
            except:
                break
        return qubit


class Planar(Toric):
    """Minimum-Weight Perfect Matching decoder for the planar lattice.

    Additionally to all edges, virtual qubits are added to the boundary, which connect to their main qubits.Edges between all virtual qubits are added with weight zero.
    """

    def decode(self, **kwargs):
        # Inherited docstring
        plaqs, stars = self.get_syndrome(find_pseudo=True)
        weight = self.correct_matching(plaqs, self.match_syndromes(plaqs, **kwargs))
        # self.correct_matching(stars, self.match_syndromes(stars, **kwargs))

        p = self.code.error_rates['p_bitflip']
        phi = self.calc_phi()# + weight*np.log(p / (1 - p))

        return phi

    def get_weight(self, a0, a1):
        (x0, y0), z0 = a0.loc, a0.z
        (x1, y1), z1 = a1.loc, a1.z
        wx = int(abs(x0 - x1))
        wy = int(abs(y0 - y1))
        wz = int(abs(z0 - z1))
        return wy + wx + wz

    def calc_phi(self):
        # Part 1: getting the edges
        values = self.code.data_qubits.values()
        inner_values = [inner_dict.values() for inner_dict in values]
        all_dqs = list(chain.from_iterable(inner_values))
        edges = [dq.edges['x'] for dq in all_dqs]

        G = nx.Graph()

        boundary_nodes = set()
        for edge in edges:
            if edge.state_type == 'x':
                # collect boundary nodes
                if edge.nodes[0].qubit_type == 'pA':
                    boundary_nodes.add(edge.nodes[0])
                if edge.nodes[1].qubit_type == 'pA':
                    boundary_nodes.add(edge.nodes[1])

                # actually add the edge
                p = self.code.error_rates['p_bitflip']
                G.add_edge(edge.nodes[0], edge.nodes[1], weight=-np.log(p / (1 - p)))

        # if in the matching and both are not boundary nodes, give it weight 0
        # print('-----------')
        # print(self.code.ancilla_qubits)
        # print(self.code.pseudo_qubits)
        # print(self.matching)
        # print('self.ancillas_matchingind', self.ancillas_matchingind)
        for node0, node1 in self.matching:
            if self.boundary_info[node0] == '' or self.boundary_info[node1] == '':
                edge_weight = self.get_weight(self.ancillas_matchingind[node0], self.ancillas_matchingind[node1])
                for dq_edge in edges:
                    for a in [node0, node1]:
                        for b in dq_edge.nodes:
                            if self.get_weight(self.ancillas_matchingind[a], b) < edge_weight/2:
                                G.add_edge(self.ancillas_matchingind[a], b, weight=0)

        # connect boundary nodes on the same side into 1 node
        for elem1 in boundary_nodes:
            for elem2 in boundary_nodes:
                if elem1 != elem2:
                    # if vertical, change loc[0] to loc[1]
                    if (elem1.loc[0] == 0 and elem2.loc[0] == 0) or (elem1.loc[0] != 0 and elem2.loc[0] != 0):
                        G.add_edge(elem1, elem2, weight=0)
                        if elem1.loc[0] != 0 and elem2.loc[0] != 0:
                            assert(elem1.loc[0] == self.code.size[0] and elem2.loc[0] == self.code.size[0])
                        assert (elem1.loc[0] == elem2.loc[0])  # they should be the same nonzero value, probably d tbh

        # call dijkstras
        # get s & t nodes
        for elem in boundary_nodes:
            # arbitrarily pick one to be the
            if elem.loc[0] == 0 and elem.loc[1] == 0:
                s = elem
            elif elem.loc[1] == 0:
                t = elem
        length, path = nx.single_source_dijkstra(G, s, t)
        # print(length, path)

        # # visualize for debugging
        # plt.figure()
        # pos = nx.spring_layout(G)
        # nx.draw(G, pos, with_labels=True)
        # labels = nx.get_edge_attributes(G, 'weight')
        # nx.draw_networkx_edge_labels(G, pos, edge_labels=labels)
        # plt.show()

        return length

    def match_syndromes(self, syndromes: LA, use_blossomv: bool = False, **kwargs) -> list:
        """Decodes a list of syndromes of the same type.

        A graph is constructed with the syndromes in ``syndromes`` as nodes and the distances between each of the syndromes as the edges. The distances are dependent on the boundary conditions of the code and is calculated by `get_qubit_distances`. A minimum-weight matching is then found by either `match_networkx` or `match_blossomv`.

        Parameters
        ----------
        syndromes
            Syndromes of the code.
        use_blossomv
            Use external C++ Blossom V library for minimum-weight matching. Needs to be downloaded and compiled by calling `.get_blossomv`.

        Returns
        -------
        list of `~.codes.elements.AncillaQubit`
            Minimum-weight matched ancilla-qubits.

        """
        matching_graph = self.match_blossomv if use_blossomv else self.match_networkx
        self.edges = self.get_qubit_distances(syndromes, self.code.size)
        self.matching = matching_graph(
            self.edges,
            maxcardinality=self.config["max_cardinality"],
            num_nodes=len(syndromes),
            **kwargs,
        )

        return self.matching


    def correct_matching(self, syndromes: List[Tuple[AncillaQubit, AncillaQubit]], matching: list):
        # Inherited docstring
        weight = 0
        for i0, i1 in matching:
            if i0 < len(syndromes) or i1 < len(syndromes):
                aq0 = syndromes[i0][0] if i0 < len(syndromes) else syndromes[i0 - len(syndromes)][1]
                aq1 = syndromes[i1][0] if i1 < len(syndromes) else syndromes[i1 - len(syndromes)][1]
                weight += self._correct_matched_qubits(aq0, aq1)
        return weight

    def get_qubit_distances(self, qubits, *args):
        """Computes the distance between a list of qubits.

        On a planar lattice, any qubit can be paired with the boundary, which is inhabited by `~.codes.elements.PseudoQubit` objects. The graph of syndromes that supports minimum-weight matching algorithms must be fully connected, with each syndrome connecting additionally to its boundary pseudo-qubit, and a fully connected graph between all pseudo-qubits with weight 0.
        """
        edges = []
        self.boundary_info = [''] * (2*len(qubits)) # index = node #, value = L or R
        self.ancillas_matchingind = [None] * (2*len(qubits))
        # if len(qubits) == 1:
        #     print('qubits', qubits)
        # Add edges between all ancilla-qubits
        for i0, (a0, _) in enumerate(qubits):
            (x0, y0), z0 = a0.loc, a0.z
            self.ancillas_matchingind[i0] = a0
            for i1, (a1, _) in enumerate(qubits[i0 + 1 :], start=i0 + 1):
                (x1, y1), z1 = a1.loc, a1.z
                wx = int(abs(x0 - x1))
                wy = int(abs(y0 - y1))
                wz = int(abs(z0 - z1))
                weight = wy + wx + wz
                edges.append([i0, i1, weight])
                self.ancillas_matchingind[i1] = a1

        # Add edges between ancilla-qubits and their boundary pseudo-qubits
        for i, (ancilla, pseudo) in enumerate(qubits):
            (xs, ys) = ancilla.loc
            (xb, yb) = pseudo.loc
            weight = xb - xs if ancilla.state_type == "x" else yb - ys
            edges.append([i, len(qubits) + i, int(abs(weight))])
            if xb == 0:
                self.boundary_info[len(qubits) + i] = 'L'
            else:
                self.boundary_info[len(qubits) + i] = 'R'
            self.ancillas_matchingind[len(qubits) + i] = pseudo

        # self.m = pymatching.Matching()
        # self.m.set_boundary_nodes(set(range(len(qubits), 2*len(qubits))))

        # Add edges of weight 0 between all pseudo-qubits
        for i0 in range(len(qubits), 2*len(qubits)):
            for i1 in range(i0 + 1, 2*len(qubits)):
                edges.append([i0, i1, 0])
        return edges

    @staticmethod
    def _walk_direction(q0, q1, *args):
        # Inherited docsting
        (x0, y0), (x1, y1) = q0.loc, q1.loc
        dx, dy = int(x0 - x1), int(y0 - y1)
        xd = (0.5, 0) if dx > 0 else (-0.5, 0)
        yd = (0, -0.5) if dy > 0 else (0, 0.5)
        return abs(dx), abs(dy), xd, yd
