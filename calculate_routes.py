import json
import pandas as pd
import osmnx as ox
import networkx as nx
import geopy.distance
from concurrent.futures import ProcessPoolExecutor, as_completed
import argparse
import yaml
from tqdm import tqdm


def cached_nearest_node(G, lat, lon, nearest_node_cache = {}):
    """
    Returns the nearest node in G for the given (lat, lon).
    Uses an in-memory cache to speed up repeated lookups.
    """
    key = (lat, lon)
    if key not in nearest_node_cache:
        # Actually find the nearest node
        # (Note: OSMnx expects (lon, lat) ordering in nearest_nodes)
        node = ox.distance.nearest_nodes(G, X=lon, Y=lat)
        nearest_node_cache[key] = node
        return node
    return nearest_node_cache[key]

def get_nearest_node(G, lat, lon):
    """
    Returns the nearest node in G for the given (lat, lon).
    """
    node = ox.distance.nearest_nodes(G, X=lon, Y=lat)
    return node

########################
# 3) The heavy-lifting function: computes one route
########################
def compute_single_route(activity, walk_graph, drive_graph, nearest_node_cache={}):
    """
    activity: a dictionary with 'type', 'time', 'start', 'end'.
    Returns a dict with route info or None if error.
    """
    try:
        # Extract lat,lon from 'start' and 'end'
        start_coords = tuple(map(float, activity['start'].split(':')[1].split(',')))
        end_coords   = tuple(map(float, activity['end'].split(':')[1].split(',')))

        # Pick the graph based on mode
        mode = 'walk' if 'walking' in activity['type'].lower() else 'drive'
        G = walk_graph if mode == 'walk' else drive_graph

        # Nearest nodes
        #start_node = cached_nearest_node(G, start_coords[0], start_coords[1])
        #end_node   = cached_nearest_node(G, end_coords[0], end_coords[1])
        start_node = get_nearest_node(G, start_coords[0], start_coords[1])
        end_node   = get_nearest_node(G, end_coords[0], end_coords[1])
        # check is start and end in node
        if start_node not in G.nodes() or end_node not in G.nodes():
            print(f"Start or end node not found in graph for {activity}")

        # Compute shortest path
        route = nx.shortest_path(G, start_node, end_node, weight='length')

        # Build route coordinate list
        route_coords = [(G.nodes[n]['y'], G.nodes[n]['x']) for n in route]

        return {
            'type': activity['type'],
            'time': activity['time'],
            'start': activity['start'],
            'end': activity['end'],
            'coords': route_coords
        }

    except Exception as e:
        # In parallel mode, we typically return None or some error indicator.
        print(f"Error computing route for {activity} -> {e}")
        return None

########################
# 4) Parallel route preprocessing
########################
def parallel_preprocess_routes(activities, walk_graph, drive_graph, max_workers=4,nearest_node_cache={}):
    """
    Parallel version of your preprocess_routes function with progress bar.
    """
    results = []
    total = len(activities)
    
    # Create progress bar
    pbar = tqdm(total=total, desc="Processing routes", unit="route")
    
    # We'll use ProcessPoolExecutor to parallelize
    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        future_to_activity = {
            executor.submit(compute_single_route, activity, walk_graph, drive_graph, nearest_node_cache): activity
            for activity in activities
        }
        for future in as_completed(future_to_activity):
            res = future.result()
            if res is not None:
                results.append(res)
            pbar.update(1)
    
    pbar.close()
    return results


def main(location_path, start, end, center_point, dist, output_file):
    # ------------
    # Load & prep data
    # ------------
    walk_graph = ox.graph_from_point(center_point, dist=dist, network_type="walk", simplify=True)
    drive_graph = ox.graph_from_point(center_point, dist=dist, network_type="drive", simplify=True)
    print("Loading and preparing data...")
    path = location_path
    with open(path) as f:
        data = json.load(f)
    df = pd.DataFrame(data)

    # Filter
    df = df[(df["startTime"] > start) & (df["endTime"] < end)]

    # Remove timezone, simplify time columns
    df["startTime"] = df["startTime"].apply(lambda x: x.replace('Z', '+00:00')[:-6])
    df["endTime"]   = df["endTime"].apply(lambda x: x.replace('Z', '+00:00')[:-6])

    # Split out dataframes
    df_timeline = df[~pd.isna(df["timelinePath"])].reset_index(drop=True)
    df_visit    = df[~pd.isna(df["visit"])].reset_index(drop=True)
    df_activity = df[~pd.isna(df["activity"])].reset_index(drop=True)

    print(f"Found {len(df_timeline)} timeline entries, {len(df_visit)} visits, and {len(df_activity)} activities")

    # Prepare timeline
    df_timeline = df_timeline.sort_values(by="startTime").reset_index(drop=True)
    data_timeline_raw = df_timeline["timelinePath"].dropna().values
    start_values      = df_timeline["startTime"].dropna().values
    data_timeline     = []
    for i, d in enumerate(data_timeline_raw):
        for el in d:
            data_timeline.append({"time": start_values[i], "point": el["point"]})

    # Prepare activity
    data_activity_raw = df_activity["activity"].values
    start_values = df_activity["startTime"].values
    end_values   = df_activity["endTime"].values
    data_activity = []
    for i, el in enumerate(data_activity_raw):
        data_activity.append({
            "time":  start_values[i],
            "point": el["start"],
            "type":  el["topCandidate"]["type"],
            "start": el["start"],
            "end":   el["end"]
        })

    # Prepare visits
    data_visit_raw = df_visit["visit"].values
    start_values   = df_visit["startTime"].values
    data_visits    = []
    for i, el in enumerate(data_visit_raw):
        data_visits.append({
            "time": start_values[i],
            "point": el["topCandidate"]["placeLocation"]
        })

    # Build timeline routes
    print("Building timeline routes...")
    data_timelines_routes = []
    for i in range(len(data_timeline) - 1):
        data_timelines_routes.append({
            "start": data_timeline[i]["point"],
            "end":   data_timeline[i + 1]["point"],
            "time":  data_timeline[i]["time"]
        })

    def get_distance(start, end):
        start = start.split(":")[1].split(",")
        end   = end.split(":")[1].split(",")
        start = (float(start[0]), float(start[1]))
        end   = (float(end[0]), float(end[1]))
        return geopy.distance.distance(start, end).km

    # Add a naive "type" label based on distance
    print("Classifying route types...")
    data_timelines_routes_distance = []
    for el in data_timelines_routes:
        dist = get_distance(el["start"], el["end"])
        if dist > 1.0:
            typething = "in a passenger vehicle"
        else:
            typething = "walking"
        data_timelines_routes_distance.append({
            "start": el["start"], 
            "end":   el["end"], 
            "time":  el["time"], 
            "type":  typething
        })

    nearest_node_cache = {}
    # ------------
    # Process routes
    # ------------
    # Process timeline routes in parallel
    print(f"\nProcessing {len(data_timelines_routes_distance)} timeline routes...")
    parallel_routes_timeline = parallel_preprocess_routes(data_timelines_routes_distance, walk_graph, drive_graph, max_workers=max_workers, nearest_node_cache=nearest_node_cache)
    
    # Process activity routes sequentially
    nearest_node_cache = {}
    print(f"\nProcessing {len(data_activity)} activity routes...")
    routes_activity = []
    for activity in tqdm(data_activity, desc="Processing activity routes", unit="route"):
        route = compute_single_route(activity, walk_graph, drive_graph, nearest_node_cache=nearest_node_cache)
        if route is not None:
            routes_activity.append(route)

    # ------------
    # Save output
    # ------------
    print("\nSaving preprocessed data...")
    with open(output_file, "w") as f:
        json.dump({
            "routes":          routes_activity,
            "routes_timeline": parallel_routes_timeline,
            "timeline":        data_timeline,
            "visits":          data_visits
        }, f)

    print(f"Preprocessing complete. Data saved to {output_file}")

if __name__ == "__main__":
    # Set up argument parser
    parser = argparse.ArgumentParser(description='Calculate routes from location data')
    parser.add_argument('--input_file', required=True, help='Path to the input location data JSON file')
    parser.add_argument('--output_file', required=True, help='Path to save the preprocessed data JSON file')
    args = parser.parse_args()
    input_file = args.input_file
    output_file = args.output_file

    # get arguments from config file
    with open("config.yaml") as f:
        config = yaml.safe_load(f)
        start = config["map"]["start"]
        end   = config["map"]["end"]
        center_point = config["map"]["center_point"]
        dist = config["map"]["dist"]
        max_workers = config["compute"]["max_workers"]
        center_point = tuple(config["map"]["center_point"])

    main(input_file, start, end, center_point, dist, output_file)
