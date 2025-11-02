import random

from judge.boring_avatars.utilities import (
    getBoolean,
    getRandomColor,
    getUnit,
    hashCode
)


ELEMENTS = 4
SIZE = 80


def generateColors(name, colors):
    numFromName = hashCode(name)
    colorRange = len(colors) if colors else None

    elementsProperties = [
        {
            'color': getRandomColor(numFromName + i, colors, colorRange),
            'translateX': getUnit(numFromName * (i + 1), SIZE / 2 - (i + 17), 1),
            'translateY': getUnit(numFromName * (i + 1), SIZE / 2 - (i + 17), 2),
            'rotate': getUnit(numFromName * (i + 1), 360),
            'isSquare': getBoolean(numFromName, 2),
        }
        for i in range(ELEMENTS)
    ]

    return elementsProperties


def AvatarBauhaus(props):
    properties = generateColors(props.name, props.colors)
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
      {'<title>' + props.name + '</title>' if props.title else ''}
      <mask id="{maskID}" maskUnits="userSpaceOnUse" x="0" y="0" width="{SIZE}" height="{SIZE}">
        <rect width="{SIZE}" height="{SIZE}" {'rx="' + str(props.size * 2) + '"' if not props.square else ''}
         fill="#FFFFFF" />
      </mask>
      <g mask="url(#{maskID})">
        <rect width="{SIZE}" height="{SIZE}" fill="{properties[0]['color']}" />
        <rect
            x="{(SIZE - 60) / 2}"
            y="{(SIZE - 20) / 2}"
            width="{SIZE}"
            height="{SIZE if properties[1]['isSquare'] else SIZE / 8}"
            fill="{properties[1]['color']}"
            transform="{
                'translate(' +
                str(properties[1]['translateX']) +
                ' ' +
                str(properties[1]['translateY']) +
                ') rotate(' +
                str(properties[1]['rotate']) +
                ' ' +
                str(SIZE / 2) +
                ' ' +
                str(SIZE / 2) +
                ')'
            }"
        />
        <circle
          cx="{SIZE / 2}"
          cy="{SIZE / 2}"
          fill="{properties[2]['color']}"
          r="{SIZE / 5}"
          transform="translate({'' + str(properties[2]['translateX']) + ' ' + str(properties[2]['translateY']) + ''})"
        />
        <line
          x1="{0}"
          y1="{SIZE / 2}"
          x2="{SIZE}"
          y2="{SIZE / 2}"
          strokeWidth="{2}"
          stroke="{properties[3]['color']}"
          transform="{
            'translate(' +
            str(properties[3]['translateX']) +
            ' ' +
            str(properties[3]['translateY']) +
            ') rotate(' +
            str(properties[3]['rotate']) +
            ' ' +
            str(SIZE / 2) +
            ' ' +
            str(SIZE / 2) +
            ')'
          }"
        />
      </g>
    </svg>
    """

    return svg
