#!/usr/bin/env python3
"""
PulseAudio Web Control Server
A simple web application to control PulseAudio volume via WebSocket
"""

import asyncio
import json
import logging
import websockets
from http.server import HTTPServer, SimpleHTTPRequestHandler
from threading import Thread
import os
import signal
import sys
import pulsectl

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class PulseAudioController:
    """Controller for PulseAudio volume operations using pulsectl"""
    
    def __init__(self):
        self.pulse = None
        self._connect()
    
    def _connect(self):
        """Connect to PulseAudio"""
        try:
            self.pulse = pulsectl.Pulse('pulseaudio-web-control')
            logger.info("Connected to PulseAudio")
        except Exception as e:
            logger.error(f"Failed to connect to PulseAudio: {e}")
            self.pulse = None
    
    def _ensure_connection(self):
        """Ensure we have a valid PulseAudio connection"""
        if self.pulse is None:
            self._connect()
        return self.pulse is not None
    
    def get_sinks(self):
        """Get list of available audio sinks"""
        if not self._ensure_connection():
            return []
        
        try:
            sinks = []
            for sink in self.pulse.sink_list():
                sinks.append({
                    'id': str(sink.index),
                    'name': sink.description or sink.name
                })
            return sinks
        except Exception as e:
            logger.error(f"Failed to get sinks: {e}")
            return []
    
    def get_sink_volume(self, sink_id):
        """Get volume level for a specific sink"""
        if not self._ensure_connection():
            return 0
        
        try:
            # Find sink by index
            sinks = self.pulse.sink_list()
            sink = None
            for s in sinks:
                if str(s.index) == str(sink_id):
                    sink = s
                    break
            
            if sink is None:
                logger.error(f"Sink with ID {sink_id} not found")
                return 0
            
            # Get volume percentage using value_flat
            volume_percentage = int(round(sink.volume.value_flat * 100))
            logger.debug(f"Sink {sink_id} volume: {volume_percentage}% (muted: {sink.mute})")
            return volume_percentage
        except Exception as e:
            logger.error(f"Failed to get sink volume: {e}")
            return 0
    
    def set_sink_volume(self, sink_id, volume_percent):
        """Set volume level for a specific sink"""
        if not self._ensure_connection():
            return False
        
        try:
            # Find sink by index
            sinks = self.pulse.sink_list()
            sink = None
            for s in sinks:
                if str(s.index) == str(sink_id):
                    sink = s
                    break
            
            if sink is None:
                logger.error(f"Sink with ID {sink_id} not found")
                return False
            
            # Convert percentage to PulseAudio volume scale
            volume_ratio = volume_percent / 100.0
            volume_ratio = max(0.0, min(1.0, volume_ratio))  # Clamp to 0-1 range
            
            logger.info(f"Setting sink {sink_id} volume to {volume_percent}% (ratio: {volume_ratio})")
            
            # Create PulseVolumeInfo object for all channels
            volume_info = pulsectl.PulseVolumeInfo(volume_ratio, len(sink.volume.values))
            
            # Set volume using pulsectl method
            self.pulse.volume_set(sink, volume_info)
            logger.info(f"Successfully set sink {sink_id} volume")
            return True
        except Exception as e:
            logger.error(f"Failed to set sink volume: {e}")
            return False
    
    def toggle_sink_mute(self, sink_id):
        """Toggle mute state for a specific sink"""
        if not self._ensure_connection():
            return False
        
        try:
            # Find sink by index
            sinks = self.pulse.sink_list()
            sink = None
            for s in sinks:
                if str(s.index) == str(sink_id):
                    sink = s
                    break
            
            if sink is None:
                logger.error(f"Sink with ID {sink_id} not found")
                return False
            
            # Toggle mute state
            self.pulse.mute(sink, not sink.mute)
            return True
        except Exception as e:
            logger.error(f"Failed to toggle sink mute: {e}")
            return False
    
    def get_sink_mute(self, sink_id):
        """Get mute state for a specific sink"""
        if not self._ensure_connection():
            return True
        
        try:
            # Find sink by index
            sinks = self.pulse.sink_list()
            sink = None
            for s in sinks:
                if str(s.index) == str(sink_id):
                    sink = s
                    break
            
            if sink is None:
                logger.error(f"Sink with ID {sink_id} not found")
                return True
            
            return sink.mute
        except Exception as e:
            logger.error(f"Failed to get sink mute: {e}")
            return True
    
    def get_applications(self):
        """Get list of applications with audio streams"""
        if not self._ensure_connection():
            return []
        
        try:
            applications = []
            for sink_input in self.pulse.sink_input_list():
                app_name = sink_input.proplist.get('application.name', 'Unknown Application')
                app_id = sink_input.proplist.get('application.process.id', 'unknown')
                applications.append({
                    'id': str(sink_input.index),
                    'name': app_name,
                    'pid': app_id,
                    'sink_id': str(sink_input.sink)
                })
            return applications
        except Exception as e:
            logger.error(f"Failed to get applications: {e}")
            return []
    
    def get_application_volume(self, app_id):
        """Get volume level for a specific application"""
        if not self._ensure_connection():
            return 0
        
        try:
            # Find application by index
            sink_inputs = self.pulse.sink_input_list()
            app = None
            for a in sink_inputs:
                if str(a.index) == str(app_id):
                    app = a
                    break
            
            if app is None:
                logger.error(f"Application with ID {app_id} not found")
                return 0
            
            # Get volume percentage using value_flat
            volume_percentage = int(round(app.volume.value_flat * 100))
            logger.debug(f"App {app_id} volume: {volume_percentage}% (muted: {app.mute})")
            return volume_percentage
        except Exception as e:
            logger.error(f"Failed to get application volume: {e}")
            return 0
    
    def set_application_volume(self, app_id, volume_percent):
        """Set volume level for a specific application"""
        if not self._ensure_connection():
            return False
        
        try:
            # Find application by index
            sink_inputs = self.pulse.sink_input_list()
            app = None
            for a in sink_inputs:
                if str(a.index) == str(app_id):
                    app = a
                    break
            
            if app is None:
                logger.error(f"Application with ID {app_id} not found")
                return False
            
            # Convert percentage to PulseAudio volume scale
            volume_ratio = volume_percent / 100.0
            volume_ratio = max(0.0, min(1.0, volume_ratio))  # Clamp to 0-1 range
            
            logger.info(f"Setting app {app_id} volume to {volume_percent}% (ratio: {volume_ratio})")
            
            # Create PulseVolumeInfo object for all channels
            volume_info = pulsectl.PulseVolumeInfo(volume_ratio, len(app.volume.values))
            
            # Set volume using pulsectl method
            self.pulse.volume_set(app, volume_info)
            logger.info(f"Successfully set app {app_id} volume")
            return True
        except Exception as e:
            logger.error(f"Failed to set application volume: {e}")
            return False
    
    def toggle_application_mute(self, app_id):
        """Toggle mute state for a specific application"""
        if not self._ensure_connection():
            return False
        
        try:
            # Find application by index
            sink_inputs = self.pulse.sink_input_list()
            app = None
            for a in sink_inputs:
                if str(a.index) == str(app_id):
                    app = a
                    break
            
            if app is None:
                logger.error(f"Application with ID {app_id} not found")
                return False
            
            # Toggle mute state
            self.pulse.mute(app, not app.mute)
            return True
        except Exception as e:
            logger.error(f"Failed to toggle application mute: {e}")
            return False
    
    def get_application_mute(self, app_id):
        """Get mute state for a specific application"""
        if not self._ensure_connection():
            return True
        
        try:
            # Find application by index
            sink_inputs = self.pulse.sink_input_list()
            app = None
            for a in sink_inputs:
                if str(a.index) == str(app_id):
                    app = a
                    break
            
            if app is None:
                logger.error(f"Application with ID {app_id} not found")
                return True
            
            return app.mute
        except Exception as e:
            logger.error(f"Failed to get application mute: {e}")
            return True

    def __del__(self):
        """Clean up PulseAudio connection"""
        if self.pulse:
            try:
                self.pulse.close()
            except:
                pass

class WebSocketHandler:
    """Handle WebSocket connections for volume control"""
    
    def __init__(self):
        self.controller = PulseAudioController()
        self.clients = set()
    
    async def register_client(self, websocket):
        """Register a new WebSocket client"""
        self.clients.add(websocket)
        logger.info(f"Client connected. Total clients: {len(self.clients)}")
        
        # Send initial data
        await self.send_initial_data(websocket)
    
    async def unregister_client(self, websocket):
        """Unregister a WebSocket client"""
        self.clients.discard(websocket)
        logger.info(f"Client disconnected. Total clients: {len(self.clients)}")
    
    async def send_initial_data(self, websocket):
        """Send initial data to a new client"""
        sinks = self.controller.get_sinks()
        sink_data = []
        
        logger.info(f"Found {len(sinks)} sinks")
        
        for sink in sinks:
            volume = self.controller.get_sink_volume(sink['id'])
            muted = self.controller.get_sink_mute(sink['id'])
            logger.info(f"Sink {sink['id']} ({sink['name']}): volume={volume}%, muted={muted}")
            sink_data.append({
                'id': sink['id'],
                'name': sink['name'],
                'volume': volume,
                'muted': muted
            })
        
        # Get applications
        applications = self.controller.get_applications()
        app_data = []
        
        logger.info(f"Found {len(applications)} applications")
        
        for app in applications:
            volume = self.controller.get_application_volume(app['id'])
            muted = self.controller.get_application_mute(app['id'])
            logger.info(f"App {app['id']} ({app['name']}): volume={volume}%, muted={muted}")
            app_data.append({
                'id': app['id'],
                'name': app['name'],
                'pid': app['pid'],
                'sink_id': app['sink_id'],
                'volume': volume,
                'muted': muted
            })
        
        message = {
            'type': 'initial_data',
            'sinks': sink_data,
            'applications': app_data
        }
        
        logger.info(f"Sending initial data: {json.dumps(message, indent=2)}")
        
        try:
            await websocket.send(json.dumps(message))
        except websockets.exceptions.ConnectionClosed:
            pass
    
    async def broadcast_update(self, sink_id, volume=None, muted=None):
        """Broadcast volume/mute updates to all clients"""
        if not self.clients:
            return
        
        message = {
            'type': 'update',
            'sink_id': sink_id,
            'volume': volume,
            'muted': muted
        }
        
        # Send to all connected clients
        disconnected = set()
        for client in self.clients:
            try:
                await client.send(json.dumps(message))
            except websockets.exceptions.ConnectionClosed:
                disconnected.add(client)
        
        # Remove disconnected clients
        self.clients -= disconnected
    
    async def broadcast_app_update(self, app_id, volume=None, muted=None):
        """Broadcast application volume/mute updates to all clients"""
        if not self.clients:
            return
        
        message = {
            'type': 'app_update',
            'app_id': app_id,
            'volume': volume,
            'muted': muted
        }
        
        # Send to all connected clients
        disconnected = set()
        for client in self.clients:
            try:
                await client.send(json.dumps(message))
            except websockets.exceptions.ConnectionClosed:
                disconnected.add(client)
        
        # Remove disconnected clients
        self.clients -= disconnected
    
    async def handle_message(self, websocket, message):
        """Handle incoming WebSocket messages"""
        try:
            data = json.loads(message)
            message_type = data.get('type')
            
            if message_type == 'set_volume':
                sink_id = data.get('sink_id')
                volume = data.get('volume')
                
                if sink_id is not None and volume is not None:
                    success = self.controller.set_sink_volume(sink_id, volume)
                    if success:
                        await self.broadcast_update(sink_id, volume=volume)
                    
                    # Send response
                    response = {
                        'type': 'volume_set',
                        'sink_id': sink_id,
                        'volume': volume,
                        'success': success
                    }
                    await websocket.send(json.dumps(response))
            
            elif message_type == 'toggle_mute':
                sink_id = data.get('sink_id')
                
                if sink_id is not None:
                    success = self.controller.toggle_sink_mute(sink_id)
                    if success:
                        muted = self.controller.get_sink_mute(sink_id)
                        volume = self.controller.get_sink_volume(sink_id)
                        await self.broadcast_update(sink_id, volume=volume, muted=muted)
                    
                    # Send response
                    response = {
                        'type': 'mute_toggled',
                        'sink_id': sink_id,
                        'muted': self.controller.get_sink_mute(sink_id),
                        'volume': self.controller.get_sink_volume(sink_id),
                        'success': success
                    }
                    await websocket.send(json.dumps(response))
            
            elif message_type == 'set_app_volume':
                app_id = data.get('app_id')
                volume = data.get('volume')
                
                if app_id is not None and volume is not None:
                    success = self.controller.set_application_volume(app_id, volume)
                    if success:
                        await self.broadcast_app_update(app_id, volume=volume)
                    
                    # Send response
                    response = {
                        'type': 'app_volume_set',
                        'app_id': app_id,
                        'volume': volume,
                        'success': success
                    }
                    await websocket.send(json.dumps(response))
            
            elif message_type == 'toggle_app_mute':
                app_id = data.get('app_id')
                
                if app_id is not None:
                    success = self.controller.toggle_application_mute(app_id)
                    if success:
                        muted = self.controller.get_application_mute(app_id)
                        volume = self.controller.get_application_volume(app_id)
                        await self.broadcast_app_update(app_id, volume=volume, muted=muted)
                    
                    # Send response
                    response = {
                        'type': 'app_mute_toggled',
                        'app_id': app_id,
                        'muted': self.controller.get_application_mute(app_id),
                        'volume': self.controller.get_application_volume(app_id),
                        'success': success
                    }
                    await websocket.send(json.dumps(response))
            
            elif message_type == 'refresh':
                await self.send_initial_data(websocket)
        
        except json.JSONDecodeError:
            logger.error("Invalid JSON received")
        except Exception as e:
            logger.error(f"Error handling message: {e}")
    
    async def handle_client(self, websocket):
        """Handle a WebSocket client connection"""
        await self.register_client(websocket)
        try:
            async for message in websocket:
                await self.handle_message(websocket, message)
        except websockets.exceptions.ConnectionClosed:
            pass
        finally:
            await self.unregister_client(websocket)

# Global WebSocket handler instance
ws_handler = WebSocketHandler()

async def websocket_server():
    """Start the WebSocket server"""
    logger.info("Starting WebSocket server on localhost:8765")
    async with websockets.serve(ws_handler.handle_client, "localhost", 8765):
        await asyncio.Future()  # Run forever

def start_http_server():
    """Start the HTTP server for serving static files"""
    class CustomHTTPRequestHandler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=os.path.dirname(os.path.abspath(__file__)), **kwargs)
        
        def end_headers(self):
            # Add CORS headers
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
            self.send_header('Access-Control-Allow-Headers', 'Content-Type')
            super().end_headers()
    
    httpd = HTTPServer(('localhost', 8089), CustomHTTPRequestHandler)
    logger.info("Starting HTTP server on localhost:8089")
    httpd.serve_forever()

def signal_handler(signum, frame):
    """Handle shutdown signals"""
    logger.info("Shutting down...")
    sys.exit(0)

async def main():
    """Main function to start both servers"""
    # Set up signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Start HTTP server in a separate thread
    http_thread = Thread(target=start_http_server, daemon=True)
    http_thread.start()
    
    # Start WebSocket server
    await websocket_server()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Server stopped by user")
    except Exception as e:
        logger.error(f"Server error: {e}")
        sys.exit(1)
