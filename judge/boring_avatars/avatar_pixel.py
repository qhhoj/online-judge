import random

from judge.boring_avatars.utilities import getRandomColor, hashCode

ELEMENTS = 64
SIZE = 80


def GenerateColors(name, colors):
    numFromName = hashCode(name)
    colorRange = len(colors) if colors else 0

    colorsList = [
        getRandomColor(numFromName % (i + 1), colors, colorRange)
        for i in range(ELEMENTS)
    ]

    return colorsList


def AvatarPixel(props):
    pixelColors = GenerateColors(props.name, props.colors)
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
      <mask
        id="{maskID}"
        mask-type="alpha"
        maskUnits="userSpaceOnUse"
        x="0"
        y="0"
        width="{SIZE}"
        height="{SIZE}"
      >
        <rect width="{SIZE}" height="{SIZE}" rx="{None if props.square else SIZE * 2}" fill="#FFFFFF" />
      </mask>
      <g mask="url(#{maskID})">
        <rect width="10" height="10" fill="{pixelColors[0]}" />
        <rect x="20" width="10" height="10" fill="{pixelColors[1]}" />
        <rect x="40" width="10" height="10" fill="{pixelColors[2]}" />
        <rect x="60" width="10" height="10" fill="{pixelColors[3]}" />
        <rect x="10" width="10" height="10" fill="{pixelColors[4]}" />
        <rect x="30" width="10" height="10" fill="{pixelColors[5]}" />
        <rect x="50" width="10" height="10" fill="{pixelColors[6]}" />
        <rect x="70" width="10" height="10" fill="{pixelColors[7]}" />
        <rect y="10" width="10" height="10" fill="{pixelColors[8]}" />
        <rect y="20" width="10" height="10" fill="{pixelColors[9]}" />
        <rect y="30" width="10" height="10" fill="{pixelColors[10]}" />
        <rect y="40" width="10" height="10" fill="{pixelColors[11]}" />
        <rect y="50" width="10" height="10" fill="{pixelColors[12]}" />
        <rect y="60" width="10" height="10" fill="{pixelColors[13]}" />
        <rect y="70" width="10" height="10" fill="{pixelColors[14]}" />
        <rect x="20" y="10" width="10" height="10" fill="{pixelColors[15]}" />
        <rect x="20" y="20" width="10" height="10" fill="{pixelColors[16]}" />
        <rect x="20" y="30" width="10" height="10" fill="{pixelColors[17]}" />
        <rect x="20" y="40" width="10" height="10" fill="{pixelColors[18]}" />
        <rect x="20" y="50" width="10" height="10" fill="{pixelColors[19]}" />
        <rect x="20" y="60" width="10" height="10" fill="{pixelColors[20]}" />
        <rect x="20" y="70" width="10" height="10" fill="{pixelColors[21]}" />
        <rect x="40" y="10" width="10" height="10" fill="{pixelColors[22]}" />
        <rect x="40" y="20" width="10" height="10" fill="{pixelColors[23]}" />
        <rect x="40" y="30" width="10" height="10" fill="{pixelColors[24]}" />
        <rect x="40" y="40" width="10" height="10" fill="{pixelColors[25]}" />
        <rect x="40" y="50" width="10" height="10" fill="{pixelColors[26]}" />
        <rect x="40" y="60" width="10" height="10" fill="{pixelColors[27]}" />
        <rect x="40" y="70" width="10" height="10" fill="{pixelColors[28]}" />
        <rect x="60" y="10" width="10" height="10" fill="{pixelColors[29]}" />
        <rect x="60" y="20" width="10" height="10" fill="{pixelColors[30]}" />
        <rect x="60" y="30" width="10" height="10" fill="{pixelColors[31]}" />
        <rect x="60" y="40" width="10" height="10" fill="{pixelColors[32]}" />
        <rect x="60" y="50" width="10" height="10" fill="{pixelColors[33]}" />
        <rect x="60" y="60" width="10" height="10" fill="{pixelColors[34]}" />
        <rect x="60" y="70" width="10" height="10" fill="{pixelColors[35]}" />
        <rect x="10" y="10" width="10" height="10" fill="{pixelColors[36]}" />
        <rect x="10" y="20" width="10" height="10" fill="{pixelColors[37]}" />
        <rect x="10" y="30" width="10" height="10" fill="{pixelColors[38]}" />
        <rect x="10" y="40" width="10" height="10" fill="{pixelColors[39]}" />
        <rect x="10" y="50" width="10" height="10" fill="{pixelColors[40]}" />
        <rect x="10" y="60" width="10" height="10" fill="{pixelColors[41]}" />
        <rect x="10" y="70" width="10" height="10" fill="{pixelColors[42]}" />
        <rect x="30" y="10" width="10" height="10" fill="{pixelColors[43]}" />
        <rect x="30" y="20" width="10" height="10" fill="{pixelColors[44]}" />
        <rect x="30" y="30" width="10" height="10" fill="{pixelColors[45]}" />
        <rect x="30" y="40" width="10" height="10" fill="{pixelColors[46]}" />
        <rect x="30" y="50" width="10" height="10" fill="{pixelColors[47]}" />
        <rect x="30" y="60" width="10" height="10" fill="{pixelColors[48]}" />
        <rect x="30" y="70" width="10" height="10" fill="{pixelColors[49]}" />
        <rect x="50" y="10" width="10" height="10" fill="{pixelColors[50]}" />
        <rect x="50" y="20" width="10" height="10" fill="{pixelColors[51]}" />
        <rect x="50" y="30" width="10" height="10" fill="{pixelColors[52]}" />
        <rect x="50" y="40" width="10" height="10" fill="{pixelColors[53]}" />
        <rect x="50" y="50" width="10" height="10" fill="{pixelColors[54]}" />
        <rect x="50" y="60" width="10" height="10" fill="{pixelColors[55]}" />
        <rect x="50" y="70" width="10" height="10" fill="{pixelColors[56]}" />
        <rect x="70" y="10" width="10" height="10" fill="{pixelColors[57]}" />
        <rect x="70" y="20" width="10" height="10" fill="{pixelColors[58]}" />
        <rect x="70" y="30" width="10" height="10" fill="{pixelColors[59]}" />
        <rect x="70" y="40" width="10" height="10" fill="{pixelColors[60]}" />
        <rect x="70" y="50" width="10" height="10" fill="{pixelColors[61]}" />
        <rect x="70" y="60" width="10" height="10" fill="{pixelColors[62]}" />
        <rect x="70" y="70" width="10" height="10" fill="{pixelColors[63]}" />
      </g>
    </svg>
    """
    return svg
