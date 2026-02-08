#!/usr/bin/env python3
"""
Zora - YouTube Music Downloader

Single entry point for the application.
Run with: python run.py
"""

from dotenv import load_dotenv
load_dotenv()

from app import create_app

app = create_app()

if __name__ == '__main__':
    print("""
    ╔═══════════════════════════════════════╗
    ║                                       ║
    ║     🎵  Z O R A  🎵                   ║
    ║     YouTube Music Downloader          ║
    ║                                       ║
    ╚═══════════════════════════════════════╝
    
    🌐 Open http://localhost:5001 in your browser
    📁 Downloads: ./downloads
    
    Press Ctrl+C to stop
    """)
    
    # Using port 5001 to avoid conflicts with macOS 'ControlCenter' (AirPlay Receiver)
    # Disable debug mode to prevent reloader hangs
    app.run(debug=False, port=5001, threaded=True)
