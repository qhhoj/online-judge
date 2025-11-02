from django.utils.safestring import mark_safe

from judge.boring_avatars import (
    Avatar,
    AvatarProperties,
)

from . import registry  # noqa: I202


@registry.function
def boring_avatars(**kwargs):
    return mark_safe('<div class="svg-container">' + Avatar(AvatarProperties(**kwargs)) + '</div>')
