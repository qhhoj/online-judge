from django.apps import AppConfig
from django.db import DatabaseError
from django.utils.translation import gettext_lazy


class JudgeAppConfig(AppConfig):
    name = 'judge'
    verbose_name = gettext_lazy('Online Judge')

    def ready(self):
        # Django 5 compatibility: Add force_text alias for packages that still use it
        # force_text was removed in Django 4.0 and replaced with force_str
        try:
            from django.utils.encoding import force_text  # noqa: F401
        except ImportError:
            # If force_text doesn't exist (Django 4.0+), create an alias
            from django.utils import encoding
            encoding.force_text = encoding.force_str

        # WARNING: AS THIS IS NOT A FUNCTIONAL PROGRAMMING LANGUAGE,
        #          OPERATIONS MAY HAVE SIDE EFFECTS.
        #          DO NOT REMOVE THINKING THE IMPORT IS UNUSED.
        # noinspection PyUnresolvedReferences
        from django.contrib.auth.models import User

        from judge.models import (
            Language,
            Profile,
        )

        from . import (  # noqa: F401, imported for side effects
            jinja2,
            signals,
        )

        try:
            lang = Language.get_default_language()
            for user in User.objects.filter(profile=None):
                # These poor profileless users
                profile = Profile(user=user, language=lang)
                profile.save()
        except DatabaseError:
            pass

        # Schedule all pending FSO contests on server startup
        try:
            from judge.utils.fso_scheduler import reschedule_all_fso_contests
            reschedule_all_fso_contests()
        except Exception:
            # Don't crash if scheduling fails
            pass
