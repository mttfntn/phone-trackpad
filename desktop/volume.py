"""Reads and sets the computer's master output volume."""
import asyncio
import sys


class WindowsVolume:
    """Default playback device via Core Audio (pycaw). Must be used from the thread that imported it."""

    def __init__(self):
        from pycaw.pycaw import AudioUtilities
        self._utils = AudioUtilities
        self._ev = None

    def _endpoint(self, refresh=False):
        # Re-fetched on refresh so switching to headphones etc. is picked up.
        if self._ev is None or refresh:
            self._ev = self._utils.GetSpeakers().EndpointVolume
        return self._ev

    async def get(self):
        ev = self._endpoint(refresh=True)
        return round(ev.GetMasterVolumeLevelScalar() * 100), bool(ev.GetMute())

    async def set_level(self, level):
        self._endpoint().SetMasterVolumeLevelScalar(level / 100, None)

    async def set_muted(self, muted):
        self._endpoint().SetMute(int(muted), None)


class MacVolume:
    """System output volume via AppleScript. Slider drags are coalesced to the newest level."""

    def __init__(self):
        self._pending = None
        self._worker = None

    @staticmethod
    async def _osascript(script):
        proc = await asyncio.create_subprocess_exec(
            "osascript", "-e", script, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
        out, _ = await proc.communicate()
        return out.decode().strip()

    async def get(self):
        out = await self._osascript("set s to get volume settings\n"
                                    "return (output volume of s as text) & \",\" & (output muted of s as text)")
        level, muted = out.split(",")
        return int(level), muted == "true"

    async def set_level(self, level):
        self._pending = level
        if self._worker is None or self._worker.done():
            self._worker = asyncio.ensure_future(self._apply())

    async def _apply(self):
        while self._pending is not None:
            level, self._pending = self._pending, None
            await self._osascript(f"set volume output volume {level}")

    async def set_muted(self, muted):
        await self._osascript(f"set volume output muted {'true' if muted else 'false'}")


class FakeVolume:
    """For --dry-run: remembers the level and logs changes."""

    def __init__(self):
        self.level, self.muted = 50, False

    async def get(self):
        return self.level, self.muted

    async def set_level(self, level):
        self.level = level
        print(f"[dry-run] volume {level}")

    async def set_muted(self, muted):
        self.muted = muted
        print(f"[dry-run] mute {muted}")


def create_volume():
    """Returns a volume controller for this OS, or None if it isn't available."""
    try:
        if sys.platform == "win32":
            return WindowsVolume()
        if sys.platform == "darwin":
            return MacVolume()
    except Exception as e:
        print(f"Volume control unavailable: {e}")
    return None
