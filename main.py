from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import json
import asyncio
import random
from datetime import datetime
from typing import Dict
import subprocess
import re
import sys
import os

app = FastAPI(title="ROS Topic Viewer")

# Configure templates
templates = Jinja2Templates(directory="templates")

# Available topics with their data types
TOPICS = {
    "/robot/position": "geometry_msgs/Point",
    "/robot/velocity": "geometry_msgs/Twist",
    "/sensor/gps": "sensor_msgs/NavSatFix",
    "/turtle1/pose": "turtlesim/Pose"
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

def parse_ros2_generic_output(output_line: str, data_buffer: Dict, parser_state: Dict) -> None:
    """
    Generic parser for ROS2 topic echo output.
    Parses any message format including nested structures.
    
    Args:
        output_line: Single line from ros2 topic echo (with original indentation)
        data_buffer: Dictionary to store parsed data
        parser_state: State information for parsing (indentation tracking, etc.)
    """
    # Skip lines that are just separators or empty
    if not output_line or output_line.strip() == '---' or not output_line.strip():
        return
    
    # Count leading spaces for indentation level
    indent = len(output_line) - len(output_line.lstrip())
    line = output_line.strip()
    
    # Match key:value pattern
    match = re.match(r'^([a-zA-Z_][a-zA-Z0-9_]*)\s*:\s*(.*)$', line)
    
    if match:
        key = match.group(1)
        value = match.group(2).strip()
        
        # Initialize indent stack if needed
        if 'indent_stack' not in parser_state:
            parser_state['indent_stack'] = []
        
        # Pop stack until we find the correct parent level
        while parser_state['indent_stack'] and parser_state['indent_stack'][-1]['indent'] >= indent:
            parser_state['indent_stack'].pop()
        
        # Build the full key path
        if parser_state['indent_stack']:
            parent_path = parser_state['indent_stack'][-1]['path']
            full_key = f"{parent_path}.{key}"
        else:
            full_key = key
        
        # If value is empty, this is a parent for nested fields
        if not value:
            parser_state['indent_stack'].append({'indent': indent, 'path': full_key})
        else:
            # Try to parse value as number, otherwise keep as string
            try:
                # Try integer first
                if '.' not in value and 'e' not in value.lower():
                    parsed_value = int(value)
                else:
                    parsed_value = float(value)
            except ValueError:
                # Keep as string
                parsed_value = value
            
            # Store in data buffer with full path
            data_buffer[full_key] = parsed_value


def flatten_to_nested_dict(flat_dict: Dict) -> Dict:
    """Convert flat dictionary with dot notation to nested dictionary"""
    result = {}
    
    for key, value in flat_dict.items():
        parts = key.split('.')
        current = result
        
        for i, part in enumerate(parts[:-1]):
            if part not in current:
                current[part] = {}
            current = current[part]
        
        current[parts[-1]] = value
    
    return result


async def ros2_topic_generator(topic_name: str):
    """Generate Server-Sent Events stream from ROS2 topic using subprocess"""
    process = None
    try:
        print(f"Starting ROS2 topic echo for {topic_name}...")
        
        # Prepare environment - source the correct ROS2 distro
        env = os.environ.copy()
        
        # Force use of ROS2 humble if on Linux and rolling is detected
        if sys.platform == 'linux' and env.get('ROS_DISTRO') == 'rolling':
            print(f"Detected ROS_DISTRO=rolling, switching to humble...")
            
            # Clear ROS-related environment variables to avoid conflicts
            ros_vars_to_clear = [k for k in env.keys() if k.startswith('ROS_') or k.startswith('AMENT_') or 'ros' in k.lower()]
            for var in ros_vars_to_clear:
                if var in ['ROSLISP_PACKAGE_DIRECTORIES', 'ROS_DISTRO', 'ROS_VERSION', 'ROS_PYTHON_VERSION']:
                    del env[var]
            
            # Source humble and run ros2 topic echo with --no-daemon to avoid daemon conflicts
            cmd = f'source /opt/ros/humble/setup.bash && ros2 topic echo {topic_name} --no-daemon'
            print(f"Running command: {cmd}")
        else:
            # Use --no-daemon flag to bypass daemon (avoids compatibility issues)
            cmd = f'ros2 topic echo {topic_name} --no-daemon'
            print(f"Running command: {cmd}")
        
        print(f"Original ROS_DISTRO: {os.environ.get('ROS_DISTRO', 'Not set')}")
        
        # Use shell mode on both Windows and Linux to properly handle environment
        # On Linux, we need to use bash explicitly to handle 'source' command
        if sys.platform == 'linux':
            process = await asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
                executable='/bin/bash'
            )
        else:
            process = await asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env
            )
        
        print(f"Subprocess started successfully. PID: {process.pid}")
        
        # Wait a moment and check for immediate errors
        await asyncio.sleep(0.2)
        
        # Check if process died immediately
        if process.returncode is not None:
            stderr_output = await process.stderr.read()
            error_msg = stderr_output.decode() if stderr_output else "No error message"
            print(f"Process died immediately with code {process.returncode}")
            print(f"STDERR: {error_msg}")
            raise Exception(f"ROS2 command failed: {error_msg}")
        
        data_buffer = {}
        parser_state = {}
        line_count = 0
        last_complete_data = None
        messages_pending = []
        
        # Read output line by line
        while True:
            # Check if process is still running
            if process.returncode is not None:
                print(f"Process terminated with return code: {process.returncode}")
                # Read any remaining stderr
                try:
                    stderr_output = await asyncio.wait_for(process.stderr.read(), timeout=0.5)
                    if stderr_output:
                        print(f"STDERR: {stderr_output.decode()}")
                except asyncio.TimeoutError:
                    pass
                break
            
            try:
                # Read all available lines to avoid lag - don't wait if no data
                lines_read = 0
                while True:
                    try:
                        line = await asyncio.wait_for(process.stdout.readline(), timeout=0.01)
                        if line:
                            # Decode but keep leading spaces for indentation detection
                            line = line.decode().rstrip()  # Only strip trailing whitespace
                            line_count += 1
                            lines_read += 1
                            
                            # Check for message separator (after stripping for comparison)
                            if line.strip() == '---':
                                # If we have complete data, add it to pending messages
                                if data_buffer:
                                    # Convert flat dict to nested structure
                                    nested_data = flatten_to_nested_dict(data_buffer)
                                    messages_pending.append(nested_data)
                                    print(f"Message buffered (total pending: {len(messages_pending)}): {list(nested_data.keys())}")
                                
                                # Reset for next message
                                data_buffer = {}
                                parser_state = {}
                            else:
                                # Parse the output line using generic parser (preserve leading spaces)
                                parse_ros2_generic_output(line, data_buffer, parser_state)
                        else:
                            # EOF reached
                            print("EOF reached on stdout")
                            break
                    except asyncio.TimeoutError:
                        # No more data available right now
                        break
                
                # After reading all available data, send only the MOST RECENT message
                if messages_pending:
                    # Get the most recent message (last in list)
                    latest_data = messages_pending[-1]
                    skipped = len(messages_pending) - 1
                    
                    if skipped > 0:
                        print(f"Skipping {skipped} old messages, sending latest only")
                    
                    timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
                    
                    # Format data for SSE - use the nested structure directly
                    data = {
                        "topic": topic_name,
                        "timestamp": timestamp,
                        "data": latest_data
                    }
                    
                    # Yield formatted SSE data
                    print(f"Sending latest data: {str(latest_data)[:100]}...")
                    yield f"data: {json.dumps(data)}\n\n"
                    
                    # Clear pending messages
                    messages_pending = []
                
                # Small delay before next read cycle
                await asyncio.sleep(0.05)
                
            except Exception as loop_error:
                print(f"Error in read loop: {loop_error}")
                await asyncio.sleep(0.1)
            
    except Exception as e:
        print(f"ERROR in ros2_topic_generator: {e}")
        import traceback
        traceback.print_exc()
        error_data = {
            "topic": topic_name,
            "timestamp": datetime.now().strftime("%H:%M:%S.%f")[:-3],
            "error": str(e)
        }
        yield f"data: {json.dumps(error_data)}\n\n"
    finally:
        if process and process.returncode is None:
            print(f"Terminating subprocess for {topic_name}")
            process.terminate()
            await process.wait()
            print(f"Subprocess terminated")



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
    """Return list of available topics from ROS2"""
    try:
        print("Fetching ROS2 topics...")
        
        # Prepare environment
        env = os.environ.copy()
        
        # Build command
        if sys.platform == 'linux' and env.get('ROS_DISTRO') == 'rolling':
            cmd = 'source /opt/ros/humble/setup.bash && ros2 topic list --no-daemon'
        else:
            cmd = 'ros2 topic list --no-daemon'
        
        print(f"Running: {cmd}")
        
        # Run ros2 topic list command
        if sys.platform == 'linux':
            process = await asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
                executable='/bin/bash'
            )
        else:
            process = await asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env
            )
        
        # Wait for command to complete with timeout
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=5.0)
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
            return {
                "error": "Command timeout",
                "message": "ros2 topic list command took too long. Is ROS2 running?"
            }
        
        # Check return code
        if process.returncode != 0:
            error_msg = stderr.decode().strip() if stderr else "Unknown error"
            print(f"Error fetching topics: {error_msg}")
            return {
                "error": "Command failed",
                "message": error_msg or "Failed to list topics. Is ROS2 running?",
                "returncode": process.returncode
            }
        
        # Parse output
        output = stdout.decode().strip()
        
        if not output:
            return {
                "error": "No topics",
                "message": "No topics found. Make sure ROS2 nodes are running.",
                "topics": []
            }
        
        # Split by newlines to get topic list
        topics = [line.strip() for line in output.split('\n') if line.strip()]
        
        print(f"Found {len(topics)} topics: {topics}")
        
        # Return topics with type (we can attempt to get type info too)
        return {
            "topics": [{"name": topic, "type": "unknown"} for topic in topics]
        }
        
    except Exception as e:
        print(f"Exception while fetching topics: {e}")
        import traceback
        traceback.print_exc()
        return {
            "error": "Exception",
            "message": str(e)
        }


@app.get("/stream/{topic_name:path}")
async def stream_topic(topic_name: str):
    """Stream data from a specific topic using Server-Sent Events"""
    # Use ROS2 subprocess for any topic (no longer checking TOPICS dict)
    generator = ros2_topic_generator(topic_name)
    
    return StreamingResponse(
        generator,
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
