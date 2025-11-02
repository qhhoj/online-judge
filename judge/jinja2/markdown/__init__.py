import logging
import re

import markdown2
from bleach.css_sanitizer import CSSSanitizer
from bleach.sanitizer import Cleaner
from django.conf import settings
from lxml import html
from lxml.etree import (
    ParserError,
    XMLSyntaxError,
)
from markupsafe import Markup

from .bleach_whitelist import (
    all_styles,
    mathml_attrs,
    mathml_tags,
)
from .. import registry

from judge.jinja2.markdown.lazy_load import lazy_load as lazy_load_processor  # noqa: I100,I202
from judge.utils.camo import client as camo_client


logger = logging.getLogger('judge.html')

NOFOLLOW_WHITELIST = settings.NOFOLLOW_EXCLUDED


cleaner_cache = {}


def get_cleaner(name, params):
    if name in cleaner_cache:
        return cleaner_cache[name]

    styles = params.pop('styles', None)
    if styles:
        params['css_sanitizer'] = CSSSanitizer(allowed_css_properties=all_styles if styles is True else styles)

    if params.pop('mathml', False):
        params['tags'] = params.get('tags', []) + mathml_tags
        params['attributes'] = params.get('attributes', {}).copy()
        params['attributes'].update(mathml_attrs)

    cleaner = cleaner_cache[name] = Cleaner(**params)
    return cleaner


def fragments_to_tree(fragment):
    tree = html.Element('div')
    try:
        parsed = html.fragments_fromstring(fragment, parser=html.HTMLParser(recover=True))
    except (XMLSyntaxError, ParserError) as e:
        if fragment and (not isinstance(e, ParserError) or e.args[0] != 'Document is empty'):
            logger.exception('Failed to parse HTML string')
        return tree

    if parsed and isinstance(parsed[0], str):
        tree.text = parsed[0]
        parsed = parsed[1:]
    tree.extend(parsed)
    return tree


def strip_paragraphs_tags(tree):
    for p in tree.xpath('.//p'):
        for child in p.iterchildren(reversed=True):
            p.addnext(child)
        parent = p.getparent()
        prev = p.getprevious()
        if prev is not None:
            prev.tail = (prev.tail or '') + p.text
        else:
            parent.text = (parent.text or '') + p.text
        parent.remove(p)


def fragment_tree_to_str(tree):
    return html.tostring(tree, encoding='unicode')[len('<div>'):-len('</div>')]


def inc_header(text, level):
    pattern = re.compile(
        r'<(\/?)h([1-9][0-9]*)>',
        re.X | re.M,
    )
    return re.sub(pattern, lambda x: '<' + x.group(1) + 'h' + str(int(x.group(2)) + level) + '>', text)


def add_table_class(text):
    return text.replace(r'<table>', r'<div class="h-scrollable-table"><table class="table">')


def end_table_class(text):
    return text.replace(r'</table>', r'</table></div>')


def replace_latex_with_placeholder(text):
    latex_placeholder = '<latex>{}</latex>'
    placeholders = []

    def replace_match(match):
        placeholders.append(match.group(0))
        return latex_placeholder.format(len(placeholders) - 1)

    text = re.sub(r'(\$\$.*?\$\$|\$.*?\$|~.*?~)', replace_match, text)

    return text, placeholders


def replace_placeholder_with_latex(html, placeholders):
    for i, latex in enumerate(placeholders):
        html = html.replace(f'<latex>{i}</latex>', latex)
    return html


@registry.filter
def markdown(text, style, math_engine=None, lazy_load=False, strip_paragraphs=False):
    styles = settings.MARKDOWN_STYLES.get(style, settings.MARKDOWN_DEFAULT_STYLE)
    if styles.get('safe_mode', True):
        safe_mode = 'escape'
    else:
        safe_mode = None

    extras = [
        'spoiler',
        'fenced-code-blocks',
        'cuddled-lists',
        'tables',
        'strike',
        'smarty-pants',
        'wikilinks',
        'target-blank',
    ]
    if styles.get('nofollow', True):
        extras.append('nofollow')

    bleach_params = styles.get('bleach', {})

    post_processors = []
    if styles.get('use_camo', False) and camo_client is not None:
        post_processors.append(camo_client.update_tree)
    if lazy_load:
        post_processors.append(lazy_load_processor)

    text, placeholders = replace_latex_with_placeholder(text)

    result = markdown2.markdown(text, safe_mode=safe_mode, extras=extras)

    result = replace_placeholder_with_latex(result, placeholders)
    result = add_table_class(result)
    result = end_table_class(result)
    result = inc_header(result, 2)

    if post_processors or strip_paragraphs:
        tree = fragments_to_tree(result)
        for processor in post_processors:
            processor(tree)
        if strip_paragraphs:
            strip_paragraphs_tags(tree)
        result = fragment_tree_to_str(tree)
    if bleach_params:
        result = get_cleaner(style, bleach_params).clean(result)
    return Markup(result)
