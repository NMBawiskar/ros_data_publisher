# ROS Topic Viewer

A web-based application for viewing real-time ROS topic data with a beautiful, modern interface.

## Features

- 🎯 **Topic Selection**: Choose from multiple simulated ROS topics via dropdown
- 📊 **Real-time Data**: Continuous streaming of random coordinate values
- 🎨 **Modern UI**: Beautiful gradient design with responsive layout
- ⚡ **Fast Updates**: Data refreshes every 500ms using Server-Sent Events
- 🔄 **Multiple Topics**: Supports position, velocity, and GPS coordinate topics

## Installation

1. Install the required dependencies:
```bash
pip install -r requirements.txt
```

## Running the Application

1. Start the FastAPI server:
```bash
python main.py
```

Or use uvicorn directly:
```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

2. Open your web browser and navigate to:
```
http://localhost:8000
```

## How to Use

1. **Select a Topic**: Use the dropdown menu to choose a ROS topic:
   - `/robot/position` - Random 3D position coordinates (x, y, z)
   - `/robot/velocity` - Random velocity vectors (linear and angular)
   - `/sensor/gps` - Random GPS coordinates

2. **View Data**: Once a topic is selected, you'll see:
   - Real-time coordinate values
   - Timestamp of the last update
   - Connection status indicator

3. **Switch Topics**: Simply select a different topic from the dropdown to switch streams

## API Endpoints

- `GET /` - Main web interface
- `GET /topics` - Returns list of available topics in JSON format
- `GET /stream/{topic_name}` - Server-Sent Events stream for a specific topic

## Technical Details

- **Backend**: FastAPI with Server-Sent Events (SSE) for real-time streaming
- **Frontend**: Vanilla HTML/CSS/JavaScript with EventSource API
- **Data Generation**: Random coordinate values generated every 500ms
- **Styling**: Modern gradient design with smooth animations

## Future Enhancements

- Integration with actual ROS topics
- Data visualization with charts
- Historical data logging
- Multiple simultaneous topic monitoring
- Custom topic configuration
