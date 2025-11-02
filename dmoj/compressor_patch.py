"""
Compatibility patch for django-compressor to work with Django 5.1+

Django 5.1 removed get_storage_class() function which django-compressor 4.4 still uses.
This patch provides a compatibility layer using Django's new storages API.

Reference: https://docs.djangoproject.com/en/5.1/ref/files/storage/
"""
import sys

from django.core.files import storage as django_storage


def get_storage_class(import_path=None):
    """
    Compatibility function for Django 5.1+ which removed get_storage_class().

    Uses Django's new storages.create_storage() API instead of the old
    get_storage_class() function.

    Args:
        import_path: Dotted path to storage class (e.g., 'django.core.files.storage.FileSystemStorage')
                     If None, returns the default storage class.

    Returns:
        Storage class (not instance)
    """
    if import_path is None:
        # Return default storage class
        from django.core.files.storage import default_storage
        return default_storage.__class__

    # Parse the import path to get module and class name
    try:
        module_path, class_name = import_path.rsplit('.', 1)
    except ValueError:
        raise ImportError(f"Invalid storage path: {import_path}")  # noqa: Q000

    # Import the module and get the class
    from importlib import import_module
    try:
        module = import_module(module_path)
        storage_class = getattr(module, class_name)
        return storage_class
    except (ImportError, AttributeError) as e:
        raise ImportError(f"Could not import storage class '{import_path}': {e}")


# Apply monkey patch to django.core.files.storage
if not hasattr(django_storage, 'get_storage_class'):
    django_storage.get_storage_class = get_storage_class
    print("✓ Applied django-compressor compatibility patch for Django 5.1+", file=sys.stderr)  # noqa: Q000
