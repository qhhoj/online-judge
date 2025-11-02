import random
import re

from judge.boring_avatars.utilities import (
    getRandomColor,
    hashCode
)


ELEMENTS = 4
SIZE = 80


def generateColors(name, colors):
    numFromName = hashCode(name)
    range_len = len(colors) if colors else 0

    colorsList = [getRandomColor(numFromName + i, colors, range_len) for i in range(ELEMENTS)]
    return colorsList


def AvatarSunset(props):
    sunsetColors = generateColors(props.name, props.colors)
    name = re.sub(r'\s+', '', props.name)  # Removes spaces from name
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
        <path fill="url(#gradient_paint0_linear_{name})" d="M0 0h80v40H0z" />
        <path fill="url(#gradient_paint1_linear_{name})" d="M0 40h80v40H0z" />
      </g>
      <defs>
        <linearGradient
          id="gradient_paint0_linear_{name}"
          x1="{SIZE / 2}"
          y1="0"
          x2="{SIZE / 2}"
          y2="{SIZE / 2}"
          gradientUnits="userSpaceOnUse"
        >
          <stop stopColor="{sunsetColors[0]}" />
          <stop offset="1" stopColor="{sunsetColors[1]}" />
        </linearGradient>
        <linearGradient
          id="gradient_paint1_linear_{name}"
          x1="{SIZE / 2}"
          y1="{SIZE / 2}"
          x2="{SIZE / 2}"
          y2="{SIZE}"
          gradientUnits="userSpaceOnUse"
        >
          <stop stopColor="{sunsetColors[2]}" />
          <stop offset="1" stopColor="{sunsetColors[3]}" />
        </linearGradient>
      </defs>
    </svg>
    """

    return svg
