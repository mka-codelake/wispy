"""Entry point for `python -m wispy`.

Uses an absolute import (not `from .main`) so PyInstaller can load this
as a top-level script without tripping over package-relative imports.
"""

from wispy.main import main

if __name__ == "__main__":
    main()
