from enum import IntEnum
import struct
from typing import Optional, List, Dict, Any, Tuple

from spidor_packet_builder import PacketBuilder, Packet


class Command(IntEnum):
    MOVE              = 0x01
    STOP              = 0x02
    SET_GAIT          = 0x03
    SET_POSE          = 0x04
    REQUEST_TELEMETRY = 0x05
    SET_LED           = 0x06
    HOME              = 0x07
    RELAX             = 0x08
    WAKE              = 0x09


class GaitType(IntEnum):
    WALK  = 0
    TROT  = 1
    CREEP = 2


GAIT_NAMES: Dict[str, GaitType] = {
    "walk": GaitType.WALK,
    "trot": GaitType.TROT,
    "creep": GaitType.CREEP,
}


def encode_move(direction: int = 1, speed: int = 200) -> bytes:
    return bytes([direction & 0xFF, speed & 0xFF])


def encode_gait(gait: GaitType | str = GaitType.WALK) -> bytes:
    if isinstance(gait, str):
        gait_val = GAIT_NAMES.get(gait.lower(), GaitType.WALK)
    else:
        gait_val = int(gait)
    return bytes([gait_val & 0xFF])


def encode_pose(angles: List[float] | Tuple[float, ...]) -> bytes:
    packed = bytearray()
    for i in range(12):
        val = int(angles[i] * 100) if i < len(angles) else 0
        packed.extend([(val >> 8) & 0xFF, val & 0xFF])
    return bytes(packed)


def encode_led(state: int = 1) -> bytes:
    return bytes([int(state) & 0xFF])


class SpidorPlugin:
    def __init__(self, builder: Optional[PacketBuilder] = None):
        self.builder = builder or PacketBuilder()

        self._commands_help: Dict[str, str] = {
            "move [dir] [speed]": "dir: 1/-1[1], speed: 0..255[200]; 0x01",
            "stop": "0x02",
            "gait <walk|trot|creep>": "0x03",
            "pose <a1 .. a12>": "0x04",
            "telem": "0x05",
            "led <0|1>": "0x06",
            "home": "0x07",
            "relax": "0x08",
            "wake": "0x09"
        }

        self._aliases: Dict[str, str] = {
            "wake": "wake",
            "relax": "relax",
            "home": "home",
            "stop": "stop",
            "move": "move",
            "gait": "gait",
            "set_gait": "gait",
            "pose": "pose",
            "set_pose": "pose",
            "telem": "telem",
            "telemetry": "telem",
            "led": "led",
            "set_led": "led",
        }


    def make_wake(self) -> Packet:
        return self.builder.build(Command.WAKE, b"")

    def make_relax(self) -> Packet:
        return self.builder.build(Command.RELAX, b"")

    def make_home(self) -> Packet:
        return self.builder.build(Command.HOME, b"")

    def make_stop(self) -> Packet:
        return self.builder.build(Command.STOP, b"")

    def make_move(self, direction: int = 1, speed: int = 200) -> Packet:
        return self.builder.build(Command.MOVE, encode_move(direction, speed))

    def make_gait(self, gait: GaitType | str = GaitType.WALK) -> Packet:
        return self.builder.build(Command.SET_GAIT, encode_gait(gait))

    def make_pose(self, angles: List[float]) -> Packet:
        return self.builder.build(Command.SET_POSE, encode_pose(angles))

    def make_telemetry_request(self) -> Packet:
        return self.builder.build(Command.REQUEST_TELEMETRY, b"")

    def make_led(self, state: int = 1) -> Packet:
        return self.builder.build(Command.SET_LED, encode_led(state))


    def is_command(self, cmd_name: str) -> bool:
        return cmd_name.lower() in self._aliases

    def execute(self, cmd_name: str, args: List[str]) -> Optional[Packet]:
        target = self._aliases.get(cmd_name.lower())
        if not target:
            return None

        try:
            if target == "wake":
                return self.make_wake()

            elif target == "relax":
                return self.make_relax()

            elif target == "home":
                return self.make_home()

            elif target == "stop":
                return self.make_stop()

            elif target == "move":
                direction = int(args[0]) if len(args) > 0 else 1
                speed = int(args[1]) if len(args) > 1 else 200
                return self.make_move(direction, speed)

            elif target == "gait":
                gait_arg = args[0] if len(args) > 0 else "walk"
                gait_val = GAIT_NAMES.get(gait_arg.lower(), GaitType.WALK)
                return self.make_gait(gait_val)

            elif target == "pose":
                if not args:
                    print("  [parsing error] appropriate format: pose <a1> <a2> ... <a12>")
                    return None
                angles = [float(a) for a in args]
                return self.make_pose(angles)

            elif target == "telem":
                return self.make_telemetry_request()

            elif target == "led":
                state = int(args[0]) if len(args) > 0 else 1
                return self.make_led(state)

        except ValueError as err:
            print(f"  [parsing error]: '{cmd_name}': {err}")
            return None

        return None

    def get_help(self) -> str:
        lines = ["\tSPIDOR plugin cmds:"]
        for cmd_pattern, desc in self._commands_help.items():
            lines.append(f"\t\t{cmd_pattern:<28} - {desc}")
        return "\n".join(lines)


    @staticmethod
    def parse_telemetry(payload: bytes) -> Optional[Dict[str, Any]]:
        """
          [0..11]   accel X, Y, Z (float32 little-endian)
          [12..23]  gyro X, Y, Z  (float32 little-endian)
          [24..25]  IR LF         (uint16 big-endian)
          [26]      Battery Raw   (uint8)
        """
        if len(payload) < 2:
            return None
        try:
            if len(payload) >= 27:
                accel_x, accel_y, accel_z = struct.unpack_from("<3f", payload, 0)
                gyro_x, gyro_y, gyro_z = struct.unpack_from("<3f", payload, 12)
                ir_lf = (payload[24] << 8) | payload[25]
                battery_high = payload[26]
                raw_adc = battery_high << 2
                voltage = round(raw_adc * (5.0 / 1024.0) * 2.0, 2)
                pct = max(0, min(100, int((voltage - 6.0) / 2.4 * 100)))

                return {
                    "battery_voltage": voltage,
                    "battery_percent": pct,
                    "ir_lf": ir_lf,
                    "accel": (round(accel_x, 2), round(accel_y, 2), round(accel_z, 2)),
                    "gyro": (round(gyro_x, 2), round(gyro_y, 2), round(gyro_z, 2)),
                }
            else:
                battery_mv = struct.unpack_from("<H", payload, 0)[0]
                voltage = round(battery_mv / 1000.0, 2)
                pct = max(0, min(100, int((voltage - 6.0) / 2.4 * 100)))
                return {
                    "battery_voltage": voltage,
                    "battery_percent": pct,
                    "ir_lf": 0,
                    "accel": (0.0, 0.0, 0.0),
                    "gyro": (0.0, 0.0, 0.0),
                }
        except struct.error:
            return None

    def handle_rx(self, packet: Packet) -> Optional[str]:
        if packet.command_id == Command.REQUEST_TELEMETRY:
            telem = self.parse_telemetry(packet.payload)
            if telem:
                return (
                    f"[TELEMETRY] Battery: {telem['battery_voltage']}V ({telem['battery_percent']}%) | "
                    f"IMU Acceleration: {telem['accel']}, Gyro: {telem['gyro']} | "
                    f"IR LF: {telem['ir_lf']}"
                )
        return None
