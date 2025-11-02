import random

from judge.boring_avatars.utilities import (
    getRandomColor,
    hashCode
)


SIZE = 90
COLORS = 5


def generateColors(colors, name):
    numFromName = hashCode(name)
    range_len = len(colors) if colors else 0
    colorsShuffle = [getRandomColor(numFromName + i, colors, range_len) for i in range(COLORS)]

    colorsList = [
        colorsShuffle[0],
        colorsShuffle[1],
        colorsShuffle[1],
        colorsShuffle[2],
        colorsShuffle[2],
        colorsShuffle[3],
        colorsShuffle[3],
        colorsShuffle[0],
        colorsShuffle[4],
    ]

    return colorsList


def AvatarRing(props):
    ringColors = generateColors(props.colors, props.name)
    maskID = random.randrange(10**9, 10**10 - 1)

    svg = f"""
    <svg
      viewBox="0 0 {SIZE} {SIZE}"
      style="display: block; {props.style}"
      fill="none"
      role="img"
      xmlns="http://www.w3.org/2000/svg"
      width="{props.size}"
      height="{props.size}"
    >
      {f"<title>{props.name}</title>" if props.title else ''}
      <mask id="{maskID}" maskUnits="userSpaceOnUse" x="0" y="0" width="{SIZE}" height="{SIZE}">
        <rect width="{SIZE}" height="{SIZE}" rx="{None if props.square else SIZE * 2}" fill="#FFFFFF" />
      </mask>
      <g mask="url(#{maskID})">
        <path d="M0 0h90v45H0z" fill="{ringColors[0]}" />
        <path d="M0 45h90v45H0z" fill="{ringColors[1]}" />
        <path d="M83 45a38 38 0 00-76 0h76z" fill="{ringColors[2]}" />
        <path d="M83 45a38 38 0 01-76 0h76z" fill="{ringColors[3]}" />
        <path d="M77 45a32 32 0 10-64 0h64z" fill="{ringColors[4]}" />
        <path d="M77 45a32 32 0 11-64 0h64z" fill="{ringColors[5]}" />
        <path d="M71 45a26 26 0 00-52 0h52z" fill="{ringColors[6]}" />
        <path d="M71 45a26 26 0 01-52 0h52z" fill="{ringColors[7]}" />
        <circle cx="45" cy="45" r="23" fill="{ringColors[8]}" />
      </g>
    </svg>
    """

    return svg
