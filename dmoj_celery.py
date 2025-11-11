import os

try:
    import MySQLdb  # noqa: F401, imported for side effect
except ImportError:
    import dmoj_install_pymysql  # noqa: F401, imported for side effect

# set the default Django settings module for the 'celery' program.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'dmoj.settings')

# Apply django-compressor compatibility patch BEFORE Django setup
# This must run before any django-compressor imports
try:
    import dmoj.compressor_patch  # noqa: F401, imported for side effect
except ImportError:
    pass

# noinspection PyUnresolvedReferences
from dmoj.celery import app  # noqa: E402, F401, imported for side effect
