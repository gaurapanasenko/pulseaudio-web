# PulseAudio Web Control

A simple web application to control PulseAudio volume levels through a modern web interface, similar to pavucontrol but accessible via browser.

## Features

- 🎵 Real-time volume control for all PulseAudio sinks
- 🔇 Mute/unmute functionality
- 📱 Responsive design that works on desktop and mobile
- 🔄 Auto-reconnection and live updates via WebSocket
- 🎨 Modern, clean interface
- ⚡ Fast and lightweight

## Requirements

- Python 3.7+
- PulseAudio
- Modern web browser with WebSocket support

## Installation

1. Clone or download this repository
2. Install Python dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## Usage

1. Start the server:
   ```bash
   python server.py
   ```

2. Open your web browser and navigate to:
   ```
   http://localhost:8080
   ```

3. Control your audio devices:
   - Use the volume sliders to adjust volume levels
   - Click the mute/unmute buttons to toggle audio
   - Use the refresh button to reload device list

## How it Works

- **Backend**: Python server using asyncio and websockets library
- **Frontend**: Single HTML page with vanilla JavaScript
- **Communication**: WebSocket connection for real-time updates
- **Audio Control**: Uses `pulsectl` Python library to interface with PulseAudio

## Server Details

- HTTP Server: `localhost:8080` (serves the web interface)
- WebSocket Server: `localhost:8765` (handles real-time communication)

## Troubleshooting

### No audio devices found
- Make sure PulseAudio is running
- Check that you have permission to access PulseAudio
- Try running `python -c "import pulsectl; p = pulsectl.Pulse(); print([s.name for s in p.sink_list()])"` to verify

### Connection issues
- Ensure no firewall is blocking ports 8080 and 8765
- Check that the server is running without errors
- Try refreshing the browser page

### Volume changes not working
- Verify you have permission to control PulseAudio
- Check if your user is in the `audio` group
- Try running the server with appropriate permissions

## License

This project is licensed under the MIT License - see the LICENSE file for details.
