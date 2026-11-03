"""Advertises the server on the local network via Bonjour/mDNS."""
import socket

import ifaddr
from zeroconf import IPVersion, ServiceInfo
from zeroconf.asyncio import AsyncZeroconf

SERVICE_TYPE = "_phonepad._tcp.local."


def local_ipv4_addresses():
    addrs = []
    for adapter in ifaddr.get_adapters():
        for ip in adapter.ips:
            if ip.is_IPv4 and not ip.ip.startswith(("127.", "169.254.")):
                addrs.append(ip.ip)
    return addrs


class Advertiser:
    def __init__(self, name, port, os_name):
        self.addresses = local_ipv4_addresses()
        self.info = ServiceInfo(
            SERVICE_TYPE,
            f"{name}.{SERVICE_TYPE}",
            port=port,
            addresses=[socket.inet_aton(a) for a in self.addresses],
            properties={"name": name, "os": os_name},
            server=f"{socket.gethostname().split('.')[0]}.local.",
        )
        self._zc = None

    async def start(self):
        self._zc = AsyncZeroconf(ip_version=IPVersion.V4Only)
        await self._zc.async_register_service(self.info, allow_name_change=True)

    async def stop(self):
        if self._zc:
            await self._zc.async_unregister_service(self.info)
            await self._zc.async_close()
