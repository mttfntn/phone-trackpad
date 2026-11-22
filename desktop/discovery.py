"""This computer's network addresses (for the link), and its Bonjour/mDNS announcement.

The announcement (_phone-trackpad._tcp) lets Bonjour browsers find the helper; the phone page
itself doesn't use it, since browsers can't browse Bonjour. The link uses the first address.
"""
import socket

import ifaddr
from zeroconf import IPVersion, ServiceInfo
from zeroconf.asyncio import AsyncZeroconf

SERVICE_TYPE = "_phone-trackpad._tcp.local."


def local_ipv4_addresses():
    """IPv4 addresses of this computer's network adapters, without loopback and link-local."""
    addrs = []
    for adapter in ifaddr.get_adapters():
        for ip in adapter.ips:
            if ip.is_IPv4 and not ip.ip.startswith(("127.", "169.254.")):
                addrs.append(ip.ip)
    return addrs


class Advertiser:
    """Announces the helper as a Bonjour service while it runs."""

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
        self._registered = False

    async def start(self):
        self._zc = AsyncZeroconf(ip_version=IPVersion.V4Only)
        await self._zc.async_register_service(self.info, allow_name_change=True)
        self._registered = True

    async def stop(self):
        """Withdraws the announcement; safe if start() never finished or failed."""
        if self._registered:
            await self._zc.async_unregister_service(self.info)
            self._registered = False
        if self._zc:
            await self._zc.async_close()
            self._zc = None
