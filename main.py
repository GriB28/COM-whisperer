import config
from whisperer import COMWhisperer


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

whisperer.start_listening()

print("\ncmds:")
print("\t<hex...> - send raw hex-coded bytes")
print("\texit     - exit\n")

try:
    while True:
        cmd_line = input(">>> ").strip()
        if not cmd_line:
            continue

        parts = cmd_line.split()
        cmd_name = parts[0].lower()

        if cmd_name in ("exit", "quit", "q"):
            break

        else:
            hex_str = "".join(parts[1:])
            try:
                raw_data = bytes.fromhex(hex_str)
                whisperer.send(raw_data)
            except ValueError:
                print("encoding error")

except KeyboardInterrupt:
    print("\ninterrupted by user")
finally:
    whisperer.disconnect()
    print("exiting...")
