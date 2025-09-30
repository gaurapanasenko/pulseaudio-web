#!/usr/bin/env python3
"""
Test script to verify pulsectl functionality
"""

import pulsectl
import sys

def test_pulsectl():
    try:
        print("Testing pulsectl connection...")
        pulse = pulsectl.Pulse('test-client')
        print("✓ Connected to PulseAudio")
        
        print("\nAvailable sinks:")
        sinks = pulse.sink_list()
        if not sinks:
            print("❌ No sinks found")
            return False
        
        for i, sink in enumerate(sinks):
            print(f"  {i}: {sink.name} (index: {sink.index})")
            print(f"     Description: {sink.description}")
            print(f"     Volume: {sink.volume}")
            print(f"     Muted: {sink.mute}")
            print()
        
        # Test volume operations on first sink
        if sinks:
            test_sink = sinks[0]
            print(f"Testing volume operations on: {test_sink.name}")
            
            # Get current volume
            current_volume = test_sink.volume
            print(f"Current volume: {current_volume}")
            
            # Calculate percentage using value_flat
            percentage = int(round(current_volume.value_flat * 100))
            print(f"Volume percentage: {percentage}%")
            
            # Test setting volume (save current volume first)
            original_volume = current_volume
            try:
                # Set to 50%
                volume_info = pulsectl.PulseVolumeInfo(0.5, len(test_sink.volume.values))
                pulse.volume_set(test_sink, volume_info)
                print("✓ Set volume to 50%")
                
                # Get new volume
                new_volume = test_sink.volume
                new_percentage = int(round(new_volume.value_flat * 100))
                print(f"New volume percentage: {new_percentage}%")
                
                # Restore original volume
                pulse.volume_set(test_sink, original_volume)
                print("✓ Restored original volume")
                
            except Exception as e:
                print(f"❌ Volume operation failed: {e}")
                return False
        
        pulse.close()
        print("\n✓ All tests passed!")
        return True
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        return False

if __name__ == "__main__":
    success = test_pulsectl()
    sys.exit(0 if success else 1)
