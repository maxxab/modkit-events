"""Select finite recovery acceptance hosts without consulting the product gate.

Object-layout accounting still runs unmodified in every selected test. CI has
explicit lanes for both accepted versions; broad hosts test refusal separately.
"""

import platform
import struct
import sys
import sysconfig
import unittest

RECOVERY_HOST = (
    sys.implementation.name == "cpython"
    and sys.platform == "linux"
    and struct.calcsize("P") == 8
    and (
        sys.version_info[:3] == (3, 12, 3)
        or (
            tuple(sys.version_info) == (3, 13, 5, "final", 0)
            and platform.machine() == "x86_64"
            and sysconfig.get_config_var("Py_DEBUG") == 0
            and sysconfig.get_config_var("Py_GIL_DISABLED") == 0
            and getattr(sys, "_is_gil_enabled", lambda: False)() is True
        )
    )
)
requires_recovery_profile = unittest.skipUnless(
    RECOVERY_HOST,
    "finite recovery acceptance requires Linux CPython 3.12.3 or 3.13.5 release/GIL profile",
)
