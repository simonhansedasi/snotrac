"""
OSMnx graph building and pandana network setup.

OSM download is slow (~5-10 min for county scale). Cache the graph to
data/raw/osm/ and load from disk on subsequent runs.

Outputs:
  data/raw/osm/snohomish_walk.graphml   (OSMnx graph, cached)
  pandana.Network object (not persisted — rebuild from graphml if needed)
"""

from pathlib import Path

import osmnx as ox
import pandana as pdna
import geopandas as gpd

PLACE = "Snohomish County, Washington"
NETWORK_TYPE = "walk"
OSM_CACHE = Path("data/raw/osm/snohomish_walk.graphml")
PRECOMPUTE_DISTANCE_M = 1.5 * 1609  # 1.5 miles in meters


def build_graph(
    place: str = PLACE,
    network_type: str = NETWORK_TYPE,
    cache_path: str | Path = OSM_CACHE,
) -> object:  # networkx.MultiDiGraph
    """Download or load the OSMnx walk network for Snohomish County."""
    cache_path = Path(cache_path)
    if cache_path.exists():
        print(f"Loading cached OSMnx graph from {cache_path}")
        G = ox.load_graphml(cache_path)
    else:
        print(f"Downloading OSMnx walk network for '{place}' — this takes 5-10 min...")
        G = ox.graph_from_place(place, network_type=network_type)
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        ox.save_graphml(G, cache_path)
        print(f"Graph cached → {cache_path}")
    return G


def build_network(
    G=None,
    place: str = PLACE,
    network_type: str = NETWORK_TYPE,
    cache_path: str | Path = OSM_CACHE,
    precompute_dist_m: float = PRECOMPUTE_DISTANCE_M,
) -> tuple:
    """
    Build a pandana Network from an OSMnx graph.

    Returns (network, nodes_gdf, edges_gdf)
    """
    if G is None:
        G = build_graph(place, network_type, cache_path)

    nodes, edges = ox.graph_to_gdfs(G)

    # pandana expects edge source/target as integer node IDs
    # graph_to_gdfs returns them as index (u, v, key) — reset to get u/v columns
    edges_reset = edges.reset_index()

    network = pdna.Network(
        node_x=nodes["x"],
        node_y=nodes["y"],
        edge_from=edges_reset["u"],
        edge_to=edges_reset["v"],
        edge_weights=edges_reset[["length"]],
        twoway=True,
    )

    print(f"Precomputing network up to {precompute_dist_m:.0f}m...")
    network.precompute(precompute_dist_m)
    print("Precompute complete.")

    return network, nodes, edges


def get_route_lines(G=None, cache_path: str | Path = OSM_CACHE) -> gpd.GeoDataFrame:
    """Return edge GeoDataFrame for map overlay (light gray route lines)."""
    if G is None:
        G = build_graph(cache_path=cache_path)
    _, edges = ox.graph_to_gdfs(G)
    return edges[["geometry"]].copy()


def save_network(network: pdna.Network, path: str | Path) -> None:
    """Serialize a pandana Network to HDF5."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    network.save_hdf5(str(path))
    print(f"pandana network saved → {path}")


def load_network(path: str | Path) -> pdna.Network:
    """Load a previously serialized pandana Network."""
    net = pdna.Network.from_hdf5(str(path))
    print(f"pandana network loaded from {path}")
    return net
