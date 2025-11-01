"""
Monkey patch for django-compressor to work with Django 5.1+

Django 5.1 removed get_storage_class() function which django-compressor 4.4 still uses.
This patch provides a compatibility layer.
"""
import sys
from django.core.files import storage as django_storage


def get_storage_class(import_path=None):
    """
    Compatibility function for Django 5.1+ which removed get_storage_class().
    
    This function mimics the old behavior by using Django's storages system.
    """
    if import_path is None:
        # Return default storage class
        from django.core.files.storage import default_storage
        return default_storage.__class__
    
    # Parse the import path
    try:
        module_path, class_name = import_path.rsplit('.', 1)
    except ValueError:
        raise ImportError(f"Invalid storage path: {import_path}")
    
    # Import the module and get the class
    from importlib import import_module
    try:
        module = import_module(module_path)
        return getattr(module, class_name)
    except (ImportError, AttributeError) as e:
        raise ImportError(f"Could not import storage class '{import_path}': {e}")


# Monkey patch django.core.files.storage to add back get_storage_class
if not hasattr(django_storage, 'get_storage_class'):
    django_storage.get_storage_class = get_storage_class
    print("✓ Applied django-compressor compatibility patch for Django 5.1+", file=sys.stderr)

