"""Phone Trackpad's version and the oldest Python it runs on.

Kept in step with pyproject.toml (`version`, `requires-python`); a test checks that they match,
and the release workflow checks that a pushed tag vX.Y.Z matches VERSION.
"""
VERSION = "1.0.0"
MIN_PYTHON = (3, 10)
