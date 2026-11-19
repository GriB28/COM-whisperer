from dataclasses import dataclass


SERIAL_PORT: str | None = "COM10"
BAUD_RATE: int = 115200
TIMEOUT: float = 1.0
DTR_RESET_DELAY: float = 2.0
AUTO_RECONNECT: bool = True


@dataclass
class PacketStructureConfig:
    header: bytes = bytes([0xAA, 0x55])

    length_size: int = 1
    length_byteorder: str = "big"

    length_includes_cmd: bool = True
    max_payload_size: int = 64

    crc_enabled: bool = True
    crc_size: int = 1
    crc_polynomial: int = 0x07
    crc_init: int = 0x00
    crc_xor_out: int = 0x00

    crc_covers_length: bool = True
    crc_covers_cmd: bool = True
    crc_covers_payload: bool = True


PACKET_CONFIG = PacketStructureConfig()
