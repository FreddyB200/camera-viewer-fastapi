# file: main.py
import os
import subprocess
import logging
import time
import shutil
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
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

@app.on_event("startup")
def startup_event():
    """This code runs when the server starts."""
    check_ffmpeg()
    
    hls_base_dir = "hls"
    if os.path.exists(hls_base_dir):
        shutil.rmtree(hls_base_dir) # Clean up old streams on startup
    logging.info(f"Creating HLS directories for {settings.TOTAL_CAMERAS} cameras...")
    for i in range(1, settings.TOTAL_CAMERAS + 1):
        os.makedirs(f"{hls_base_dir}/cam{i}", exist_ok=True)

    logging.info("Starting FFmpeg processes...")
    for i in range(1, settings.TOTAL_CAMERAS + 1):
        rtsp_url = (
            f"rtsp://{settings.CAM_USER}:{settings.CAM_PASS}@"
            f"{settings.CAM_IP}:{settings.CAM_PORT}/cam/realmonitor?channel={i}&subtype=1"
        )
        hls_playlist_path = f"{hls_base_dir}/cam{i}/stream.m3u8"

        command = [
            'ffmpeg', '-rtsp_transport', 'tcp', '-i', rtsp_url, '-c:v', 'copy', 
            '-hls_time', '2', '-hls_list_size', '3', '-hls_flags', 'delete_segments',
            '-start_number', '1', hls_playlist_path
        ]
        
        process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        ffmpeg_processes.append((i, process))
    
    logging.info("Waiting 5 seconds to check initial stream status...")
    time.sleep(5)
    for cam_id, process in ffmpeg_processes:
        if process.poll() is not None: # If the process has terminated
            error_output = process.stderr.read().decode('utf-8')
            logging.error(f"FATAL: FFmpeg process for Camera {cam_id} failed on startup.")
            logging.error(f"-> Most likely cause: Incorrect IP, port, or credentials.")
            logging.error(f"-> FFmpeg error output: {error_output.strip()}")
        else:
            logging.info(f"Stream for Camera {cam_id} started successfully.")

app.mount("/hls", StaticFiles(directory="hls"), name="hls")

@app.get("/", response_class=HTMLResponse)
async def get_frontend():
    with open("index.html") as f:
        return HTMLResponse(content=f.read(), status_code=200)

@app.get("/health", response_class=JSONResponse)
async def health_check():
    return {"status": "ok"}