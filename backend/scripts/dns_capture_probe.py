
import pydivert

# Capture only incoming IPv4 DNS queries from Mercusys clients.
# SNIFF mode observes packets without redirecting or blocking them.

FILTER = (
    "inbound and ip and udp "
    "and udp.DstPort == 53 "
    "and ip.DstAddr == 192.168.137.1 "
    "and ip.SrcAddr >= 192.168.137.2 "
    "and ip.SrcAddr <= 192.168.137.254"
)

def main():
    print("BetGuard DNS Capture Test")
    print("Waiting for client DNS requests...")
    print("Press Ctrl+C to stop.\n")

    try:
        with pydivert.WinDivert(
            FILTER,
            flags=pydivert.Flag.SNIFF
        ) as capture:
            for packet in capture:
                print(
                    f"DNS request: "
                    f"{packet.src_addr}:{packet.src_port} "
                    f"-> {packet.dst_addr}:{packet.dst_port}",
                    flush=True
                )
    except KeyboardInterrupt:
        print("\nCapture stopped.")

if __name__ == "__main__":
    main()
