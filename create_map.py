import json
import folium
from datetime import datetime
from folium.plugins import HeatMap
import os
from PIL import Image
import piexif
from folium import Popup
from geopy.distance import geodesic
import logging
import yaml
from pathlib import Path
from datetime import timezone

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

from base64 import  b64encode
from io import BytesIO
import argparse

def parse_utc_datetime(dt_str):
    """Parse a datetime string and ensure it's in UTC."""
    # Remove 'Z' and add UTC timezone
    dt_str = dt_str.replace("Z", "+00:00")
    dt = datetime.fromisoformat(dt_str)
    # Convert to UTC if it has a timezone
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc)
    else:
        # If no timezone, assume UTC
        dt = dt.replace(tzinfo=timezone.utc)
    return dt

# Resize the image to a smaller size before encoding
def resize_image(image_path, max_width=150):
    """Resize image while maintaining aspect ratio and orientation."""
    try:
        with Image.open(image_path) as img:
            # Get the original orientation from EXIF
            try:
                exif = img._getexif()
                if exif is not None:
                    orientation = exif.get(274)  # 274 is the orientation tag
                    if orientation is not None:
                        # Rotate the image according to EXIF orientation
                        if orientation == 3:
                            img = img.rotate(180, expand=True)
                        elif orientation == 6:
                            img = img.rotate(270, expand=True)
                        elif orientation == 8:
                            img = img.rotate(90, expand=True)
            except Exception as e:
                logger.debug(f"Could not read EXIF orientation: {e}")

            # Calculate new dimensions maintaining aspect ratio
            width_percent = max_width / float(img.size[0])
            new_height = int(float(img.size[1]) * width_percent)
            img = img.resize((max_width, new_height), Image.LANCZOS)
            return img, new_height  # Return both the image and its height
    except Exception as e:
        logger.error(f"Error resizing image {image_path}: {e}")
        return None, None

# Encode resized image to Base64
def encode_resized_image(image_path, max_width=300):
    """Encode resized image to Base64."""
    try:
        resized_img, height = resize_image(image_path, max_width)
        if resized_img:
            with BytesIO() as buffer:
                resized_img.save(buffer, format="JPEG")
                return b64encode(buffer.getvalue()).decode("utf-8"), height
        return None, None
    except Exception as e:
        logger.error(f"Error encoding image {image_path}: {e}")
        return None, None

# Function to extract GPS info from an image
def get_gps_info(image_path):
    """Extract GPS coordinates from image EXIF data."""
    try:
        exif_data = piexif.load(image_path)
        gps_data = exif_data.get("GPS")

        if not gps_data:
            logger.debug(f"No GPS data found in {image_path}")
            return None

        def convert_to_degrees(value):
            d = value[0][0] / value[0][1]
            m = value[1][0] / value[1][1]
            s = value[2][0] / value[2][1]
            return d + (m / 60.0) + (s / 3600.0)

        latitude = convert_to_degrees(gps_data[piexif.GPSIFD.GPSLatitude])
        if gps_data[piexif.GPSIFD.GPSLatitudeRef] != b"N":
            latitude = -latitude

        longitude = convert_to_degrees(gps_data[piexif.GPSIFD.GPSLongitude])
        if gps_data[piexif.GPSIFD.GPSLongitudeRef] != b"E":
            longitude = -longitude

        return latitude, longitude

    except Exception as e:
        logger.error(f"Error processing {image_path}: {e}")
        return None

# Function to filter images within a certain distance of Lisbon
def is_within_distance(coords, center_coords, max_distance_km):
    """Check if coordinates are within specified distance of center point."""
    return geodesic(coords, center_coords).km <= max_distance_km

# Helper function to filter data by time
def filter_by_time(data, start_time, end_time):
    """Filter data points within specified time range."""
    return [
        item
        for item in data
        if start_time <= parse_utc_datetime(item["time"]) <= end_time
    ]

def generate_folium_map(data, config, image_folder=None):
    """Generate an interactive map with the specified configuration."""
    vis_config = config["visualization"]
    map_config = config["map"]
    
    # Parse time range and ensure UTC timezone
    start_time = parse_utc_datetime(map_config["start"])
    end_time = parse_utc_datetime(map_config["end"])
    
    logger.info(f"Generating map for time range: {start_time} to {end_time}")
    
    # Filter data
    filtered_timeline = filter_by_time(data["timeline"], start_time, end_time)
    filtered_visits = filter_by_time(data["visits"], start_time, end_time)
    
    # Filter routes based on activity types
    show_walking = "walking" in vis_config["selected_activity_types"]
    show_driving = "in passenger vehicle" in vis_config["selected_activity_types"]
    
    filtered_routes = [
        route
        for route in data["routes"]
        if start_time <= parse_utc_datetime(route["time"]) <= end_time
        and ((show_walking and route["type"] == "walking")
             or (show_driving and route["type"] == "in passenger vehicle"))
    ]
    
    filtered_routes_timeline = [
        route
        for route in data["routes_timeline"]
        if start_time <= parse_utc_datetime(route["time"]) <= end_time
        and ((show_walking and route["type"] == "walking")
             or (show_driving and route["type"] == "in passenger vehicle"))
    ]

    logger.info(f"Filtered data: {len(filtered_timeline)} timeline points, "
                f"{len(filtered_visits)} visits, {len(filtered_routes)} routes")

    # Create map
    center = tuple(map_config["center_point"])
    m = folium.Map(location=center, zoom_start=vis_config["zoom_start"], tiles=None)
    folium.TileLayer(vis_config["map_style"]).add_to(m)

    # Create legend HTML
    legend_html = '''
    <div style="position: fixed; 
                bottom: 50px; right: 50px; 
                border:2px solid grey; z-index:9999; 
                background-color: rgba(255, 255, 255, 0.8);
                padding: 10px;
                font-size:14px;
                border-radius: 5px;">
        <p style="margin: 0 0 10px 0;"><b>Routes</b></p>
        <p style="margin: 0;"><i class="fa fa-map-marker fa-2x" style="color:''' + vis_config["walking_color"] + '''"></i> Walking</p>
        <p style="margin: 0;"><i class="fa fa-map-marker fa-2x" style="color:''' + vis_config["driving_color"] + '''"></i> Driving</p>
        <p style="margin: 10px 0 10px 0;"><b>Points</b></p>
        <p style="margin: 0;"><i class="fa fa-circle fa-2x" style="color:''' + vis_config["timeline_color"] + '''"></i> Timeline</p>
        <p style="margin: 0;"><i class="fa fa-circle fa-2x" style="color:''' + vis_config["visits_color"] + '''"></i> Visits</p>
    </div>
    '''
    m.get_root().html.add_child(folium.Element(legend_html))

    # Add timeline points
    for point in filtered_timeline:
        coords = tuple(map(float, point["point"].split(":")[1].split(",")))
        folium.CircleMarker(
            location=coords,
            radius=vis_config["timeline_radius"],
            color=vis_config["timeline_color"],
            fill=True,
            fill_color=vis_config["timeline_color"],
            fill_opacity=vis_config["timeline_opacity"],
        ).add_to(m)

    # Add visit points
    for point in filtered_visits:
        coords = tuple(map(float, point["point"].split(":")[1].split(",")))
        folium.CircleMarker(
            location=coords,
            radius=vis_config["visits_radius"],
            color=vis_config["visits_color"],
            fill=True,
            fill_color=vis_config["visits_color"],
            fill_opacity=vis_config["visits_opacity"],
        ).add_to(m)

    # Add routes
    for route in filtered_routes:
        route_color = (vis_config["walking_color"] if route["type"] == "walking" 
                      else vis_config["driving_color"])
        route_weight = (vis_config["walking_radius"] if route["type"] == "walking" 
                       else vis_config["driving_radius"])
        route_opacity = (vis_config["walking_opacity"] if route["type"] == "walking" 
                        else vis_config["driving_opacity"])
        
        folium.PolyLine(
            locations=route["coords"],
            color=route_color,
            weight=route_weight,
            opacity=route_opacity,
        ).add_to(m)

    # Add timeline routes
    for route in filtered_routes_timeline:
        route_color = (vis_config["walking_color"] if route["type"] == "walking" 
                      else vis_config["driving_color"])
        route_weight = (vis_config["walking_radius"] if route["type"] == "walking" 
                       else vis_config["driving_radius"])
        route_opacity = (vis_config["walking_opacity"] if route["type"] == "walking" 
                        else vis_config["driving_opacity"])
        
        folium.PolyLine(
            locations=route["coords"],
            color=route_color,
            weight=route_weight,
            opacity=route_opacity,
        ).add_to(m)

    # Add heatmap if enabled
    if vis_config["show_heatmap"]:
        logger.info("Adding heatmap layer")
        tpoints = [x["point"] for x in data["timeline"]]
        tpoints = [x.split(":")[1].split(",") for x in tpoints]
        tpoints = [[float(x[0]), float(x[1])] for x in tpoints]
        intensity = [1 for _ in range(len(tpoints))]
        tpoints = [tpoints[i] + [intensity[i]] for i in range(len(tpoints))]

        HeatMap(tpoints, min_opacity=0.4, gradient={
            "blue": 0.0,
            "orange": 0.5,
            "red": 1.0
        }).add_to(m)

    # Add images if enabled
    if image_folder:
        logger.info("Processing images")
        if not os.path.exists(image_folder):
            logger.warning(f"Image folder {image_folder} not found")
        else:
            image_count = 0
            for filename in os.listdir(image_folder):
                if filename.lower().endswith(".jpg") or filename.lower().endswith(".png") or filename.lower().endswith(".jpeg"):
                    image_path = os.path.join(image_folder, filename)
                    gps_info = get_gps_info(image_path)

                    if gps_info:
                        latitude, longitude = gps_info
                        if is_within_distance((latitude, longitude), center, 
                                            vis_config["max_image_distance_km"]):
                            encoded_image, image_height = encode_resized_image(
                                image_path, 
                                vis_config["max_image_width"]
                            )
                            if encoded_image:
                                # Calculate exact dimensions for the popup
                                popup_width = vis_config["max_image_width"] + 10  # Minimal padding
                                popup_height = image_height + 10  # Minimal padding
                                
                                # Create a more compact popup with just the image
                                html = f'''
                                <div style="margin: 0; padding: 0; overflow: hidden; width: {popup_width}px; height: {popup_height}px;">
                                    <img src="data:image/jpeg;base64,{encoded_image}" 
                                            style="width: {vis_config["max_image_width"]}px; height: {image_height}px; display: block;">
                                </div>
                                '''
                                # Create iframe with exact dimensions
                                iframe = folium.IFrame(html, width=popup_width, height=popup_height)
                                popup = Popup(iframe, max_width=popup_width, max_height=popup_height)

                                folium.Marker(
                                    location=[latitude, longitude],
                                    popup=popup,
                                    icon=folium.Icon(color="blue", icon="camera"),
                                ).add_to(m)
                                image_count += 1
                
        logger.info(f"Added {image_count} images to the map")

    return m


def main():
    # Set up argument parser
    parser = argparse.ArgumentParser(description='Create an interactive map from location data')
    parser.add_argument('--input_file', required=True, help='Path to the preprocessed data JSON file')
    parser.add_argument('--output_file', required=True, help='Path to save the generated HTML map file')
    parser.add_argument('--config_file', required=False, help='Path to the config file')
    parser.add_argument('--image_folder', required=False, help='Path to the image folder')
    args = parser.parse_args()

    # Load configuration
    if not args.config_file:
        with open("config.yaml") as f:
            config = yaml.safe_load(f)
    else:
        with open(args.config_file) as f:
            config = yaml.safe_load(f)

    # Load preprocessed data
    with open(args.input_file) as f:
        data = json.load(f)

    # Generate map
    m = generate_folium_map(data, config, image_folder=args.image_folder)

    # Save map
    m.save(args.output_file)
    logger.info(f"Map saved to {args.output_file}")

if __name__ == "__main__":
    main()

