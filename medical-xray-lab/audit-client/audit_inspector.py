"""
Medical Device Protocol Auditing & Diagnostic Utility
Used by students in the `protocol-audit-client` container to inspect Modbus TCP
register telemetry, decode active X-ray study references, and verify security hardening controls.
"""

import argparse
import json
import urllib.request
from pymodbus.client import ModbusTcpClient


def decode_ascii_registers(registers: list[int]) -> str:
    chars = []
    for reg in registers:
        high = (reg >> 8) & 0xFF
        low = reg & 0xFF
        if high:
            chars.append(chr(high))
        if low:
            chars.append(chr(low))
    return "".join(chars).strip("\x00")


def inspect_plc(host: str, port: int) -> dict:
    client = ModbusTcpClient(host=host, port=port, timeout=5)
    if not client.connect():
        raise RuntimeError(f"Could not connect to Modbus TCP controller at {host}:{port}")

    try:
        coils_res = client.read_coils(address=0, count=2)
        hr_res = client.read_holding_registers(address=0, count=21)

        if coils_res.isError() or hr_res.isError():
            raise RuntimeError("Modbus read returned an error response.")

        coils = coils_res.bits[:2]
        regs = hr_res.registers
        staged_image_path = decode_ascii_registers(regs[5:21])

        report = {
            "controller_endpoint": f"{host}:{port}",
            "coils": {
                "coil_0_door_interlock": bool(coils[0]),
                "coil_1_exposure_trigger": bool(coils[1]),
            },
            "holding_registers": {
                "hr_0_device_status": regs[0],
                "hr_1_tube_kvp": regs[1],
                "hr_2_tube_mas": regs[2],
                "hr_3_selected_study_index": regs[3],
                "hr_4_last_http_sync_code": regs[4],
                "hr_5_20_staged_image_path": staged_image_path,
            },
        }
        return report
    finally:
        client.close()


def check_image_server_status(server_url: str) -> dict:
    req = urllib.request.Request(f"{server_url}/api/status", headers={"User-Agent": "MedAuditInspector/1.0"})
    with urllib.request.urlopen(req, timeout=5) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser(description="Medical X-Ray Modbus/OpenPLC Protocol Diagnostic Inspector")
    parser.add_argument("--plc-host", default="xray-modbus-controller", help="Modbus TCP Controller hostname")
    parser.add_argument("--plc-port", type=int, default=5020, help="Modbus TCP Controller port")
    parser.add_argument("--server-url", default="http://medical-image-server:8080", help="Medical Image Server URL")
    args = parser.parse_args()

    print("=== [1] Modbus TCP / OpenPLC Register Telemetry Inspection ===")
    plc_report = inspect_plc(args.plc_host, args.plc_port)
    print(json.dumps(plc_report, indent=2))

    print("\n=== [2] Medical Image Server Telemetry & Security Mode ===")
    server_status = check_image_server_status(args.server_url)
    print(json.dumps(server_status.get("plc", {}), indent=2))
    print(f"Total Verified X-Ray Studies Loaded: {server_status.get('total_xrays', 0)}")


if __name__ == "__main__":
    main()
