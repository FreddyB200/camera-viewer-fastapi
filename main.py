# file: main.py (CORRECTED STARTUP LOGIC)
import os
import subprocess
import logging
import time
import shutil
import threading
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from starlette.staticfiles import StaticFiles
from settings import settings

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

app = FastAPI()
ffmpeg_processes = {}
HLS_BASE_DIR = "hls"
STALE_THRESHOLD_SECONDS = 30

def check_ffmpeg():
    if not shutil.which("ffmpeg"):
        logging.error("CRITICAL: ffmpeg command not found.")
        raise RuntimeError("FFmpeg not found")
    logging.info("FFmpeg installation confirmed.")

def start_ffmpeg_process(cam_id: int):
    if cam_id in ffmpeg_processes and ffmpeg_processes[cam_id].poll() is None:
        logging.warning(f"Terminating existing process for Camera {cam_id} before restart.")
        ffmpeg_processes[cam_id].kill()
        ffmpeg_processes[cam_id].wait()

    cam_hls_dir = f"{HLS_BASE_DIR}/cam{cam_id}"
    # This directory is now created in startup_event to avoid race conditions
    # os.makedirs(cam_hls_dir, exist_ok=True) 

    rtsp_url = (
        f"rtsp://{settings.CAM_USER}:{settings.CAM_PASS}@"
        f"{settings.CAM_IP}:{settings.CAM_PORT}/cam/realmonitor?channel={cam_id}&subtype=1"
    )
    hls_playlist_path = f"{cam_hls_dir}/stream.m3u8"

    command = [
        'ffmpeg', '-rtsp_transport', 'tcp', '-timeout', '15000000', '-i', rtsp_url,
        '-c:v', 'copy', '-hls_time', '2', '-hls_list_size', '3', 
        '-hls_flags', 'delete_segments', '-start_number', '1', hls_playlist_path
    ]

    logging.info(f"Starting stream for Camera {cam_id}...")
    process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    ffmpeg_processes[cam_id] = process
    return process

def monitor_ffmpeg_processes():
    while True:
        time.sleep(15)
        # logging.info("Supervisor: Running health check...") # Too noisy
        for cam_id in range(1, settings.TOTAL_CAMERAS + 1):
            process = ffmpeg_processes.get(cam_id)
            playlist_path = f"{HLS_BASE_DIR}/cam{cam_id}/stream.m3u8"

            is_stale = False
            if os.path.exists(playlist_path):
                mtime = os.path.getmtime(playlist_path)
                if (time.time() - mtime) > STALE_THRESHOLD_SECONDS:
                    is_stale = True

            if (process and process.poll() is not None) or is_stale:
                if is_stale:
                    logging.warning(f"Supervisor: Stream for Camera {cam_id} is STALE. Restarting...")
                else:
                    logging.warning(f"Supervisor: FFmpeg process for Camera {cam_id} died. Restarting...")
                start_ffmpeg_process(cam_id)

@app.on_event("startup")
def startup_event():
    check_ffmpeg()

    # --- THE FIX IS HERE ---
    # 1. First, create ALL directories needed.
    if os.path.exists(HLS_BASE_DIR): shutil.rmtree(HLS_BASE_DIR)
    for i in range(1, settings.TOTAL_CAMERAS + 1): 
        os.makedirs(f"{HLS_BASE_DIR}/cam{i}", exist_ok=True)

    # 2. THEN, mount the parent directory. Now it is guaranteed to exist.
    app.mount("/hls", StaticFiles(directory=HLS_BASE_DIR), name="hls")
    logging.info(f"Mounted '{HLS_BASE_DIR}' directory.")

    # 3. NOW, start the processes that will write to these directories.
    for i in range(1, settings.TOTAL_CAMERAS + 1): 
        start_ffmpeg_process(i)

    # 4. Finally, start the monitor.
    monitor_thread = threading.Thread(target=monitor_ffmpeg_processes, daemon=True)
    monitor_thread.start()
    logging.info("Started background supervisor for FFmpeg processes.")

# --- Routes ---
@app.get("/", response_class=HTMLResponse)
async def get_frontend():
    with open("index.html") as f:
        return HTMLResponse(content=f.read(), status_code=200)

@app.get("/health", response_class=JSONResponse)
async def health_check():
    active_streams = [cid for cid, p in ffmpeg_processes.items() if p.poll() is None]
    return {"status": "ok", "total_streams": settings.TOTAL_CAMERAS, "active_streams": len(active_streams)}