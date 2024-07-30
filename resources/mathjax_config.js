window.MathJax = {
    loader: {
        load: [
            '[tex]/unicode',
        ]
    },
    tex: {
        inlineMath: [
            ['~', '~'],
            ['\\(', '\\)'],
            ['$', '$'],
        ],
        packages: {
            '[+]': ['unicode'],
            '[+]': ['textmacros'],
        },
    },
    options: {
        enableMenu: false,
    }
};
