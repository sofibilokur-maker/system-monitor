
import os
from datetime import datetime
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import create_engine, text


load_dotenv()

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "12345")
DB_NAME = os.getenv("DB_NAME", "monitor_db")

DATABASE_URL = f"postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

engine = create_engine(DATABASE_URL)

app = FastAPI(title="Monitoring Server")


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)



class TelemetryIn(BaseModel):
    device_id: str
    timestamp: str
    cpu_usage: float
    ram_usage: float
    disk_usage: float
    network_upload_mb_s: Optional[float] = None
    network_download_mb_s: Optional[float] = None


@app.get("/")
def root():
    return {"status": "ok", "message": "Monitoring server is running"}


@app.post("/api/telemetry")
def receive_telemetry(data: TelemetryIn):
    try:
        with engine.begin() as conn:

            conn.execute(
                text(
                    """
                    INSERT INTO devices (device_id, hostname, registered_at)
                    VALUES (:device_id, :device_id, now())
                    ON CONFLICT (device_id) DO NOTHING
                    """
                ),
                {"device_id": data.device_id},
            )

            # Записуємо сам знімок телеметрії
            conn.execute(
                text(
                    """
                    INSERT INTO telemetry (
                        device_id, "timestamp", cpu_usage, ram_usage, disk_usage,
                        network_upload_mb_s, network_download_mb_s
                    ) VALUES (
                        :device_id, :timestamp, :cpu_usage, :ram_usage, :disk_usage,
                        :network_upload_mb_s, :network_download_mb_s
                    )
                    """
                ),
                data.model_dump(),
            )

        return {"status": "received", "device_id": data.device_id}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"DB error: {e}")


@app.get("/api/devices")
def list_devices():
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT device_id FROM devices ORDER BY device_id")
        ).fetchall()
    return {"devices": [r[0] for r in rows]}


collect_jobs = {}


@app.post("/api/devices/{device_id}/collect")
def request_collect(device_id: str, duration: int = 60, interval: int = 5):
    collect_jobs[device_id] = {"status": "pending", "duration": duration, "interval": interval}
    return collect_jobs[device_id]


@app.get("/api/devices/{device_id}/collect/status")
def collect_status(device_id: str):
    return collect_jobs.get(device_id, {"status": "idle"})


@app.get("/api/agent/{device_id}/poll")
def agent_poll(device_id: str):
    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO devices (device_id, hostname) VALUES (:d, :d) ON CONFLICT (device_id) DO NOTHING"),
            {"d": device_id},
        )
    job = collect_jobs.get(device_id)
    if job and job["status"] == "pending":
        job["status"] = "running"
        return {"collect": True, "duration": job["duration"], "interval": job["interval"]}
    return {"collect": False}


@app.post("/api/agent/{device_id}/done")
def agent_done(device_id: str):
    if device_id in collect_jobs:
        collect_jobs[device_id]["status"] = "done"
    return {"ok": True}


@app.get("/api/telemetry/{device_id}")
def get_last_telemetry(device_id: str, limit: int = 100):
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT "timestamp", cpu_usage, ram_usage, disk_usage,
                       network_upload_mb_s, network_download_mb_s
                FROM telemetry
                WHERE device_id = :device_id
                ORDER BY "timestamp" DESC
                LIMIT :limit
                """
            ),
            {"device_id": device_id, "limit": limit},
        ).mappings().all()

    return {"device_id": device_id, "records": [dict(r) for r in rows]}