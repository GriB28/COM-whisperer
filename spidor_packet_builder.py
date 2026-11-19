from typing import Optional, Tuple, List, Any
from config import PACKET_CONFIG, PacketStructureConfig


class Packet:
    def __init__(
        self,
        header: bytes,
        length: int,
        command_id: int,
        payload: bytes,
        crc: Optional[int],
        raw: bytes
    ):
        self.header = header
        self.length = length
        self.command_id = command_id
        self.payload = payload
        self.crc = crc
        self.raw = raw

    @property
    def command_name(self) -> str:
        return f"0x{self.command_id:02X}"

    def to_hex(self, separator: str = " ") -> str:
        return self.raw.hex(separator).upper()

    def __repr__(self) -> str:
        crc_str = f"0x{self.crc:02X}" if self.crc is not None else "None"
        return (
            f"<Packet cmd={self.command_name}(0x{self.command_id:02X}) "
            f"len={self.length} payload={len(self.payload)}B crc={crc_str} "
            f"hex='{self.to_hex()}'>"
        )

    def __bytes__(self) -> bytes:
        return self.raw

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, Packet):
            return False
        return self.raw == other.raw


class PacketBuilder:
    def __init__(self, cfg: Optional[PacketStructureConfig] = None):
        self.cfg = cfg or PACKET_CONFIG

    @staticmethod
    def _crc8(data: bytes | bytearray, poly: int = 0x07, init: int = 0x00, xor_out: int = 0x00) -> int:
        crc = init & 0xFF
        for byte in data:
            crc ^= byte
            for _ in range(8):
                if crc & 0x80:
                    crc = ((crc << 1) ^ poly) & 0xFF
                else:
                    crc = (crc << 1) & 0xFF
        return (crc ^ xor_out) & 0xFF

    def build(self, command: int, payload: bytes = b"") -> Packet:
        cmd_id = int(command)

        if len(payload) > self.cfg.max_payload_size:
            raise ValueError(
                f"payload length ({len(payload)}B) is above the limit: {self.cfg.max_payload_size}B"
            )

        payload_len = len(payload)
        length_val = (payload_len + 1) if self.cfg.length_includes_cmd else payload_len

        length_bytes = length_val.to_bytes(self.cfg.length_size, byteorder=self.cfg.length_byteorder)
        cmd_bytes = bytes([cmd_id & 0xFF])

        crc_data = bytearray()
        if self.cfg.crc_covers_length:
            crc_data.extend(length_bytes)
        if self.cfg.crc_covers_cmd:
            crc_data.extend(cmd_bytes)
        if self.cfg.crc_covers_payload:
            crc_data.extend(payload)

        crc_val: Optional[int] = None
        crc_bytes = b""
        if self.cfg.crc_enabled:
            crc_val = self._crc8(
                crc_data,
                poly=self.cfg.crc_polynomial,
                init=self.cfg.crc_init,
                xor_out=self.cfg.crc_xor_out
            )
            crc_bytes = bytes([crc_val])

        raw_packet = self.cfg.header + length_bytes + cmd_bytes + payload + crc_bytes

        return Packet(
            header=self.cfg.header,
            length=length_val,
            command_id=cmd_id,
            payload=payload,
            crc=crc_val,
            raw=bytes(raw_packet)
        )

    def parse_packet(self, raw: bytes) -> Packet:
        hdr_len = len(self.cfg.header)
        if len(raw) < hdr_len + self.cfg.length_size + 1 + (self.cfg.crc_size if self.cfg.crc_enabled else 0):
            raise ValueError(f"the packat is too short({len(raw)}B)")

        if raw[:hdr_len] != self.cfg.header:
            raise ValueError(f"header mismatch: awaited {self.cfg.header.hex()}, given {raw[:hdr_len].hex()}")

        idx = hdr_len
        length_val = int.from_bytes(raw[idx:idx + self.cfg.length_size], byteorder=self.cfg.length_byteorder)
        length_bytes = raw[idx:idx + self.cfg.length_size]
        idx += self.cfg.length_size

        cmd_id = raw[idx]
        cmd_bytes = raw[idx:idx + 1]
        idx += 1

        payload_len = (length_val - 1) if self.cfg.length_includes_cmd else length_val
        if payload_len < 0:
            raise ValueError(f"incorrect payload length: {payload_len}")

        payload = raw[idx:idx + payload_len]
        idx += payload_len

        crc_val: Optional[int] = None
        if self.cfg.crc_enabled:
            if idx >= len(raw):
                raise ValueError("CRC not found")
            crc_val = raw[idx]
            idx += 1

            crc_data = bytearray()
            if self.cfg.crc_covers_length:
                crc_data.extend(length_bytes)
            if self.cfg.crc_covers_cmd:
                crc_data.extend(cmd_bytes)
            if self.cfg.crc_covers_payload:
                crc_data.extend(payload)

            expected_crc = self._crc8(crc_data, self.cfg.crc_polynomial, self.cfg.crc_init, self.cfg.crc_xor_out)
            if crc_val != expected_crc:
                raise ValueError(f"CRC mismatch: awaited 0x{expected_crc:02X}, given 0x{crc_val:02X}")

        return Packet(
            header=self.cfg.header,
            length=length_val,
            command_id=cmd_id,
            payload=payload,
            crc=crc_val,
            raw=raw[:idx]
        )

    def extract_packets_from_stream(self, buffer: bytearray) -> Tuple[List[Packet], bytearray]:
        packets: List[Packet] = []
        hdr = self.cfg.header
        hdr_len = len(hdr)
        crc_len = self.cfg.crc_size if self.cfg.crc_enabled else 0

        while True:
            start_pos = buffer.find(hdr)
            if start_pos == -1:
                buffer = buffer[-(hdr_len - 1):] if hdr_len > 1 else bytearray()
                break

            if start_pos > 0:
                del buffer[:start_pos]

            min_needed = hdr_len + self.cfg.length_size + 1 + crc_len
            if len(buffer) < min_needed:
                break

            len_start = hdr_len
            len_end = len_start + self.cfg.length_size
            length_val = int.from_bytes(buffer[len_start:len_end], byteorder=self.cfg.length_byteorder)
            payload_len = (length_val - 1) if self.cfg.length_includes_cmd else length_val

            if payload_len < 0 or payload_len > self.cfg.max_payload_size:
                del buffer[:1]
                continue

            total_packet_size = hdr_len + self.cfg.length_size + 1 + payload_len + crc_len
            if len(buffer) < total_packet_size:
                break

            packet_raw = bytes(buffer[:total_packet_size])
            try:
                pkt = self.parse_packet(packet_raw)
                packets.append(pkt)
                del buffer[:total_packet_size]
            except ValueError:
                del buffer[:1]

        return packets, buffer
