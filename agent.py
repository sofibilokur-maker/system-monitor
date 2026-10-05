import socket
import time
from datetime import datetime

import psutil
import requests


SERVER_URL = "http://127.0.0.1:8000"

DEVICE_ID = socket.gethostname()

POLL_INTERVAL = 2

MAX_SAMPLES = 10


POLL_URL = f"{SERVER_URL}/api/agent/{DEVICE_ID}/poll"

TELEMETRY_URL = f"{SERVER_URL}/api/telemetry"

DONE_URL = f"{SERVER_URL}/api/agent/{DEVICE_ID}/done"

_temp_warned = False

def get_temperature():
    global _temp_warned

    try:
        r = requests.get("http://localhost:8085/data.json", timeout=3)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        if not _temp_warned:
            print("[WARNING] LibreHardwareMonitor недоступний:", e)
            _temp_warned = True
        return None

    package = None
    others = []

    def walk(node, in_temp_group=False):
        nonlocal package

        text = node.get("Text", "")
        value = node.get("Value", "")

        is_temp_group = in_temp_group or text == "Temperatures"

        if is_temp_group and "°C" in value:
            try:
                num = float(value.replace("°C", "").replace(",", ".").strip())
                if "Package" in text or "Tctl" in text or "Tdie" in text:
                    package = num
                elif "CPU" in text or "Core" in text:
                    others.append(num)
            except ValueError:
                pass

        for child in node.get("Children", []):
            walk(child, is_temp_group)

    walk(data)

    if package is not None:
        return round(package, 2)
    if others:
        return round(max(others), 2)
    return None

def get_network():

    try:

        stats = psutil.net_io_counters()

        upload = (
            stats.bytes_sent
            / (1024 * 1024)
        )

        download = (
            stats.bytes_recv
            / (1024 * 1024)
        )

        return (
            round(upload, 2),
            round(download, 2)
        )


    except Exception as e:

        print(
            "[WARNING] Network error:",
            e
        )

        return 0, 0

def collect_data():

    print()
    print("[COLLECT] Reading system data...")



    cpu = psutil.cpu_percent(
        interval=1
    )



    ram = psutil.virtual_memory()



    disk = psutil.disk_usage("C:\\")



    temperature = get_temperature()


    if temperature is None:
        temperature = 0.0



    network_upload, network_download = (
        get_network()
    )


    data = {

        "device_id": DEVICE_ID,

        "timestamp":
            datetime.now().isoformat(),

        "cpu_usage":
            round(cpu, 2),

        "ram_usage":
            round(ram.percent, 2),

        "disk_usage":
            round(disk.percent, 2),

        "temperature":
            temperature,

        "network_upload_mb_s":
            network_upload,

        "network_download_mb_s":
            network_download
    }


    print()
    print("CPU:", data["cpu_usage"], "%")
    print("RAM:", data["ram_usage"], "%")
    print("Disk:", data["disk_usage"], "%")
    print(
        "Temperature:",
        data["temperature"],
        "°C"
    )
    print(
        "Network upload:",
        data["network_upload_mb_s"],
        "MB"
    )
    print(
        "Network download:",
        data["network_download_mb_s"],
        "MB"
    )


    return data


def send_telemetry(data):

    try:

        response = requests.post(
            TELEMETRY_URL,
            json=data,
            timeout=10
        )


        print(
            "[SEND] HTTP:",
            response.status_code
        )


        if response.status_code == 200:

            result = response.json()

            print(
                "[SEND] Server:",
                result
            )

            return True


        print(
            "[ERROR] Server:",
            response.text
        )

        return False


    except Exception as e:

        print(
            "[ERROR] Send telemetry:",
            e
        )

        return False




def send_done():

    try:

        response = requests.post(
            DONE_URL,
            timeout=10
        )


        print(
            "[DONE] Server response:",
            response.status_code
        )


    except Exception as e:

        print(
            "[ERROR] Done request:",
            e
        )




def main():

    print()
    print("=" * 60)
    print("SYSTEM MONITOR AGENT")
    print("=" * 60)

    print(
        "Device:",
        DEVICE_ID
    )

    print(
        "Server:",
        SERVER_URL
    )

    print(
        "Maximum samples:",
        MAX_SAMPLES
    )

    print("=" * 60)


    samples_sent = 0


    while True:



        if samples_sent >= MAX_SAMPLES:

            print()
            print("=" * 60)
            print("10 SAMPLES SENT")
            print("AGENT STOPPED")
            print("=" * 60)

            break



        try:

            response = requests.get(
                POLL_URL,
                timeout=10
            )


            if response.status_code != 200:

                print(
                    "[ERROR] Poll HTTP:",
                    response.status_code
                )

                time.sleep(
                    POLL_INTERVAL
                )

                continue


            command = response.json()


        except Exception as e:

            print(
                "[ERROR] Poll:",
                e
            )

            time.sleep(
                POLL_INTERVAL
            )

            continue



        if not command.get("collect", False):

            status = command.get(
                "status",
                "waiting"
            )


            if status == "done":

                print(
                    "[SERVER] Collection finished."
                )

                break


            print(
                "[SERVER] Waiting for collection..."
            )


            time.sleep(
                POLL_INTERVAL
            )

            continue




        print()
        print(
            f"Collecting sample "
            f"{samples_sent + 1}/{MAX_SAMPLES}"
        )


        data = collect_data()



        success = send_telemetry(
            data
        )


        if success:

            samples_sent += 1

            print(
                f"[SUCCESS] "
                f"Sample {samples_sent}/"
                f"{MAX_SAMPLES} saved."
            )


        else:

            print(
                "[ERROR] "
                "Sample was NOT saved."
            )




        if samples_sent >= MAX_SAMPLES:

            send_done()

            print()
            print("=" * 60)
            print("10 SAMPLES COLLECTED")
            print("AGENT STOPPED")
            print("=" * 60)

            break




        print(
            "Waiting 5 seconds..."
        )

        time.sleep(5)



if __name__ == "__main__":
    main()