import config
from whisperer import COMWhisperer
from spidor_plugin import SpidorPlugin


print("available COM ports:")
ports = COMWhisperer.list_available_ports()
if not ports:
    print("  [WARNING] no active COM ports")
else:
    for idx, p in enumerate(ports, start=1):
        print(f"  {idx}. {p.device} — {p.description}")

target_port = config.SERIAL_PORT
print(f"\ndefault values from config: {target_port} @ {config.BAUD_RATE}")

whisperer = COMWhisperer()
connected = whisperer.connect()

if not connected:
    print("\nunable to open this port")
    exit(1)

spidor_plugin = SpidorPlugin(whisperer.builder)


def on_packet_received(pkt):
    telem_str = spidor_plugin.handle_rx(pkt)
    if telem_str:
        print(f"\n{telem_str}\n>>> ", end="", flush=True)
    else:
        print(f"\n[RX] {pkt.to_hex()} (cmd: 0x{pkt.command_id:02X})\n>>> ", end="", flush=True)


whisperer.start_listening(on_packet_received)

print("\ncmds:")
print(spidor_plugin.get_help())
print("\t<hex...>                     - send raw hex-coded bytes")
print("\thelp                         - show this help")
print("\texit                         - exit\n")

try:
    while True:
        cmd_line = input(">>> ").strip()
        if not cmd_line:
            continue

        parts = cmd_line.split()
        cmd_name = parts[0].lower()
        args = parts[1:]

        if cmd_name in ("exit", "quit", "q"):
            break

        if cmd_name == "help":
            print(spidor_plugin.get_help())
            print("\t  <hex...>                     - send raw hex-coded bytes")
            print("\t  help                         - show this help")
            print("\t  exit                         - exit\n")
            continue

        # 1. Вызов команды плагина по имени
        if spidor_plugin.is_command(cmd_name):
            pkt = spidor_plugin.execute(cmd_name, args)
            if pkt is not None:
                success = whisperer.send(pkt)
                status = "OK" if success else "FAIL"
                print(f"  [TX {status}] {pkt.to_hex()} ({cmd_name})")
            continue

        # 2. Отправка сырых hex-байт (например: raw AA 55 ... или сразу AA 55 ...)
        if cmd_name == "raw":
            hex_str = "".join(args)
        else:
            hex_str = "".join(parts)

        try:
            raw_data = bytes.fromhex(hex_str)
            success = whisperer.send(raw_data)
            status = "OK" if success else "FAIL"
            print(f"  [TX {status}] {raw_data.hex(' ').upper()}")
        except ValueError:
            print(f"  unknown command '{cmd_name}'. type 'help' for available commands")

except KeyboardInterrupt:
    print("\ninterrupted by user")
finally:
    whisperer.disconnect()
    print("exiting...")
