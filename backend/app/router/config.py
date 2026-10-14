import ipaddress
import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RouterSettings:
    # Keep the original field order intact so existing
    # positional construction remains backward-compatible.
    bind: str
    port: int
    peers: tuple[str, ...]
    upstream: str
    token: str
    state_path: Path
    ca_file: str | None = None

    # New stock-router compatibility options are appended
    # with defaults so the existing OpenWrt implementation
    # and tests continue to work unchanged.
    client_networks: tuple[str, ...] = ()
    mode: str = "openwrt"

    @classmethod
    def environment(cls):
        if os.getenv("BETGUARD_ROUTER_ENABLED", "0") != "1":
            return None

        mode = os.getenv(
            "BETGUARD_ROUTER_MODE",
            "openwrt",
        ).strip().lower()

        if mode not in ("openwrt", "stock_dhcp"):
            raise ValueError(
                "BETGUARD_ROUTER_MODE must be "
                "'openwrt' or 'stock_dhcp'"
            )

        bind = ipaddress.ip_address(
            os.environ["BETGUARD_ROUTER_DNS_BIND"]
        )

        peer_values = [
            item.strip()
            for item in os.getenv(
                "BETGUARD_ROUTER_PEERS",
                "",
            ).split(",")
            if item.strip()
        ]

        peers = tuple(
            str(ipaddress.ip_address(item))
            for item in peer_values
        )

        network_values = [
            item.strip()
            for item in os.getenv(
                "BETGUARD_ROUTER_CLIENT_NETWORKS",
                "",
            ).split(",")
            if item.strip()
        ]

        networks = tuple(
            ipaddress.ip_network(
                item,
                strict=False,
            )
            for item in network_values
        )

        client_networks = tuple(
            str(network)
            for network in networks
        )

        upstream = ipaddress.ip_address(
            os.getenv(
                "BETGUARD_ROUTER_UPSTREAM",
                "1.1.1.1",
            )
        )

        port = int(
            os.getenv(
                "BETGUARD_ROUTER_DNS_PORT",
                "5353",
            )
        )

        token = os.environ[
            "BETGUARD_ROUTER_ADMIN_TOKEN"
        ]

        if (
            bind.version != 4
            or not bind.is_private
            or bind.is_loopback
            or bind.is_unspecified
            or not (
                port == 53
                or 1024 <= port <= 65535
            )
            or len(token) < 32
            or not upstream.is_global
        ):
            raise ValueError(
                "Invalid router service configuration"
            )

        for peer in peers:
            address = ipaddress.ip_address(peer)

            if (
                address.version != 4
                or not address.is_private
                or address.is_loopback
                or address.is_unspecified
            ):
                raise ValueError(
                    "Invalid router peer configuration"
                )

        for network in networks:
            if (
                network.version != 4
                or not network.is_private
                or network.is_loopback
                or network.prefixlen == 0
            ):
                raise ValueError(
                    "Invalid router client network"
                )

        if mode == "openwrt":
            if not peers:
                raise ValueError(
                    "OpenWrt mode requires at least "
                    "one authorized router peer"
                )

        if mode == "stock_dhcp":
            if not networks:
                raise ValueError(
                    "Stock DHCP mode requires at least "
                    "one authorized client network"
                )

            if not any(
                bind in network
                for network in networks
            ):
                raise ValueError(
                    "The DNS listener address must "
                    "belong to an authorized client network"
                )

        state_path = Path(
            os.getenv(
                "BETGUARD_ROUTER_STATE_PATH",
                str(
                    Path(__file__).resolve().parents[2]
                    / ".local"
                    / "router.sqlite3"
                ),
            )
        )

        ca_file = (
            os.getenv("BETGUARD_ROUTER_CA_FILE")
            or None
        )

        return cls(
            bind=str(bind),
            port=port,
            peers=peers,
            upstream=str(upstream),
            token=token,
            state_path=state_path,
            ca_file=ca_file,
            client_networks=client_networks,
            mode=mode,
        )