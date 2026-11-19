import time
import threading
from typing import Optional, Callable, List, Union
import serial
import serial.tools.list_ports

import config
from spidor_packet_builder import PacketBuilder, Packet


class COMWhisperer:
    def __init__(
        self,
        port: Optional[str] = None,
        baudrate: Optional[int] = None,
        timeout: Optional[float] = None,
        packet_config: Optional[config.PacketStructureConfig] = None,
        auto_reset_delay: Optional[float] = None,
    ):
        self.port = port if port is not None else config.SERIAL_PORT
        self.baudrate = baudrate if baudrate is not None else config.BAUD_RATE
        self.timeout = timeout if timeout is not None else config.TIMEOUT
        self.auto_reset_delay = auto_reset_delay if auto_reset_delay is not None else config.DTR_RESET_DELAY

        self.builder = PacketBuilder(packet_config or config.PACKET_CONFIG)

        self._serial: Optional[serial.Serial] = None
        self._lock = threading.Lock()
        self._rx_buffer = bytearray()

        self._listener_thread: Optional[threading.Thread] = None
        self._listening = False
        self._on_packet_callback: Optional[Callable[[Packet], None]] = None

    @staticmethod
    def list_available_ports() -> List[serial.tools.list_ports_common.ListPortInfo]:
        return list(serial.tools.list_ports.comports())

    @classmethod
    def auto_detect_port(cls) -> Optional[str]:
        ports = cls.list_available_ports()
        for p in ports:
            desc = (p.description or "").lower()
            hwid = (p.hwid or "").lower()
            if any(k in desc or k in hwid for k in ["arduino", "ch340", "cp210", "ftdi", "usb-serial", "usb serial"]):
                return p.device
        if ports:
            return ports[0].device
        return None

    def connect(self, port: Optional[str] = None, baudrate: Optional[int] = None) -> bool:
        target_port = port or self.port
        target_baud = baudrate or self.baudrate
        if not target_port or target_port.lower() == "auto":
            detected = self.auto_detect_port()
            if detected:
                target_port = detected
            else:
                return False

        try:
            self._serial = serial.Serial(
                port=target_port,
                baudrate=target_baud,
                timeout=self.timeout,
                write_timeout=self.timeout
            )
            self.port = target_port
            self.baudrate = target_baud

            if self.auto_reset_delay > 0:
                time.sleep(self.auto_reset_delay)

            self._serial.reset_input_buffer()
            self._serial.reset_output_buffer()
            self._rx_buffer.clear()
            return True
        except serial.SerialException as ex:
            self._serial = None
            return False

    def disconnect(self) -> None:
        self.stop_listening()
        with self._lock:
            if self._serial and self._serial.is_open:
                try:
                    self._serial.close()
                except:
                    pass
            self._serial = None

    @property
    def is_connected(self) -> bool:
        return self._serial is not None and self._serial.is_open

    def send(self, data: Union[Packet, bytes]) -> bool:
        if not self.is_connected or self._serial is None:
            return False

        raw_bytes = bytes(data) if isinstance(data, Packet) else data
        with self._lock:
            try:
                self._serial.write(raw_bytes)
                self._serial.flush()
                return True
            except serial.SerialException:
                return False

    def read_packets(self, max_wait_sec: float = 0.5) -> List[Packet]:
        if not self.is_connected or self._serial is None:
            return []

        start_time = time.time()
        packets: List[Packet] = []

        while time.time() - start_time < max_wait_sec:
            with self._lock:
                available = self._serial.in_waiting
                if available > 0:
                    chunk = self._serial.read(available)
                    self._rx_buffer.extend(chunk)
                    new_packets, self._rx_buffer = self.builder.extract_packets_from_stream(self._rx_buffer)
                    packets.extend(new_packets)
                    if new_packets:
                        break
            time.sleep(0.01)

        return packets

    def start_listening(self, callback: Optional[Callable[[Packet], None]] = None) -> None:
        if self._listening:
            return

        self._on_packet_callback = callback
        self._listening = True
        self._listener_thread = threading.Thread(target=self._listener_loop, daemon=True, name="COM-Listener")
        self._listener_thread.start()

    def stop_listening(self) -> None:
        self._listening = False
        if self._listener_thread and self._listener_thread.is_alive():
            self._listener_thread.join(timeout=1.0)
        self._listener_thread = None

    def _listener_loop(self) -> None:
        while self._listening and self.is_connected:
            try:
                available = self._serial.in_waiting if self._serial else 0
                if available > 0:
                    with self._lock:
                        chunk = self._serial.read(available)
                    if chunk:
                        self._rx_buffer.extend(chunk)
                        packets, self._rx_buffer = self.builder.extract_packets_from_stream(self._rx_buffer)
                        for pkt in packets:
                            if self._on_packet_callback:
                                try:
                                    self._on_packet_callback(pkt)
                                except:
                                    pass
                time.sleep(0.01)
            except:
                break

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.disconnect()
