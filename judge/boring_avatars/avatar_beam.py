import random
from types import SimpleNamespace

from judge.boring_avatars.utilities import getBoolean, getContrast, getRandomColor, getUnit, hashCode

SIZE = 36


def generateData(name, colors):
    numFromName = hashCode(name)
    colorRange = len(colors) if colors else None
    wrapperColor = getRandomColor(numFromName, colors, colorRange)
    preTranslateX = getUnit(numFromName, 10, 1)
    wrapperTranslateX = preTranslateX + SIZE / 9 if preTranslateX < 5 else preTranslateX
    preTranslateY = getUnit(numFromName, 10, 2)
    wrapperTranslateY = preTranslateY + SIZE / 9 if preTranslateY < 5 else preTranslateY

    data = SimpleNamespace(
        wrapperColor=wrapperColor,
        faceColor=getContrast(wrapperColor),
        backgroundColor=getRandomColor(numFromName + 13, colors, colorRange),
        wrapperTranslateX=wrapperTranslateX,
        wrapperTranslateY=wrapperTranslateY,
        wrapperRotate=getUnit(numFromName, 360),
        wrapperScale=1 + getUnit(numFromName, SIZE // 12) / 10,
        isMouthOpen=getBoolean(numFromName, 2),
        isCircle=getBoolean(numFromName, 1),
        eyeSpread=getUnit(numFromName, 5),
        mouthSpread=getUnit(numFromName, 3),
        faceRotate=getUnit(numFromName, 10, 3),
        faceTranslateX=wrapperTranslateX / 2 if wrapperTranslateX > SIZE / 6 else getUnit(numFromName, 8, 1),
        faceTranslateY=wrapperTranslateY / 2 if wrapperTranslateY > SIZE / 6 else getUnit(numFromName, 7, 2),
    )

    return data


def AvatarBeam(props):
    data = generateData(props.name, props.colors)
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
            <rect width="{SIZE}" height="{SIZE}" rx="{None if props.square else SIZE * 2}" fill="#FFFFFF" />
        </mask>
        <g mask="url(#{maskID})">
            <rect width="{SIZE}" height="{SIZE}" fill="{data.backgroundColor}" />
            <rect
            x="0"
            y="0"
            width="{SIZE}"
            height="{SIZE}"
            transform="translate({data.wrapperTranslateX} {data.wrapperTranslateY})
             rotate({data.wrapperRotate} {SIZE / 2} {SIZE / 2}) scale({data.wrapperScale})"
            fill="{data.wrapperColor}"
            rx="{SIZE if data.isCircle else SIZE / 6}"
            />
            <g
            transform="translate({data.faceTranslateX} {data.faceTranslateY})
             rotate({data.faceRotate} {SIZE / 2} {SIZE / 2})"
            >
            {f'''
                <path
                d="M15 {19 + data.mouthSpread}c2 1 4 1 6 0"
                stroke="{data.faceColor}"
                fill="none"
                strokeLinecap="round"
                />
            ''' if data.isMouthOpen else f'''
                <path
                d="M13,{19 + data.mouthSpread} a1,0.75 0 0,0 10,0"
                fill="{data.faceColor}"
                />
            '''}
            <rect
                x="{14 - data.eyeSpread}"
                y="14"
                width="1.5"
                height="2"
                rx="1"
                stroke="none"
                fill="{data.faceColor}"
            />
            <rect
                x="{20 + data.eyeSpread}"
                y="14"
                width="1.5"
                height="2"
                rx="1"
                stroke="none"
                fill="{data.faceColor}"
            />
            </g>
        </g>
        </svg>
        """

    return svg
