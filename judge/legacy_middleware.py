# Legacy middleware file - imports all middleware classes from middleware.py
# This file exists to maintain compatibility with existing settings.py configuration

from .middleware import (
    ShortCircuitMiddleware,
    DMOJLoginMiddleware,
    IPBasedAuthMiddleware,
    DMOJImpersonationMiddleware,
    ContestMiddleware,
    APIMiddleware,
    MiscConfigMiddleware,
    OrganizationSubdomainMiddleware,
)

# Make all middleware classes available at module level
__all__ = [
    'ShortCircuitMiddleware',
    'DMOJLoginMiddleware', 
    'IPBasedAuthMiddleware',
    'DMOJImpersonationMiddleware',
    'ContestMiddleware',
    'APIMiddleware',
    'MiscConfigMiddleware',
    'OrganizationSubdomainMiddleware',
] 