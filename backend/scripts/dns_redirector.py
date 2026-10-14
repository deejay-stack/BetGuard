"""BetGuard: time-limited, single-client UDP DNS redirection test.

Requirements:
  - Run as Windows Administrator with pydivert 3.1.1.
  - BetGuard DNS must listen on 192.168.137.1:5300.
  - Windows ICS continues to listen on port 53.

This is an experimental prototype, NOT a production DNS firewall.
Only redirects DNS for the one specified iPhone. Test expires automatically.
"""

import threading

import pydivert


GATEWAY_IP = "192.168.137.1"
CLIENT_IP = "192.168.137.216"
ICS_DNS_PORT = 53
BETGUARD_DNS_PORT = 5300
TEST_SECONDS = 180  # Automatic shutdown after three minutes.

FILTER = (
    f"(inbound and ip and udp and "
    f"ip.SrcAddr == {CLIENT_IP} and "
    f"ip.DstAddr == {GATEWAY_IP} and "
    f"udp.DstPort == {ICS_DNS_PORT}) or "
    f"(outbound and ip and udp and "
    f"ip.SrcAddr == {GATEWAY_IP} and "
    f"ip.DstAddr == {CLIENT_IP} and "
    f"udp.SrcPort == {BETGUARD_DNS_PORT})"
)


def main():
    print("BetGuard DNS Redirector - SINGLE CLIENT TEST", flush=True)
    print(f"Client: {CLIENT_IP}", flush=True)
    print(
        f"Request: {GATEWAY_IP}:{ICS_DNS_PORT}"
        f" -> {GATEWAY_IP}:{BETGUARD_DNS_PORT}",
        flush=True,
    )
    print(f"Test will automatically stop in {TEST_SECONDS} seconds.", flush=True)
    print("Keep Windows ICS and the BetGuard DNS backend running.\n", flush=True)

    divert = pydivert.WinDivert(FILTER)
    timed_out = threading.Event()
    counts = {"requests": 0, "responses": 0}

    def stop_on_timeout():
        timed_out.set()
        # Closing the handle releases captured traffic and unblocks recv().
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
        print("Redirector active. Test from your iPhone now.\n", flush=True)

        while not timed_out.is_set():
            packet = divert.recv()

            if packet.is_outbound:
                # BetGuard response -> appear to iPhone as a normal port-53 reply.
                packet.src_port = ICS_DNS_PORT
                kind = "Response"
                counts["responses"] += 1
            else:
                # iPhone query -> deliver locally to BetGuard, not ICS DNS.
                packet.dst_port = BETGUARD_DNS_PORT
                kind = "Request "
                counts["requests"] += 1

            # PyDivert recalculates IPv4 and UDP checksums when sending.
            divert.send(packet)
            print(
                f"{kind}: {packet.src_addr}:{packet.src_port} -> "
                f"{packet.dst_addr}:{packet.dst_port}",
                flush=True,
            )

    except KeyboardInterrupt:
        print("\nManual stop requested.", flush=True)
    except (OSError, RuntimeError) as error:
        if not timed_out.is_set():
            print(f"Redirector error: {error}", flush=True)
            raise
    finally:
        watchdog.cancel()
        if divert.is_open:
            try:
                divert.close()
            except (OSError, RuntimeError):
                pass
        print(
            f"\nRedirector stopped. "
            f"Requests: {counts['requests']}, "
            f"Responses: {counts['responses']}. "
            "Windows ICS DNS should be in control again.",
            flush=True,
        )


if __name__ == "__main__":
    main()
