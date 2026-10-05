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

DATABASE_URL = (
    f"postgresql+psycopg2://"
    f"{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
)

engine = create_engine(DATABASE_URL)

app = FastAPI(title="Monitoring Server")



app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)




MAX_SAMPLES = 10




collect_jobs = {}




class TelemetryIn(BaseModel):
    device_id: str
    timestamp: str

    cpu_usage: float
    ram_usage: float
    disk_usage: float

    temperature: Optional[float] = 0

    network_upload_mb_s: Optional[float] = None
    network_download_mb_s: Optional[float] = None




@app.get("/")
def root():
    return {
        "status": "ok",
        "message": "Monitoring server is running"
    }




@app.get("/health")
def health():
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))

        return {
            "server": "ok",
            "database": "ok"
        }

    except Exception as e:
        return {
            "server": "ok",
            "database": "error",
            "message": str(e)
        }




@app.post("/api/telemetry")
def receive_telemetry(data: TelemetryIn):

    try:



        job = collect_jobs.get(data.device_id)

        if job is not None:

            if job["samples_received"] >= MAX_SAMPLES:

                return {
                    "status": "limit_reached",
                    "device_id": data.device_id,
                    "samples_received": job["samples_received"],
                    "max_samples": MAX_SAMPLES
                }




        with engine.begin() as conn:



            conn.execute(
                text(
                    """
                    INSERT INTO devices
                    (
                        device_id,
                        hostname,
                        registered_at
                    )
                    VALUES
                    (
                        :device_id,
                        :device_id,
                        now()
                    )
                    ON CONFLICT (device_id)
                    DO NOTHING
                    """
                ),
                {
                    "device_id": data.device_id
                }
            )



            conn.execute(
                text(
                    """
                    INSERT INTO telemetry
                    (
                        device_id,
                        "timestamp",
                        cpu_usage,
                        ram_usage,
                        disk_usage,
                        temperature,
                        network_upload_mb_s,
                        network_download_mb_s
                    )
                    VALUES
                    (
                        :device_id,
                        :timestamp,
                        :cpu_usage,
                        :ram_usage,
                        :disk_usage,
                        :temperature,
                        :network_upload_mb_s,
                        :network_download_mb_s
                    )
                    """
                ),
                data.model_dump()
            )




        if job is not None:

            job["samples_received"] += 1

            print(
                f"[DATA] {data.device_id}: "
                f"{job['samples_received']}/{MAX_SAMPLES}"
            )



            if job["samples_received"] >= MAX_SAMPLES:

                job["status"] = "done"

                print(
                    f"[DONE] Collection finished for "
                    f"{data.device_id}"
                )

            else:

                job["status"] = "running"


        return {
            "status": "received",
            "device_id": data.device_id,
            "samples_received": (
                job["samples_received"]
                if job is not None
                else None
            ),
            "max_samples": MAX_SAMPLES
        }


    except Exception as e:

        print("[ERROR] Telemetry:", e)

        raise HTTPException(
            status_code=500,
            detail=f"DB error: {e}"
        )




@app.get("/api/devices")
def list_devices():

    try:

        with engine.connect() as conn:

            rows = conn.execute(
                text(
                    """
                    SELECT device_id
                    FROM devices
                    ORDER BY device_id
                    """
                )
            ).fetchall()

        return {
            "devices": [row[0] for row in rows]
        }

    except Exception as e:

        raise HTTPException(
            status_code=500,
            detail=str(e)
        )




@app.post("/api/devices/{device_id}/collect")
def request_collect(
    device_id: str,
    duration: int = 60,
    interval: int = 5
):

    try:



        with engine.begin() as conn:

            conn.execute(
                text(
                    """
                    DELETE FROM telemetry
                    WHERE device_id = :device_id
                    """
                ),
                {
                    "device_id": device_id
                }
            )


        print()
        print("=" * 60)
        print("OLD TELEMETRY CLEARED")
        print("=" * 60)
        print("Device:", device_id)
        print("=" * 60)




        collect_jobs[device_id] = {

            "status": "pending",

            "duration": duration,

            "interval": interval,

            "samples_received": 0,

            "max_samples": MAX_SAMPLES,

            "started_at": datetime.now().isoformat()
        }


        print()
        print("=" * 60)
        print("NEW COLLECTION")
        print("=" * 60)
        print("Device:", device_id)
        print("Duration:", duration)
        print("Interval:", interval)
        print("Maximum samples:", MAX_SAMPLES)
        print("=" * 60)


        return {
            "status": "started",
            "device_id": device_id,
            "duration": duration,
            "interval": interval,
            "max_samples": MAX_SAMPLES
        }


    except Exception as e:

        print("[ERROR] Start collection:", e)

        raise HTTPException(
            status_code=500,
            detail=f"Collection error: {e}"
        )




@app.get("/api/devices/{device_id}/collect/status")
def collect_status(device_id: str):

    job = collect_jobs.get(device_id)

    if job is None:

        return {
            "status": "idle",
            "device_id": device_id,
            "samples_received": 0,
            "max_samples": MAX_SAMPLES
        }


    return {
        "status": job["status"],
        "device_id": device_id,
        "samples_received": job["samples_received"],
        "max_samples": job["max_samples"],
        "duration": job["duration"],
        "interval": job["interval"]
    }




@app.get("/api/agent/{device_id}/poll")
def agent_poll(device_id: str):



    with engine.begin() as conn:

        conn.execute(
            text(
                """
                INSERT INTO devices
                (
                    device_id,
                    hostname,
                    registered_at
                )
                VALUES
                (
                    :device_id,
                    :device_id,
                    now()
                )
                ON CONFLICT (device_id)
                DO NOTHING
                """
            ),
            {
                "device_id": device_id
            }
        )




    job = collect_jobs.get(device_id)


    if job is None:

        return {
            "collect": False,
            "status": "waiting"
        }




    if job["samples_received"] >= MAX_SAMPLES:

        job["status"] = "done"

        return {
            "collect": False,
            "status": "done",
            "samples_received": job["samples_received"],
            "max_samples": MAX_SAMPLES
        }




    if job["status"] == "pending":

        job["status"] = "running"



    if job["status"] == "running":

        return {
            "collect": True,
            "status": "running",
            "duration": job["duration"],
            "interval": job["interval"],
            "samples_received": job["samples_received"],
            "max_samples": MAX_SAMPLES
        }


    return {
        "collect": False,
        "status": job["status"]
    }




@app.post("/api/agent/{device_id}/done")
def agent_done(device_id: str):

    if device_id in collect_jobs:

        collect_jobs[device_id]["status"] = "done"

        print(
            f"[DONE] Agent {device_id} "
            f"finished collection"
        )


    return {
        "ok": True,
        "status": "done"
    }




@app.get("/api/telemetry/{device_id}")
def get_last_telemetry(
    device_id: str,
    limit: int = 100
):

    try:

        with engine.connect() as conn:

            rows = conn.execute(
                text(
                    """
                    SELECT
                        "timestamp",
                        cpu_usage,
                        ram_usage,
                        disk_usage,
                        temperature,
                        network_upload_mb_s,
                        network_download_mb_s

                    FROM telemetry

                    WHERE device_id = :device_id

                    ORDER BY "timestamp" DESC

                    LIMIT :limit
                    """
                ),
                {
                    "device_id": device_id,
                    "limit": limit
                }
            ).mappings().all()


        return {
            "device_id": device_id,
            "records": [dict(row) for row in rows]
        }


    except Exception as e:

        print("[ERROR] Get telemetry:", e)

        raise HTTPException(
            status_code=500,
            detail=str(e)
        )



ALERT_THRESHOLDS = {

    "cpu_warning": 80,
    "cpu_critical": 90,

    "ram_warning": 80,
    "ram_critical": 90,

    "disk_warning": 80,
    "disk_critical": 90,

    "temperature_warning": 70,
    "temperature_critical": 85
}


def generate_alerts(record):

    alerts = []




    if record["cpu_usage"] >= ALERT_THRESHOLDS["cpu_critical"]:

        alerts.append({
            "type": "critical",
            "metric": "CPU",
            "value": record["cpu_usage"],
            "message": (
                f"Критичне навантаження CPU: "
                f"{record['cpu_usage']}%"
            )
        })

    elif record["cpu_usage"] >= ALERT_THRESHOLDS["cpu_warning"]:

        alerts.append({
            "type": "warning",
            "metric": "CPU",
            "value": record["cpu_usage"],
            "message": (
                f"Високе навантаження CPU: "
                f"{record['cpu_usage']}%"
            )
        })




    if record["ram_usage"] >= ALERT_THRESHOLDS["ram_critical"]:

        alerts.append({
            "type": "critical",
            "metric": "RAM",
            "value": record["ram_usage"],
            "message": (
                f"Критичне використання RAM: "
                f"{record['ram_usage']}%"
            )
        })

    elif record["ram_usage"] >= ALERT_THRESHOLDS["ram_warning"]:

        alerts.append({
            "type": "warning",
            "metric": "RAM",
            "value": record["ram_usage"],
            "message": (
                f"Високе використання RAM: "
                f"{record['ram_usage']}%"
            )
        })




    if record["disk_usage"] >= ALERT_THRESHOLDS["disk_critical"]:

        alerts.append({
            "type": "critical",
            "metric": "Disk",
            "value": record["disk_usage"],
            "message": (
                f"Критичне використання диска: "
                f"{record['disk_usage']}%"
            )
        })

    elif record["disk_usage"] >= ALERT_THRESHOLDS["disk_warning"]:

        alerts.append({
            "type": "warning",
            "metric": "Disk",
            "value": record["disk_usage"],
            "message": (
                f"Високе використання диска: "
                f"{record['disk_usage']}%"
            )
        })




    if record["temperature"] >= ALERT_THRESHOLDS["temperature_critical"]:

        alerts.append({
            "type": "critical",
            "metric": "Temperature",
            "value": record["temperature"],
            "message": (
                f"Критична температура: "
                f"{record['temperature']}°C"
            )
        })

    elif record["temperature"] >= ALERT_THRESHOLDS["temperature_warning"]:

        alerts.append({
            "type": "warning",
            "metric": "Temperature",
            "value": record["temperature"],
            "message": (
                f"Висока температура: "
                f"{record['temperature']}°C"
            )
        })


    return alerts



@app.get("/api/alerts/{device_id}")
def get_alerts(device_id: str):

    try:

        with engine.connect() as conn:

            row = conn.execute(
                text(
                    """
                    SELECT
                        cpu_usage,
                        ram_usage,
                        disk_usage,
                        temperature

                    FROM telemetry

                    WHERE device_id = :device_id

                    ORDER BY "timestamp" DESC

                    LIMIT 1
                    """
                ),
                {
                    "device_id": device_id
                }
            ).mappings().first()


        if row is None:

            return {
                "device_id": device_id,
                "alerts": []
            }


        record = {

            "cpu_usage": float(row["cpu_usage"]),

            "ram_usage": float(row["ram_usage"]),

            "disk_usage": float(row["disk_usage"]),

            "temperature": float(
                row["temperature"] or 0
            )
        }


        return {
            "device_id": device_id,
            "alerts": generate_alerts(record)
        }


    except Exception as e:

        print("[ERROR] Alerts:", e)

        return {
            "device_id": device_id,
            "alerts": [],
            "error": str(e)
        }