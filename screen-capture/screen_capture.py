#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Screen Capture Tool
Simple screenshot capture for dual monitors.
"""

import os
from datetime import datetime

# Get script directory
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(SCRIPT_DIR, "images")
os.makedirs(OUTPUT_DIR, exist_ok=True)

def capture_screen():
    """Capture screen using PIL"""
    try:
        from PIL import ImageGrab
    except ImportError:
        print("[ERR] PIL not installed, installing...")
        import subprocess
        subprocess.check_call([
            "pip", "install", "Pillow"
        ])
        from PIL import ImageGrab
    
    # Capture full screen
    screenshot = ImageGrab.grab()
    
    # Generate filename
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"screenshot_{timestamp}.png"
    filepath = os.path.join(OUTPUT_DIR, filename)
    
    # Save image
    screenshot.save(filepath)
    print(f"[OK] Screenshot saved to: {filepath}")
    print(f"[INFO] Resolution: {screenshot.size[0]}x{screenshot.size[1]}")
    
    # 打印 MEDIA: 行供 Hermes 网关抓取
    print(f"MEDIA:{filepath}")
    
    return filepath

if __name__ == "__main__":
    capture_screen()
