MathJax = {
    package: [
        'base',
    ],
    options: {
        ignoreHtmlClass: 'tex2jax_ignore',
        processHtmlClass: 'tex2jax_process'
    },
    loader: {
        load: [
            '[tex]/textmacros',
            '[tex]/ams',
            "input/tex",
            "output/chtml",
        ],
    },
    tex: {
        packages: {
            '[+]': [
                'textmacros',
                'ams',
            ]
        },
        autoload: {
            color: [],
            colorv2: ['color']
        },
        inlineMath: [['$', '$'], ['~', '~']],
        displayMath: [['$$', '$$']],
    },
    svg: {
        fontCache: 'global'
    },
    processEscapes: true,
    processEnvironments: true,
    processRefs: true,
    digits: /^(?:[0-9]+(?:\{,\}[0-9]{3})*(?:\.[0-9]*)?|\.[0-9]+)/,
};
