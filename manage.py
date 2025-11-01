#!/usr/bin/env python
import os
import sys

try:
    import MySQLdb  # noqa: F401, imported for side effect
except ImportError:
    import dmoj_install_pymysql  # noqa: F401, imported for side effect

if __name__ == '__main__':
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'dmoj.settings')

    # Apply django-compressor compatibility patch BEFORE Django setup
    # This must run before any django-compressor imports
    try:
        import dmoj.compressor_patch  # noqa: F401
    except ImportError:
        pass

    from django.core.management import execute_from_command_line
    execute_from_command_line(sys.argv)
