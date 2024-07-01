import json
from datetime import datetime
from collections import defaultdict
from geopy.distance import distance

def parse_json_to_routes(json_data):
    routes_by_date = defaultdict(list)
    
    for segment in json_data["semanticSegments"]:
        if "timelinePath" in segment:
            for point in segment["timelinePath"]:
                lat, lon = point["point"].replace("°", "").replace("Â", "").split(", ")
                time = datetime.strptime(point["time"], "%Y-%m-%dT%H:%M:%S.%f%z")
                date = time.strftime("%Y-%m-%d")
                routes_by_date[date].append({
                    "lat": float(lat),
                    "lon": float(lon),
                    "time": time.isoformat()
                })
    
    return routes_by_date

def analyze_journeys(routes_by_date, distance_threshold=0.1, time_threshold=300):  # 100 meters, 5 minutes
    journeys_by_date = {}
    
    for date, points in routes_by_date.items():
        journeys = []
        start_point = None
        prev_point = None
        journey_points = []
        journey_distance = 0
        
        for point in points:
            current_time = datetime.fromisoformat(point['time'])
            if not start_point:
                start_point = point
                prev_point = point
                journey_points = [point]
                continue
            
            prev_time = datetime.fromisoformat(prev_point['time'])
            current_distance = distance((prev_point['lat'], prev_point['lon']), (point['lat'], point['lon'])).km
            journey_distance += current_distance
            time_diff = (current_time - prev_time).total_seconds()
            
            if current_distance > distance_threshold or time_diff > time_threshold:
                journey_points.append(point)
                if not journeys or (current_time - datetime.fromisoformat(journeys[-1]['end']['time'])).total_seconds() > time_threshold:
                    journeys.append({
                        'start': start_point,
                        'end': point,
                        'points': journey_points,
                        'distance': journey_distance
                    })
                    journey_points = [point]
                    journey_distance = 0
                else:
                    journeys[-1]['end'] = point
                    journeys[-1]['points'].extend(journey_points)
                    journeys[-1]['distance'] += journey_distance
                    journey_points = [point]
                    journey_distance = 0
                
                start_point = point
            else:
                journey_points.append(point)
            
            prev_point = point
        
        journeys_by_date[date] = journeys
    
    return journeys_by_date

def create_html(routes_by_date, journeys_by_date):
    html_content = '''
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Google Location History Viewer</title>
        <link rel="stylesheet" href="https://unpkg.com/leaflet@1.7.1/dist/leaflet.css"/>
        <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/flatpickr/dist/flatpickr.min.css">
        <script src="https://unpkg.com/leaflet@1.7.1/dist/leaflet.js"></script>
        <script src="https://cdn.jsdelivr.net/npm/flatpickr"></script>
        <style>
            body {
                font-family: Arial, sans-serif;
                margin: 0;
                padding: 0;
                background-color: #f0f0f0;
            }
            .header {
                background-color: #4285F4;
                color: white;
                text-align: center;
                padding: 1em;
                font-size: 24px;
                font-weight: bold;
            }
            .main-container {
                display: flex;
                flex-direction: column;
                max-width: 1200px;
                margin: 0 auto;
                padding: 20px;
                background-color: white;
                box-shadow: 0 0 10px rgba(0,0,0,0.1);
            }
            #datePicker {
                margin-bottom: 20px;
                padding: 10px;
                font-size: 16px;
                border: 1px solid #ddd;
                border-radius: 4px;
            }
            #container {
                display: flex;
                height: 600px;
            }
            #map {
                flex: 7;
                border-radius: 4px;
                overflow: hidden;
            }
            #journeyList {
                flex: 3;
                overflow-y: auto;
                padding: 10px;
                background-color: #f9f9f9;
                border-left: 1px solid #ddd;
                border-radius: 0 4px 4px 0;
            }
            .journey-item {
                cursor: pointer;
                padding: 10px;
                margin-bottom: 10px;
                border-radius: 4px;
                transition: all 0.3s ease;
            }
            .journey-item:hover {
                opacity: 0.8;
                transform: translateY(-2px);
            }
            .journey-item.selected {
                border: 2px solid #4285F4;
                box-shadow: 0 0 5px rgba(66,133,244,0.5);
            }
            .leaflet-popup-content-wrapper {
                border-radius: 4px;
            }
        </style>
    </head>
    <body>
        <div class="header">Google Location History Viewer</div>
        <div class="main-container">
            <input type="text" id="datePicker" placeholder="Select Date">
            <div id="container">
                <div id="map"></div>
                <div id="journeyList"></div>
            </div>
        </div>
        <script>
            const routes = {routes_json};
            const journeys = {journeys_json};
            const dates = Object.keys(journeys).sort();

            const map = L.map('map').setView([0, 0], 2);
            L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
                attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
            }).addTo(map);

            let currentRoutes = [];
            let currentMarkers = [];
            let colors = [];

            function generateColors(n) {
                const colors = [];
                for (let i = 0; i < n; i++) {
                    const hue = i / n;
                    const rgb = hslToRgb(hue, 0.5, 0.5);
                    colors.push(`rgb(${rgb[0]}, ${rgb[1]}, ${rgb[2]})`);
                }
                return colors;
            }

            function hslToRgb(h, s, l) {
                let r, g, b;
                if (s === 0) {
                    r = g = b = l;
                } else {
                    const hue2rgb = (p, q, t) => {
                        if (t < 0) t += 1;
                        if (t > 1) t -= 1;
                        if (t < 1/6) return p + (q - p) * 6 * t;
                        if (t < 1/2) return q;
                        if (t < 2/3) return p + (q - p) * (2/3 - t) * 6;
                        return p;
                    };
                    const q = l < 0.5 ? l * (1 + s) : l + s - l * s;
                    const p = 2 * l - q;
                    r = hue2rgb(p, q, h + 1/3);
                    g = hue2rgb(p, q, h);
                    b = hue2rgb(p, q, h - 1/3);
                }
                return [Math.round(r * 255), Math.round(g * 255), Math.round(b * 255)];
            }

            function showRoute(date) {
                clearMap();
                
                if (journeys[date]) {
                    colors = generateColors(journeys[date].length);
                    const journeyList = document.getElementById('journeyList');
                    journeyList.innerHTML = '<h3>Journeys for ' + date + '</h3>';
                    
                    journeys[date].forEach((journey, index) => {
                        const journeyItem = document.createElement('div');
                        journeyItem.className = 'journey-item';
                        journeyItem.style.backgroundColor = colors[index];
                        journeyItem.innerHTML = 'Journey ' + (index + 1) + ':<br>' +
                            'Start: ' + new Date(journey.start.time).toLocaleString() + '<br>' +
                            'End: ' + new Date(journey.end.time).toLocaleString() + '<br>' +
                            'Distance: ' + journey.distance.toFixed(2) + ' km';
                        journeyItem.onclick = () => toggleJourney(date, index);
                        journeyList.appendChild(journeyItem);
                    });
                    
                    showAllJourneys(date);
                } else {
                    journeyList.innerHTML = '<p>No journeys recorded for this date.</p>';
                }
            }

            function clearMap() {
                currentRoutes.forEach(route => map.removeLayer(route));
                currentMarkers.forEach(marker => map.removeLayer(marker));
                currentRoutes = [];
                currentMarkers = [];
            }

            function showAllJourneys(date) {
                journeys[date].forEach((journey, index) => {
                    addJourneyToMap(journey, index);
                });
                const bounds = L.latLngBounds(currentRoutes.flatMap(route => route.getLatLngs()));
                map.fitBounds(bounds);
            }

            function toggleJourney(date, index) {
                const journeyItems = document.querySelectorAll('.journey-item');
                journeyItems[index].classList.toggle('selected');
                
                clearMap();
                journeyItems.forEach((item, i) => {
                    if (item.classList.contains('selected')) {
                        addJourneyToMap(journeys[date][i], i);
                    }
                });
                
                if (currentRoutes.length > 0) {
                    const bounds = L.latLngBounds(currentRoutes.flatMap(route => route.getLatLngs()));
                    map.fitBounds(bounds);
                }
            }

            function addJourneyToMap(journey, index) {
                const points = journey.points.map(p => [p.lat, p.lon]);
                const route = L.polyline(points, {color: colors[index], weight: 3}).addTo(map);
                currentRoutes.push(route);

                const startMarker = L.marker(points[0], {
                    icon: L.divIcon({
                        className: 'custom-div-icon',
                        html: "<div style='background-color:"+colors[index]+";' class='marker-pin'></div><i class='my-div-icon'></i>",
                        iconSize: [30, 42],
                        iconAnchor: [15, 42]
                    })
                }).addTo(map);
                startMarker.bindPopup('Start: ' + new Date(journey.start.time).toLocaleString());
                currentMarkers.push(startMarker);

                const endMarker = L.marker(points[points.length - 1], {
                    icon: L.divIcon({
                        className: 'custom-div-icon',
                        html: "<div style='background-color:"+colors[index]+";' class='marker-pin'></div><i class='my-div-icon'></i>",
                        iconSize: [30, 42],
                        iconAnchor: [15, 42]
                    })
                }).addTo(map);
                endMarker.bindPopup('End: ' + new Date(journey.end.time).toLocaleString());
                currentMarkers.push(endMarker);
            }

            flatpickr("#datePicker", {
                enableTime: false,
                dateFormat: "Y-m-d",
                minDate: dates[0],
                maxDate: dates[dates.length - 1],
                enable: dates,
                onChange: function(selectedDates, dateStr, instance) {
                    showRoute(dateStr);
                }
            });

            if (dates.length > 0) {
                showRoute(dates[0]);
            }
        </script>
    </body>
    </html>
    '''
    return html_content.replace('{routes_json}', json.dumps(routes_by_date)).replace('{journeys_json}', json.dumps(journeys_by_date, default=str))

# Read the JSON file
with open('location-history.json', 'r') as json_file:
    json_data = json.load(json_file)

routes_by_date = parse_json_to_routes(json_data)
journeys_by_date = analyze_journeys(routes_by_date)
html_content = create_html(routes_by_date, journeys_by_date)

# Write to HTML file
with open('location_history_map.html', 'w', encoding='utf-8') as html_file:
    html_file.write(html_content)

print("HTML file 'location_history_map.html' has been created.")