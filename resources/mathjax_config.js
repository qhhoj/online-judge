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
        },
    },
    options: {
        enableMenu: false,
    }
};
