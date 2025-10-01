#!/usr/bin/env python3
"""
Simple peak monitor - shows audio levels without interfering with playback
"""

import pulsectl
import time
import sys

def simple_peak_monitor():
    """Simple peak monitoring with minimal interference"""
    
    print("🎵 Simple Peak Monitor")
    print("=" * 40)
    print("Shows audio levels every 2 seconds")
    print("Press Ctrl+C to stop")
    print("=" * 40)
    
    try:
        # Connect to PulseAudio
        pulse = pulsectl.Pulse('simple-peak-monitor')
        print("✅ Connected to PulseAudio")
        
        while True:
            print(f"\n📊 Audio Levels - {time.strftime('%H:%M:%S')}")
            print("-" * 80)
            print("Sinks: Name | Peak% | State | Mute | Volume")
            print("-" * 80)
            
            # Get sinks
            sinks = pulse.sink_list()
            for sink in sinks:
                try:
                    # Get peak with minimal timeout
                    peak_value = pulse.get_peak_sample(sink.index, 0.01)
                    peak_percent = peak_value * 100
                    
                    # Get state information
                    state_str = str(sink.state).split('=')[-1] if '=' in str(sink.state) else str(sink.state)
                    mute_str = "MUTED" if sink.mute else "UNMUTED"
                    volume_str = f"{sink.volume.value_flat*100:.1f}%"
                    
                    # Show activity with state info
                    if peak_percent > 1:
                        print(f"🔊 {sink.description[:25]:<25} {peak_percent:5.1f}% | {state_str} | {mute_str} | {volume_str}")
                    else:
                        print(f"🔇 {sink.description[:25]:<25}  0.0% | {state_str} | {mute_str} | {volume_str}")
                        
                except Exception as e:
                    print(f"❌ {sink.description[:25]:<25} Error: {e}")
            
            # Get applications
            sink_inputs = pulse.sink_input_list()
            if sink_inputs:
                print("\n📱 Applications:")
                print("Name | Peak% | Mute | State | Volume | Sink")
                print("-" * 60)
                for app in sink_inputs:
                    try:
                        peak_value = pulse.get_peak_sample(app.index, 0.01)
                        peak_percent = peak_value * 100
                        
                        app_name = app.proplist.get('application.name', 'Unknown')[:20]
                        mute_str = "MUTED" if app.mute else "UNMUTED"
                        volume_str = f"{app.volume.value_flat*100:.1f}%"
                        sink_id = app.sink
                        corked_str = "CORKED" if app.corked else "ACTIVE"
                        
                        if peak_percent > 1:
                            print(f"🎵 {app_name:<20} {peak_percent:5.1f}% | {mute_str} | {corked_str} | {volume_str} | Sink:{sink_id}")
                        else:
                            print(f"🔇 {app_name:<20}  0.0% | {mute_str} | {corked_str} | {volume_str} | Sink:{sink_id}")
                            
                    except Exception as e:
                        app_name = app.proplist.get('application.name', 'Unknown')[:20]
                        print(f"❌ {app_name:<20} Error: {e}")
            
            # Wait 2 seconds before next update
            time.sleep(2)
            
    except KeyboardInterrupt:
        print("\n⏹️ Monitoring stopped")
    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        try:
            pulse.close()
        except:
            pass

if __name__ == "__main__":
    simple_peak_monitor()
