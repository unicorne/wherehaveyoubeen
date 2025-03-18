# Where Have You Been

A Python-based tool for visualizing and analyzing location data, creating interactive maps of your movements, routes, and visited places.

## Overview

This project processes location data to create detailed, interactive maps showing your movement patterns, including:
- Walking and driving routes
- Visited locations
- Timeline of movements
- Optional heatmap visualization
- Photo integration with GPS data (if available)

## Example

#### Lisbon
![lisbon](https://github.com/user-attachments/assets/61acc146-f21c-40ab-ab4b-f19c76ba7dd1)

![lisbon2](https://github.com/user-attachments/assets/5d647e94-432e-4269-b6d8-378de7cbc0dc)

#### Paris

![paris](https://github.com/user-attachments/assets/701fa759-7f0f-40e7-89c6-b18882879b2e)


## Features

- **Route Processing**: Automatically detects and visualizes walking and driving routes
- **Timeline Visualization**: Shows your movement patterns over time
- **Visit Detection**: Highlights places where you've spent time
- **Multiple Visualization Options**:
  - Route colors for different transportation modes
  - Timeline points
  - Visit markers
  - Optional heatmap layer
  - Photo integration with location data
- **Efficient Processing**:
  - Parallel processing for timeline routes
  - Caching system for faster node lookups
  - Progress bars for long-running operations




## Installation

Requires Python 3.7+. For packages see requirements.

1. Clone the repository:
```bash
git clone https://github.com/yourusername/wherehaveyoubeen.git
cd wherehaveyoubeen
```

2. Install required packages:
```bash
pip install -r requirements.txt
```

## Configuration

Create a `config.yaml` file with the following structure:

```yaml
map:
  start: "2024-01-01T00:00:00"  # Start date for data processing
  end: "2024-12-31T23:59:59"    # End date for data processing
  center_point: [38.7223, -9.1393]  # Center point for map [lat, lon]
  dist: 5000  # Distance in meters for graph extraction.

compute:
  max_workers: 4  # Number of parallel workers for route processing

visualization:
  zoom_start: 13
  map_style: "cartodbdark_matter"
  selected_activity_types: ["walking", "in passenger vehicle"]
  show_heatmap: true
  show_images: true
  image_folder: "photos"
  max_image_width: 300
  max_image_distance_km: 5
  timeline_radius: 3
  visits_radius: 5
  walking_radius: 2
  driving_radius: 3
  timeline_color: "#1f77b4"
  visits_color: "#2ca02c"
  walking_color: "#ff7f0e"
  driving_color: "#d62728"
  timeline_opacity: 0.8
  visits_opacity: 0.8
  walking_opacity: 0.8
  driving_opacity: 0.8
```

Experiment with cardboard styles: e.g [here](https://deparkes.co.uk/2016/06/10/folium-map-tiles/)

## Usage

1. Process your location data:

**This can take a long time!!** Since we calculate routes between all movements. 
```bash
python calculate_routes.py --input_file your_location_data.json --output_file preprocessed_data.json
```

2. Generate the interactive map:
```bash
python create_map.py --input_file preprocessed_data/preprocessed_data.json --output_file outputs/map.html
```

3. Open the generated `map.html` in your web browser to view your interactive map.

## Input Data Format

The input JSON file should contain location data in the following format:

```json
{
  "startTime": "2024-01-01T12:00:00Z",
  "endTime": "2024-01-01T13:00:00Z",
  "timelinePath": [...],
  "activity": {
    "start": "geo:38.7100827,-9.1602843",
    "end": "geo:38.7101792,-9.1600991",
    "topCandidate": {
      "type": "walking"
    }
  },
  "visit": {
    "topCandidate": {
      "placeLocation": "geo:38.7100827,-9.1602843"
    }
  }
}
```

This is the format exported from your Google Maps timeline. [See here](https://support.google.com/maps/thread/280205453/how-do-i-download-my-timeline-history?hl=en) 

## Output

The tool generates:
1. A preprocessed JSON file containing:
   - Computed routes with coordinates
   - Timeline data
   - Visit information
2. An interactive HTML map featuring:
   - Color-coded routes (walking/driving)
   - Timeline points
   - Visit markers
   - Optional heatmap layer
   - Photos with GPS data (if enabled)

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

The MIT License is a permissive license that is short and to the point. It lets people do anything they want with your code as long as they provide attribution back to you and don't hold you liable.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## Images

You can include an folder with images. All images with existing geo tag are added to the map. The image size is reduced for computational purposes. 

## Route calculation

Relies on [OSMnx](https://osmnx.readthedocs.io/en/stable/). 



