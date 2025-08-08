import os
import subprocess
import logging
import time
import shutil
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from settings import settings

# --- Setup professional logging ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- A function to check if FFmpeg is installed ---
def check_ffmpeg():
    if not shutil.which("ffmpeg"):
        logging.error("CRITICAL: ffmpeg command not found. Please ensure FFmpeg is installed in the Docker container.")
        raise RuntimeError("FFmpeg not found")
    logging.info("FFmpeg installation confirmed.")

# --- Main Application Setup ---
app = FastAPI()
ffmpeg_processes = []
HLS_BASE_DIR = "hls"

@app.on_event("startup")
def startup_event():
    """This code runs when the server starts."""
    check_ffmpeg()
    
    if os.path.exists(HLS_BASE_DIR):
        shutil.rmtree(HLS_BASE_DIR)
    logging.info(f"Creating HLS directories for {settings.TOTAL_CAMERAS} cameras...")
    for i in range(1, settings.TOTAL_CAMERAS + 1):
        os.makedirs(f"{HLS_BASE_DIR}/cam{i}", exist_ok=True)

    logging.info("Starting FFmpeg processes...")
    for i in range(1, settings.TOTAL_CAMERAS + 1):
        rtsp_url = (
            f"rtsp://{settings.CAM_USER}:{settings.CAM_PASS}@"
            f"{settings.CAM_IP}:{settings.CAM_PORT}/cam/realmonitor?channel={i}&subtype=1"
        )
        hls_playlist_path = f"{HLS_BASE_DIR}/cam{i}/stream.m3u8"
        command = [
            'ffmpeg', '-rtsp_transport', 'tcp', '-i', rtsp_url, '-c:v', 'copy', 
            '-hls_time', '2', '-hls_list_size', '3', '-hls_flags', 'delete_segments',
            '-start_number', '1', hls_playlist_path
        ]
        process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        ffmpeg_processes.append((i, process))
    
    logging.info("Waiting 5 seconds to check initial stream status...")
    time.sleep(5)
    # (Checking logic remains the same as before)

# --- THE FIX IS HERE: A custom route to serve HLS files with no-cache headers ---
@app.get("/hls/{cam_id}/{filename}")
async def get_hls_file(cam_id: str, filename: str):
    file_path = os.path.join(HLS_BASE_DIR, cam_id, filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")

    # For playlist files, add headers to prevent caching.
    if filename.endswith(".m3u8"):
        headers = {
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
        }
        return FileResponse(file_path, headers=headers)
    
    # For video segment files (.ts), let the browser cache them normally.
    return FileResponse(file_path)

# Serve the main HTML file
@app.get("/", response_class=HTMLResponse)
async def get_frontend():
    with open("index.html") as f:
        return HTMLResponse(content=f.read(), status_code=200)

# Add a health check endpoint
@app.get("/health", response_class=JSONResponse)
async def health_check():
    return {"status": "ok"}