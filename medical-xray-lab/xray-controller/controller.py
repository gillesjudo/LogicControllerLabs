"""
Medical X-Ray Device Controller (Modbus TCP / OpenPLC Register Layout)

Holding Registers (Function Codes 03 / 06 / 16):
  HR 0  (%QW0) : Device Status (0=IDLE, 1=READY, 2=EXPOSING, 3=TRANSFERRING, 4=INTERLOCK_OPEN)
  HR 1  (%QW1) : Tube Voltage in kVp (Default: 85, Safe Range: 40..150)
  HR 2  (%QW2) : Tube Current-Time in mAs (Default: 12, Safe Range: 1..200)
  HR 3  (%QW3) : Selected X-Ray Study Index on Image Server (0..N-1)
  HR 4  (%QW4) : Last Image Server HTTP Sync Code (e.g., 200, 401, 500)
  HR 5..20     : Active Study Image Path (ASCII-encoded, 2 chars per 16-bit register)

Coils (Function Codes 01 / 05):
  Coil 0 (%QX0.0): Radiation Room Door Interlock (1=CLOSED/SAFE, 0=OPEN)
  Coil 1 (%QX0.1): Exposure / Stage Study Trigger (1=Execute acquisition & sync with Image Server)
"""

import json
import logging
import os
import threading
import time
import urllib.request
from pymodbus.datastore import (
    ModbusSequentialDataBlock,
    ModbusServerContext,
    ModbusSlaveContext,
)
from pymodbus.server import StartTcpServer

logging.basicConfig(level=logging.INFO, format="%(asctime)s [XRAY-PLC] %(message)s")
log = logging.getLogger("xray-plc")

IMAGE_SERVER_URL = os.environ.get("IMAGE_SERVER_URL", "http://medical-image-server:8080")
MODBUS_PORT = int(os.environ.get("MODBUS_PORT", "5020"))
PLC_SHARED_TOKEN = os.environ.get("PLC_SHARED_TOKEN", "")
READ_ONLY_MODE = os.environ.get("PLC_READ_ONLY_LOCK", "false").lower() == "true"

STATUS_LABELS = {
    0: "IDLE",
    1: "READY",
    2: "EXPOSING",
    3: "TRANSFERRING",
    4: "INTERLOCK_OPEN",
}


def encode_ascii_registers(text: str, num_registers: int = 16) -> list[int]:
    """Packs an ASCII string (up to num_registers * 2 chars) into 16-bit Modbus registers."""
    padded = text[: num_registers * 2].ljust(num_registers * 2, "\x00")
    regs = []
    for i in range(0, len(padded), 2):
        high = ord(padded[i])
        low = ord(padded[i + 1])
        regs.append((high << 8) | low)
    return regs


def sync_with_image_server(payload: dict) -> tuple[int, dict]:
    url = f"{IMAGE_SERVER_URL}/api/plc-sync"
    data = json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if PLC_SHARED_TOKEN:
        headers["X-PLC-Token"] = PLC_SHARED_TOKEN

    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            return resp.status, body
    except urllib.error.HTTPError as err:
        return err.code, {}
    except Exception as exc:
        log.warning("Image server sync error: %s", exc)
        return 503, {}


def plc_control_loop(context: ModbusServerContext) -> None:
    slave_id = 0x00
    # Initialize default safe state
    store = context[slave_id]
    store.setValues(3, 0, [1, 85, 12, 0, 200])  # HR 0..4
    store.setValues(1, 0, [1, 0])  # Coil 0=1 (Door Closed), Coil 1=0 (No Trigger)

    while True:
        try:
            coils = store.getValues(1, 0, count=2)
            hrs = store.getValues(3, 0, count=5)

            door_closed = bool(coils[0])
            exposure_trigger = bool(coils[1])

            kvp = max(40, min(150, int(hrs[1])))
            mas = max(1, min(200, int(hrs[2])))
            study_index = max(0, int(hrs[3]))

            if READ_ONLY_MODE:
                # Defensive hardening: reset unauthorized register mutations back to baseline
                kvp, mas, study_index, exposure_trigger = 85, 12, 0, False
                store.setValues(3, 1, [kvp, mas, study_index])
                store.setValues(1, 1, [0])

            if not door_closed:
                status_code = 4  # INTERLOCK_OPEN
                exposure_trigger = False
                store.setValues(1, 1, [0])
            elif exposure_trigger:
                status_code = 3  # TRANSFERRING / STAGING
            else:
                status_code = 1  # READY

            payload = {
                "status_code": status_code,
                "status_label": STATUS_LABELS.get(status_code, "READY"),
                "kvp": kvp,
                "mas": mas,
                "door_interlock_closed": door_closed,
                "exposure_triggered": exposure_trigger,
                "selected_study_index": study_index,
            }

            http_code, resp_body = sync_with_image_server(payload)
            store.setValues(3, 0, [status_code, kvp, mas, study_index, http_code])

            image_path = resp_body.get("image_path", "/images/XR-HUMYN-001.png")
            ascii_regs = encode_ascii_registers(image_path, num_registers=16)
            store.setValues(3, 5, ascii_regs)

            # Auto-reset momentary exposure trigger coil after staging completes
            if exposure_trigger:
                log.info(
                    "Staged study index=%d (%s) at %d kVp, %d mAs -> HTTP %d",
                    study_index,
                    image_path,
                    kvp,
                    mas,
                    http_code,
                )
                store.setValues(1, 1, [0])
                store.setValues(3, 0, [1])

        except Exception as exc:
            log.error("PLC loop exception: %s", exc)

        time.sleep(1.5)


def main() -> None:
    store = ModbusSlaveContext(
        di=ModbusSequentialDataBlock(0, [0] * 32),
        co=ModbusSequentialDataBlock(0, [0] * 32),
        hr=ModbusSequentialDataBlock(0, [0] * 64),
        ir=ModbusSequentialDataBlock(0, [0] * 32),
    )
    context = ModbusServerContext(slaves=store, single=True)

    worker = threading.Thread(target=plc_control_loop, args=(context,), daemon=True)
    worker.start()

    log.info("Starting Medical X-Ray Modbus/OpenPLC Controller on 0.0.0.0:%d", MODBUS_PORT)
    StartTcpServer(context=context, address=("0.0.0.0", MODBUS_PORT))


if __name__ == "__main__":
    main()
