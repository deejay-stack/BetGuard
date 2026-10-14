"""BetGuard bounded LAN test: redirect IPv4 UDP DNS for ICS Wi-Fi clients.

Run from an Administrator PowerShell terminal with PyDivert installed.
Requires ICS on 192.168.137.1:53 and BetGuard DNS on 192.168.137.1:5300.

TEST ONLY: Automatically stops after 180 seconds. When the redirector is
not running, ICS serves unfiltered DNS again. TCP, IPv6, DoH, VPN are not
covered. Do not rely on this for unattended or comprehensive protection.
"""

import threading
import pydivert

GATEWAY_IP = "192.168.137.1"
FIRST_CLIENT_IP = "192.168.137.3"  # Exclude the gateway (.1) and router (.2).
LAST_CLIENT_IP = "192.168.137.254"
ICS_PORT = 53
BETGUARD_PORT = 5300
TEST_SECONDS = 180

# Capture only DNS queries addressed to the Windows ICS gateway and replies
# from the BetGuard test port back to the Wi-Fi clients.
FILTER = (
    f"((inbound and ip and udp and "
    f"ip.SrcAddr >= {FIRST_CLIENT_IP} and "
    f"ip.SrcAddr <= {LAST_CLIENT_IP} and "
    f"ip.DstAddr == {GATEWAY_IP} and udp.DstPort == {ICS_PORT}) "
    f"or (outbound and ip and udp and "
    f"ip.SrcAddr == {GATEWAY_IP} and "
    f"ip.DstAddr >= {FIRST_CLIENT_IP} and "
    f"ip.DstAddr <= {LAST_CLIENT_IP} and "
    f"udp.SrcPort == {BETGUARD_PORT}))"
)


def main():
    print("BetGuard LAN DNS redirector — THREE-MINUTE TEST", flush=True)
    print(f"Clients: {FIRST_CLIENT_IP} to {LAST_CLIENT_IP}", flush=True)
    print(f"Intercept queries to {GATEWAY_IP}:{ICS_PORT}", flush=True)
    print(f"Send them to BetGuard at {GATEWAY_IP}:{BETGUARD_PORT}", flush=True)
    print("Only IPv4 UDP DNS is included. Normal browsing may briefly be affected.", flush=True)
    print("Automatic exit after 180 seconds.\n", flush=True)

    divert = pydivert.WinDivert(FILTER)
    timed_out = threading.Event()
    counts = {"requests": 0, "responses": 0}
    clients = set()

    def stop_on_timeout():
        timed_out.set()
        try:
            if divert.is_open:
                divert.close()
        except (OSError, RuntimeError):
            pass

    watchdog = threading.Timer(TEST_SECONDS, stop_on_timeout)
    watchdog.daemon = True

    try:
        divert.open()
        watchdog.start()
        print("Redirector active: test DNS from your Wi-Fi device(s).", flush=True)

        while not timed_out.is_set():
            packet = divert.recv()
            if packet.is_outbound:
                client = packet.dst_addr
                packet.src_port = ICS_PORT
                counts["responses"] += 1
                kind = "Response"
            else:
                client = packet.src_addr
                packet.dst_port = BETGUARD_PORT
                counts["requests"] += 1
                kind = "Request "

            divert.send(packet)
            clients.add(client)
            print(f"{kind} — client {client}", flush=True)

    except KeyboardInterrupt:
        print("\nManual stop requested.", flush=True)
    except Exception as error:
        if not timed_out.is_set():
            print(f"Redirector error: {error}", flush=True)
            raise
    finally:
        watchdog.cancel()
        try:
            if divert.is_open:
                divert.close()
        except (OSError, RuntimeError):
            pass
        print("\nRedirector stopped; Windows ICS DNS should resume.", flush=True)
        print(f"Requests: {counts['requests']}; Responses: {counts['responses']}", flush=True)
        print(f"Unique client IPs seen: {len(clients)}", flush=True)
        if clients:
            print("Clients: " + ", ".join(sorted(clients)), flush=True)


if __name__ == "__main__":
    main()
