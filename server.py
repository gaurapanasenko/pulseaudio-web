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
import time
import pulsectl
import argparse

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def parse_arguments():
    """Parse command line arguments for host and port configuration"""
    parser = argparse.ArgumentParser(description='PulseAudio Web Control Server')
    parser.add_argument('--host', default='0.0.0.0', 
                       help='Host to bind the servers to (default: 0.0.0.0)')
    parser.add_argument('--port', type=int, default=8080,
                       help='Port for HTTP server (default: 8080). WebSocket will use port + 685')
    args = parser.parse_args()
    
    # Calculate WebSocket port as HTTP port + 685
    args.ws_port = args.port + 685
    
    return args

class PulseAudioController:
    """Controller for PulseAudio volume operations using pulsectl"""
    
    def __init__(self):
        self.pulse = None
        self._connect()
        
        # Change tracking for efficient updates
        self._last_sink_data = {}
        self._last_app_data = {}
        self._last_card_data = {}
        self._last_sink_ids = set()
        self._last_app_ids = set()
        self._last_card_ids = set()
        
        # Cache for sink objects to avoid repeated sink_list() calls
        self._sink_cache = {}
        self._sink_cache_timestamp = 0
        
        # Cache for application objects to avoid repeated sink_input_list() calls
        self._app_cache = {}
        self._app_cache_timestamp = 0
    
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
    
    def _get_sink_by_id(self, sink_id):
        """Get sink object by ID, using cache to avoid repeated sink_list() calls"""
        if not self._ensure_connection():
            return None
        
        # Refresh cache if it's empty or if we don't have this sink
        if not self._sink_cache or sink_id not in self._sink_cache:
            self._refresh_sink_cache()
        
        return self._sink_cache.get(sink_id)
    
    def _refresh_sink_cache(self):
        """Refresh the sink cache with current sink objects"""
        try:
            self._sink_cache.clear()
            for sink in self.pulse.sink_list():
                self._sink_cache[str(sink.index)] = sink
            self._sink_cache_timestamp = time.time()
        except Exception as e:
            logger.error(f"Failed to refresh sink cache: {e}")
            self._sink_cache.clear()
    
    def _get_app_by_id(self, app_id):
        """Get application object by ID, using cache to avoid repeated sink_input_list() calls"""
        if not self._ensure_connection():
            return None
        
        # Refresh cache if it's empty or if we don't have this app
        if not self._app_cache or app_id not in self._app_cache:
            self._refresh_app_cache()
        
        return self._app_cache.get(app_id)
    
    def _refresh_app_cache(self):
        """Refresh the app cache with current application objects"""
        try:
            self._app_cache.clear()
            for app in self.pulse.sink_input_list():
                self._app_cache[str(app.index)] = app
            self._app_cache_timestamp = time.time()
        except Exception as e:
            logger.error(f"Failed to refresh app cache: {e}")
            self._app_cache.clear()
    
    def get_sinks(self):
        """Get list of available audio sinks"""
        if not self._ensure_connection():
            return []
        
        try:
            # Refresh cache to ensure we have current data
            self._refresh_sink_cache()
            
            sinks = []
            default_sink = self.pulse.server_info().default_sink_name
            for sink in self._sink_cache.values():
                sinks.append({
                    'id': str(sink.index),
                    'name': sink.description or sink.name,
                    'is_default': sink.name == default_sink,
                    'pulse_sink': sink  # Include the pulse sink object
                })
            return sinks
        except Exception as e:
            logger.error(f"Failed to get sinks: {e}")
            return []
    
    def get_sink_volume(self, sink):
        """Get volume level from pulse sink object"""
        try:
            # Get volume percentage using value_flat
            volume_percentage = int(round(sink.volume.value_flat * 100))
            return volume_percentage
        except Exception as e:
            logger.error(f"Failed to get sink volume from object: {e}")
            return 0
    
    def set_sink_volume(self, sink_id, volume_percent):
        """Set volume level for a specific sink"""
        sink = self._get_sink_by_id(sink_id)
        if sink is None:
            logger.error(f"Sink with ID {sink_id} not found")
            return False
        
        try:
            # Convert percentage to PulseAudio volume scale
            volume_ratio = volume_percent / 100.0
            volume_ratio = max(0.0, min(1.0, volume_ratio))  # Clamp to 0-1 range
            
            logger.info(f"Setting sink {sink_id} volume to {volume_percent}% (ratio: {volume_ratio})")
            
            # Create PulseVolumeInfo object for all channels
            volume_info = pulsectl.PulseVolumeInfo(volume_ratio, len(sink.volume.values))
            
            # Set volume using pulsectl method
            self.pulse.volume_set(sink, volume_info)
            logger.info(f"Successfully set sink {sink_id} volume")
            
            # Invalidate cache since we modified the sink
            self._sink_cache.clear()
            return True
        except Exception as e:
            logger.error(f"Failed to set sink volume: {e}")
            return False
    
    def toggle_sink_mute(self, sink_id):
        """Toggle mute state for a specific sink"""
        sink = self._get_sink_by_id(sink_id)
        if sink is None:
            logger.error(f"Sink with ID {sink_id} not found")
            return False
        
        try:
            # Toggle mute state
            self.pulse.mute(sink, not sink.mute)
            
            # Invalidate cache since we modified the sink
            self._sink_cache.clear()
            return True
        except Exception as e:
            logger.error(f"Failed to toggle sink mute: {e}")
            return False
    
    def get_sink_mute(self, sink):
        """Get mute state from pulse sink object"""
        try:
            return sink.mute
        except Exception as e:
            logger.error(f"Failed to get sink mute from object: {e}")
            return True
    
    def get_applications(self):
        """Get list of applications with audio streams"""
        if not self._ensure_connection():
            return []
        
        try:
            # Refresh cache to ensure we have current data
            self._refresh_app_cache()
            
            applications = []
            for app in self._app_cache.values():
                app_name = app.proplist.get('application.name', 'Unknown Application')
                app_id = app.proplist.get('application.process.id', 'unknown')
                applications.append({
                    'id': str(app.index),
                    'name': app_name,
                    'pid': app_id,
                    'sink_id': str(app.sink),
                    'pulse_app': app  # Include the pulse app object
                })
            return applications
        except Exception as e:
            logger.error(f"Failed to get applications: {e}")
            return []
    
    def get_application_volume(self, app):
        """Get volume level from pulse app object"""
        try:
            # Get volume percentage using value_flat
            volume_percentage = int(round(app.volume.value_flat * 100))
            return volume_percentage
        except Exception as e:
            logger.error(f"Failed to get application volume from object: {e}")
            return 0
    
    def set_application_volume(self, app_id, volume_percent):
        """Set volume level for a specific application"""
        app = self._get_app_by_id(app_id)
        if app is None:
            logger.error(f"Application with ID {app_id} not found")
            return False
        
        try:
            # Convert percentage to PulseAudio volume scale
            volume_ratio = volume_percent / 100.0
            volume_ratio = max(0.0, min(1.0, volume_ratio))  # Clamp to 0-1 range
            
            logger.info(f"Setting app {app_id} volume to {volume_percent}% (ratio: {volume_ratio})")
            
            # Create PulseVolumeInfo object for all channels
            volume_info = pulsectl.PulseVolumeInfo(volume_ratio, len(app.volume.values))
            
            # Set volume using pulsectl method
            self.pulse.volume_set(app, volume_info)
            logger.info(f"Successfully set app {app_id} volume")
            
            # Invalidate cache since we modified the app
            self._app_cache.clear()
            return True
        except Exception as e:
            logger.error(f"Failed to set application volume: {e}")
            return False
    
    def toggle_application_mute(self, app_id):
        """Toggle mute state for a specific application"""
        app = self._get_app_by_id(app_id)
        if app is None:
            logger.error(f"Application with ID {app_id} not found")
            return False
        
        try:
            # Toggle mute state
            self.pulse.mute(app, not app.mute)
            
            # Invalidate cache since we modified the app
            self._app_cache.clear()
            return True
        except Exception as e:
            logger.error(f"Failed to toggle application mute: {e}")
            return False
    
    def get_application_mute(self, app):
        """Get mute state from pulse app object"""
        try:
            return app.mute
        except Exception as e:
            logger.error(f"Failed to get application mute from object: {e}")
            return True
    
    def set_default_sink(self, sink_id):
        """Set the default sink for audio playback"""
        sink = self._get_sink_by_id(sink_id)
        if sink is None:
            logger.error(f"Sink with ID {sink_id} not found")
            return False
        
        try:
            # Set as default sink
            self.pulse.sink_default_set(sink)
            logger.info(f"Set sink {sink_id} ({sink.name}) as default")
            return True
        except Exception as e:
            logger.error(f"Failed to set default sink: {e}")
            return False
    
    def move_application_to_sink(self, app_id, sink_id):
        """Move an application's audio stream to a different sink"""
        if not self._ensure_connection():
            return False
        
        try:
            # Find application by index
            app = self._get_app_by_id(app_id)
            if app is None:
                logger.error(f"Application with ID {app_id} not found")
                return False
            
            # Find target sink by index
            target_sink = self._get_sink_by_id(sink_id)
            if target_sink is None:
                logger.error(f"Target sink with ID {sink_id} not found")
                return False
            
            # Move application to target sink
            self.pulse.sink_input_move(app.index, target_sink.index)
            logger.info(f"Moved application {app_id} to sink {sink_id} ({target_sink.name})")
            return True
        except Exception as e:
            logger.error(f"Failed to move application to sink: {e}")
            return False
    
    
    def get_cards(self):
        """Get list of audio cards with their profiles"""
        if not self._ensure_connection():
            return []
        
        try:
            cards = []
            for card in self.pulse.card_list():
                # Get current profile
                current_profile = card.profile_active.name if card.profile_active else 'unknown'
                
                # Get all available profiles
                profiles = []
                for profile in card.profile_list:
                    profiles.append({
                        'name': profile.name,
                        'description': profile.description
                    })
                
                cards.append({
                    'id': str(card.index),
                    'name': card.name,
                    'description': card.proplist.get('device.description', card.name),
                    'profiles': profiles,
                    'current_profile': current_profile
                })
            
            return cards
        except Exception as e:
            logger.error(f"Failed to get cards: {e}")
            return []
    
    def set_card_profile(self, card_id, profile_name):
        """Set the profile for a specific card"""
        if not self._ensure_connection():
            return False
        
        try:
            # Find card by index
            cards = self.pulse.card_list()
            card = None
            for c in cards:
                if str(c.index) == str(card_id):
                    card = c
                    break
            
            if card is None:
                logger.error(f"Card with ID {card_id} not found")
                return False
            
            # Find the profile and set it
            for profile in card.profile_list:
                if profile.name == profile_name:
                    self.pulse.card_profile_set(card, profile)
                    logger.info(f"Set card {card_id} profile to {profile_name}")
                    return True
            
            logger.error(f"Profile {profile_name} not found for card {card_id}")
            return False
        except Exception as e:
            logger.error(f"Failed to set card profile: {e}")
            return False

    def get_sink_status(self, sink):
        """Get sink activity state from pulse sink object (running and not muted = active)"""
        try:
            is_running = 'running' in str(sink.state)
            return is_running and not sink.mute
        except Exception as e:
            logger.error(f"Failed to get sink state from object: {e}")
            return False
    
    def get_application_status(self, app):
        """Get application activity state from pulse app object (not corked and not muted = active)"""
        try:
            return not app.corked and not app.mute
        except Exception as e:
            logger.error(f"Failed to get application state from object: {e}")
            return False

    def get_light_data(self):
        """Get light data (volumes, states) without heavy names"""
        try:
            sinks = self.get_sinks()
            applications = self.get_applications()
            cards = self.get_cards()
            
            # Create light data structures
            light_sinks = {}
            light_apps = {}
            light_cards = {}
            
            for sink in sinks:
                pulse_sink = sink['pulse_sink']
                volume = self.get_sink_volume(pulse_sink)
                muted = self.get_sink_mute(pulse_sink)
                status = self.get_sink_status(pulse_sink)
                light_sinks[sink['id']] = {
                    'volume': volume,
                    'muted': muted,
                    'is_default': sink['is_default'],
                    'status': status
                }
            
            for app in applications:
                pulse_app = app['pulse_app']
                volume = self.get_application_volume(pulse_app)
                muted = self.get_application_mute(pulse_app)
                status = self.get_application_status(pulse_app)
                light_apps[app['id']] = {
                    'volume': volume,
                    'muted': muted,
                    'sink_id': app['sink_id'],
                    'status': status
                }
            
            for card in cards:
                light_cards[card['id']] = {
                    'current_profile': card['current_profile']
                }
            
            return {
                'sinks': light_sinks,
                'applications': light_apps,
                'cards': light_cards
            }
            
        except Exception as e:
            logger.error(f"Error getting light data: {e}")
            return {'sinks': {}, 'applications': {}, 'cards': {}}

    def get_changed_data(self):
        """Get only the data that has changed since last check"""
        changes = {
            'list_changed': False,
            'light_data': {'sinks': {}, 'applications': {}, 'cards': {}}
        }
        
        try:
            # Get current IDs
            current_sinks = self.get_sinks()
            current_apps = self.get_applications()
            current_cards = self.get_cards()
            
            current_sink_ids = {sink['id'] for sink in current_sinks}
            current_app_ids = {app['id'] for app in current_apps}
            current_card_ids = {card['id'] for card in current_cards}
            
            # Check if lists changed by comparing with previously stored IDs
            if (current_sink_ids != self._last_sink_ids or 
                current_app_ids != self._last_app_ids or 
                current_card_ids != self._last_card_ids):
                changes['list_changed'] = True
                changes['ids'] = {
                    'sinks': list(current_sink_ids),
                    'applications': list(current_app_ids),
                    'cards': list(current_card_ids)
                }
                
                # Update stored IDs
                self._last_sink_ids = current_sink_ids.copy()
                self._last_app_ids = current_app_ids.copy()
                self._last_card_ids = current_card_ids.copy()
            
            # Get light data for all items
            light_data = self.get_light_data()
            
            # Check for changes in light data (including status)
            for sink_id, sink_data in light_data['sinks'].items():
                if sink_id not in self._last_sink_data or self._last_sink_data[sink_id] != sink_data:
                    changes['light_data']['sinks'][sink_id] = sink_data
                    self._last_sink_data[sink_id] = sink_data.copy()
            
            for app_id, app_data in light_data['applications'].items():
                if app_id not in self._last_app_data or self._last_app_data[app_id] != app_data:
                    changes['light_data']['applications'][app_id] = app_data
                    self._last_app_data[app_id] = app_data.copy()
            
            for card_id, card_data in light_data['cards'].items():
                if card_id not in self._last_card_data or self._last_card_data[card_id] != card_data:
                    changes['light_data']['cards'][card_id] = card_data
                    self._last_card_data[card_id] = card_data.copy()
            
            return changes
            
        except Exception as e:
            logger.error(f"Error getting changed data: {e}")
            return changes

    def get_detailed_data_by_ids(self, sink_ids=None, app_ids=None, card_ids=None):
        """Get detailed data (including names) for specific IDs"""
        try:
            result = {'sinks': {}, 'applications': {}, 'cards': {}}
            
            if sink_ids:
                sinks = self.get_sinks()
                for sink in sinks:
                    if sink['id'] in sink_ids:
                        # Create clean copy without pulse object
                        clean_sink = {
                            'id': sink['id'],
                            'name': sink['name'],
                            'is_default': sink['is_default']
                        }
                        result['sinks'][sink['id']] = clean_sink
            
            if app_ids:
                applications = self.get_applications()
                for app in applications:
                    if app['id'] in app_ids:
                        # Create clean copy without pulse object
                        clean_app = {
                            'id': app['id'],
                            'name': app['name'],
                            'pid': app['pid'],
                            'sink_id': app['sink_id']
                        }
                        result['applications'][app['id']] = clean_app
            
            if card_ids:
                cards = self.get_cards()
                for card in cards:
                    if card['id'] in card_ids:
                        result['cards'][card['id']] = card
            
            return result
            
        except Exception as e:
            logger.error(f"Error getting detailed data: {e}")
            return {'sinks': {}, 'applications': {}, 'cards': {}}

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
        self.audio_level_task = None
    
    async def register_client(self, websocket):
        """Register a new WebSocket client"""
        self.clients.add(websocket)
        logger.info(f"Client connected. Total clients: {len(self.clients)}")
        
        # Force an update by clearing change tracking so new client gets data
        self.controller._last_sink_data.clear()
        self.controller._last_app_data.clear()
        self.controller._last_card_data.clear()
        self.controller._last_sink_ids.clear()
        self.controller._last_app_ids.clear()
        self.controller._last_card_ids.clear()
    
    async def unregister_client(self, websocket):
        """Unregister a WebSocket client"""
        self.clients.discard(websocket)
        logger.info(f"Client disconnected. Total clients: {len(self.clients)}")
    
    
    
    
    async def start_auto_monitoring(self):
        """Start automatic monitoring with efficient change detection"""
        while True:
            try:
                if self.clients:
                    # Get only changed data
                    changes = self.controller.get_changed_data()
                    
                    # Send updates only if there are changes
                    has_changes = (changes['list_changed'] or 
                                 any(changes['light_data'].values()))
                    
                    if has_changes:
                        # Send list changes (IDs only)
                        if changes['list_changed']:
                            message = {
                                'type': 'list_update',
                                'ids': changes['ids']
                            }
                            await self._broadcast_to_all(message)
                        
                        # Send light data changes (volumes, states, status without names)
                        if any(changes['light_data'].values()):
                            message = {
                                'type': 'light_data_update',
                                'data': changes['light_data']
                            }
                            await self._broadcast_to_all(message)
                
                # Wait 200ms before next check (5 FPS)
                await asyncio.sleep(0.2)
                
            except Exception as e:
                logger.error(f"Error in auto monitoring: {e}")
                await asyncio.sleep(1)  # Wait longer on error
    
    async def _broadcast_to_all(self, message):
        """Broadcast message to all connected clients"""
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
            
            elif message_type == 'toggle_mute':
                sink_id = data.get('sink_id')
                
                if sink_id is not None:
                    success = self.controller.toggle_sink_mute(sink_id)
            
            elif message_type == 'set_app_volume':
                app_id = data.get('app_id')
                volume = data.get('volume')
                
                if app_id is not None and volume is not None:
                    success = self.controller.set_application_volume(app_id, volume)
            
            elif message_type == 'toggle_app_mute':
                app_id = data.get('app_id')
                
                if app_id is not None:
                    success = self.controller.toggle_application_mute(app_id)
            
            elif message_type == 'set_default_sink':
                sink_id = data.get('sink_id')
                
                if sink_id is not None:
                    success = self.controller.set_default_sink(sink_id)
                    
                    # If successful, the auto monitoring will detect changes and update clients
            
            elif message_type == 'move_app_to_sink':
                app_id = data.get('app_id')
                sink_id = data.get('sink_id')
                
                if app_id is not None and sink_id is not None:
                    success = self.controller.move_application_to_sink(app_id, sink_id)
                    
                    # If successful, the auto monitoring will detect changes and update clients
            
            elif message_type == 'set_card_profile':
                card_id = data.get('card_id')
                profile_name = data.get('profile_name')
                
                if card_id is not None and profile_name is not None:
                    success = self.controller.set_card_profile(card_id, profile_name)
                    
                    # If successful, the auto monitoring will detect changes and update clients
            
            elif message_type == 'refresh':
                # Force a refresh by clearing the change tracking
                self.controller._last_sink_data.clear()
                self.controller._last_app_data.clear()
                self.controller._last_card_data.clear()
                self.controller._last_sink_ids.clear()
                self.controller._last_app_ids.clear()
                self.controller._last_card_ids.clear()
            
            elif message_type == 'request_detailed_data':
                # Client requests detailed data for specific IDs
                sink_ids = data.get('sink_ids', [])
                app_ids = data.get('app_ids', [])
                card_ids = data.get('card_ids', [])
                
                detailed_data = self.controller.get_detailed_data_by_ids(
                    sink_ids=sink_ids,
                    app_ids=app_ids,
                    card_ids=card_ids
                )
                
                response = {
                    'type': 'detailed_data',
                    'data': detailed_data
                }
                
                await websocket.send(json.dumps(response))
        
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

async def websocket_server(host, port):
    """Start the WebSocket server"""
    logger.info(f"Starting WebSocket server on {host}:{port}")
    
    # Start auto monitoring task
    auto_monitoring_task = asyncio.create_task(ws_handler.start_auto_monitoring())
    
    async with websockets.serve(ws_handler.handle_client, host, port):
        await asyncio.Future()  # Run forever

def start_http_server(host, port):
    """Start the HTTP server for serving static files"""
    class CustomHTTPRequestHandler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            static_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static')
            super().__init__(*args, directory=static_dir, **kwargs)
        
        def end_headers(self):
            # Add CORS headers
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
            self.send_header('Access-Control-Allow-Headers', 'Content-Type')
            super().end_headers()
    
    httpd = HTTPServer((host, port), CustomHTTPRequestHandler)
    logger.info(f"Starting HTTP server on {host}:{port}")
    httpd.serve_forever()

def signal_handler(signum, frame):
    """Handle shutdown signals"""
    logger.info("Shutting down...")
    sys.exit(0)

async def main():
    """Main function to start both servers"""
    # Parse command line arguments
    args = parse_arguments()
    
    # Set up signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Start HTTP server in a separate thread
    http_thread = Thread(target=start_http_server, args=(args.host, args.port), daemon=True)
    http_thread.start()
    
    # Start WebSocket server
    await websocket_server(args.host, args.ws_port)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Server stopped by user")
    except Exception as e:
        logger.error(f"Server error: {e}")
        sys.exit(1)
