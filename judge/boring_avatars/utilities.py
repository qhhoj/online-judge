import math


def hashCode(name):
    hash = 0
    for character in name:
        hash = (hash << 5) - hash + ord(character)
        hash = hash & 0xFFFFFFFF  # Ensure it's a 32-bit integer
    return abs(hash)


def getDigit(number, postion):
    return (number // (10 ** postion)) % 10


def getBoolean(number, postion):
    return (getDigit(number, postion) % 2) == 0


def getAngle(x, y):
    return math.degrees(math.atan2(y, x))


def getUnit(number, range, index=None):
    value = number % range

    if index and getBoolean(number, index):
        return -value

    return value


def getRandomColor(number, colors, range):
    return colors[number % range]


def getContrast(hexcolor):
    if hexcolor.startswith('#'):
        hexcolor = hexcolor[1:]

    r = int(hexcolor[0:2], 16)
    g = int(hexcolor[2:4], 16)
    b = int(hexcolor[4:6], 16)

    yiq = ((r * 299) + (g * 587) + (b * 114)) / 1000

    return '#000000' if yiq >= 128 else '#FFFFFF'


class AvatarProperties:
    genre = 'beam'
    colors = ['#0A0310', '#49007E', '#FF005B', '#FF7D10', '#FFB238']
    name = 'Sample Name'
    title = False
    size = 40
    square = False
    style = ''

    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)
