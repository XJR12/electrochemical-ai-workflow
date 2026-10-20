#!/usr/bin/env python3
"""Output directory numbering.

Every run must create a fresh directory: <name>_0, <name>_1, <name>_2 ...
An existing directory is never reused or overwritten.
"""

import os


def next_output_dir(base):
    """Return the first unused ``<base>_<n>`` directory (n starts at 0).

    The directory is not created here; callers create it when writing.
    """
    for n in range(1000):
        candidate = "%s_%d" % (base, n)
        if not os.path.exists(candidate):
            return candidate
    raise RuntimeError("输出目录编号过多（已到 _999），请先清理：%s" % base)
