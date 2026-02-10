from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import json
import asyncio
import random
from datetime import datetime
from typing import Dict

app = FastAPI(title="ROS Topic Viewer")

# Configure templates
templates = Jinja2Templates(directory="templates")

# Available topics with their data types
TOPICS = {
    "/robot/position": "geometry_msgs/Point",
    "/robot/velocity": "geometry_msgs/Twist",
    "/sensor/gps": "sensor_msgs/NavSatFix"
}


def generate_random_coordinates(topic_name: str) -> Dict:
    """Generate random coordinate values based on topic type"""
    timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    
    if "position" in topic_name or "gps" in topic_name:
        return {
            "topic": topic_name,
            "timestamp": timestamp,
            "data": {
                "x": round(random.uniform(-100, 100), 3),
                "y": round(random.uniform(-100, 100), 3),
                "z": round(random.uniform(0, 50), 3)
            }
        }
    elif "velocity" in topic_name:
        return {
            "topic": topic_name,
            "timestamp": timestamp,
            "data": {
                "linear": {
                    "x": round(random.uniform(-5, 5), 3),
                    "y": round(random.uniform(-5, 5), 3),
                    "z": round(random.uniform(-2, 2), 3)
                },
                "angular": {
                    "x": round(random.uniform(-1, 1), 3),
                    "y": round(random.uniform(-1, 1), 3),
                    "z": round(random.uniform(-1, 1), 3)
                }
            }
        }
    else:
        return {
            "topic": topic_name,
            "timestamp": timestamp,
            "data": {
                "x": round(random.uniform(-10, 10), 3),
                "y": round(random.uniform(-10, 10), 3)
            }
        }


async def event_generator(topic_name: str):
    """Generate Server-Sent Events stream for a specific topic"""
    while True:
        # Generate random coordinates
        data = generate_random_coordinates(topic_name)
        
        # Format as SSE
        yield f"data: {json.dumps(data)}\n\n"
        
        # Send updates every 500ms
        await asyncio.sleep(0.5)


@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    """Serve the main HTML page"""
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/topics")
async def get_topics():
    """Return list of available topics"""
    return [{"name": name, "type": msg_type} for name, msg_type in TOPICS.items()]


@app.get("/stream/{topic_name:path}")
async def stream_topic(topic_name: str):
    """Stream data from a specific topic using Server-Sent Events"""
    if topic_name not in TOPICS:
        return {"error": "Topic not found"}
    
    return StreamingResponse(
        event_generator(topic_name),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
