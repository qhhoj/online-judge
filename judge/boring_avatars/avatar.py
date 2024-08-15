from judge.boring_avatars.avatar_bauhaus import AvatarBauhaus
from judge.boring_avatars.avatar_beam import AvatarBeam
from judge.boring_avatars.avatar_marble import AvatarMarble
from judge.boring_avatars.avatar_pixel import AvatarPixel
from judge.boring_avatars.avatar_ring import AvatarRing
from judge.boring_avatars.avatar_sunset import AvatarSunset

DEFAULT_GENRE = 'beam'
MATCH_GENRE_FROM_STRING = {
    'bauhaus': AvatarBauhaus,
    'beam': AvatarBeam,
    'marble': AvatarMarble,
    'pixel': AvatarPixel,
    'ring': AvatarRing,
    'sunset': AvatarSunset,
}


def Avatar(props):
    if props.genre not in MATCH_GENRE_FROM_STRING:
        props.genre = DEFAULT_GENRE
    avatar = MATCH_GENRE_FROM_STRING[props.genre]
    return avatar(props)
