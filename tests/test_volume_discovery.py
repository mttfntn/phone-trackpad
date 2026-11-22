"""volume (Windows via fake pycaw, macOS via a fake osascript) and discovery (fake network adapters)."""
import asyncio
import sys
import unittest
from unittest import mock

from helpers import fake_modules, fresh_import, module


class FakeEndpoint:
    def __init__(self, level=0.5, mute=0):
        self.level, self.mute, self.calls = level, mute, []

    def GetMasterVolumeLevelScalar(self):
        return self.level

    def GetMute(self):
        return self.mute

    def SetMasterVolumeLevelScalar(self, v, ctx):
        self.calls.append(("level", v))

    def SetMute(self, v, ctx):
        self.calls.append(("mute", v))


def fake_pycaw(endpoints):
    """endpoints: list handed out by successive GetSpeakers() calls (default device changes)."""
    it = iter(endpoints)

    class AudioUtilities:
        @staticmethod
        def GetSpeakers():
            return module("speakers", EndpointVolume=next(it))

    pycaw_inner = module("pycaw.pycaw", AudioUtilities=AudioUtilities)
    return {"pycaw": module("pycaw", pycaw=pycaw_inner), "pycaw__pycaw": pycaw_inner}


class VolumeTest(unittest.TestCase):
    def setUp(self):
        self.vol = fresh_import("volume")

    def test_windows_volume(self):
        a, b = FakeEndpoint(0.334, 0), FakeEndpoint(0.9, 1)
        with fake_modules(**fake_pycaw([a, b, b])):
            v = self.vol.WindowsVolume()
            self.assertEqual(asyncio.run(v.get()), (33, False))
            self.assertEqual(asyncio.run(v.get()), (90, True))   # picks up the new default device
            asyncio.run(v.set_level(25))
            asyncio.run(v.set_muted(True))
        self.assertEqual(b.calls, [("level", 0.25), ("mute", 1)])

    def test_create_volume_per_platform(self):
        with mock.patch.object(sys, "platform", "darwin"):
            self.assertIsInstance(self.vol.create_volume(), self.vol.MacVolume)
        with mock.patch.object(sys, "platform", "win32"), fake_modules(**fake_pycaw([])):
            self.assertIsInstance(self.vol.create_volume(), self.vol.WindowsVolume)
        with mock.patch.object(sys, "platform", "linux"):
            self.assertIsNone(self.vol.create_volume())

    def test_create_volume_without_pycaw(self):
        with mock.patch.object(sys, "platform", "win32"), mock.patch.dict(sys.modules, {"pycaw": None}), \
                mock.patch("builtins.print") as out:
            self.assertIsNone(self.vol.create_volume())
        self.assertIn("Volume control unavailable", out.call_args[0][0])

    def test_mac_get_parses_osascript(self):
        v = self.vol.MacVolume()
        with mock.patch.object(self.vol.MacVolume, "_osascript", mock.AsyncMock(return_value="37,true")):
            self.assertEqual(asyncio.run(v.get()), (37, True))

    def test_mac_set_level_coalesces_to_newest(self):
        scripts = []

        async def slow_osascript(script):
            scripts.append(script)
            await asyncio.sleep(0.05)
            return ""

        async def drag():
            v = self.vol.MacVolume()
            for level in (10, 20, 30, 40):
                await v.set_level(level)
                await asyncio.sleep(0.01)
            await asyncio.sleep(0.2)
            await v.set_muted(True)
            await v.set_muted(False)

        with mock.patch.object(self.vol.MacVolume, "_osascript", staticmethod(slow_osascript)):
            asyncio.run(drag())
        self.assertEqual(scripts, ["set volume output volume 10", "set volume output volume 40",
                                   "set volume output muted true", "set volume output muted false"])

    @unittest.skipUnless(sys.platform == "darwin", "needs macOS osascript")
    def test_mac_real_get(self):
        # Only reads the volume; never changes it.
        try:
            level, muted = asyncio.run(self.vol.MacVolume().get())
        except ValueError:
            self.skipTest("no audio output device (osascript returned 'missing value')")
        self.assertTrue(0 <= level <= 100)
        self.assertIsInstance(muted, bool)

    def test_fake_volume(self):
        v = self.vol.FakeVolume()
        with mock.patch("builtins.print"):
            asyncio.run(v.set_level(12))
            asyncio.run(v.set_muted(True))
        self.assertEqual(asyncio.run(v.get()), (12, True))


class Ip:
    def __init__(self, ip):
        self.ip = ip
        self.is_IPv4 = isinstance(ip, str)


class DiscoveryTest(unittest.TestCase):
    def test_local_addresses_skip_loopback_linklocal_ipv6(self):
        adapters = [module("a", ips=[Ip("127.0.0.1"), Ip(("fe80::1", 0, 0))]),
                    module("b", ips=[Ip("192.168.1.15"), Ip("169.254.3.4")]),
                    module("c", ips=[Ip("10.0.0.2")])]
        disc = fresh_import("discovery")
        with mock.patch.object(disc.ifaddr, "get_adapters", return_value=adapters):
            self.assertEqual(disc.local_ipv4_addresses(), ["192.168.1.15", "10.0.0.2"])


if __name__ == "__main__":
    unittest.main()
