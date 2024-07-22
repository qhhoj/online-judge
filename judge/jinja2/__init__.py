import itertools
import json
from urllib.parse import quote

from jinja2.ext import Extension
from mptt.utils import get_cached_trees
from statici18n.templatetags.statici18n import inlinei18n

from judge.highlight_code import highlight_code
from judge.user_translations import gettext

from django.utils.safestring import mark_safe
from . import (camo, datetime, filesize, format, gravatar, language, markdown, rating, reference, render, social,
               spaceless, submission, timedelta)
from . import registry

registry.function('str', str)
registry.filter('str', str)
registry.filter('json', json.dumps)
registry.filter('highlight', highlight_code)
registry.filter('urlquote', quote)
registry.filter('roundfloat', round)
registry.function('ordinal', lambda n: '%d%s' % (n, 'tsnrhtdd'[(n // 10 % 10 != 1) * (n % 10 < 4) * n % 10::4]))
registry.function('inlinei18n', inlinei18n)
registry.function('mptt_tree', get_cached_trees)
registry.function('user_trans', gettext)


@registry.function
def counter(start=1):
    return itertools.count(start).__next__


@registry.function
def render_input(field, attrs):
    form_input = field.as_widget(attrs=attrs)

    help_text = ''
    if field.help_text:
        help_text = f"""
                <br>
                <span class="help-text text-sm text-stone-500 border-b">
                    <i class="fa-solid fa-circle-info fa-fw" aria-hidden="true"></i>
                    {field.help_text}
                </span>
                """

    return mark_safe(f"""
        <tr class="mb-4">
            <th style="max-width: 10em; width: 10em">
                <label for="{field.auto_id}" class="text-base font-bold text-gray-900 {'need' if field.field.required else ''}">{field.label}:</label>
            </th>
            <td class="pl-5">
                {form_input}
                {help_text}
            </td>
        </tr>
    """)


@registry.function
def render_text_input(field):
    attrs = {
        'class': 'bg-gray-50 border border-gray-300 text-gray-900 rounded-lg focus:ring-primary-600 focus:border-primary-600 w-2/5 p-2.5',
    }

    return render_input(field, attrs)


@registry.function
def render_checkbox_input(field):
    attrs = {
        'class': 'w-4 h-4 text-primary bg-gray-100 border-gray-300 rounded focus:ring-blue-500 focus:ring-2',
    }

    return render_input(field, attrs)


@registry.function
def render_file_input(field):
    attrs = {
        'class': 'w-2/5 text-sm text-gray-900 border border-gray-300 rounded-lg cursor-pointer bg-gray-50 focus:outline-none',
    }

    return render_input(field, attrs)


class DMOJExtension(Extension):
    def __init__(self, env):
        super(DMOJExtension, self).__init__(env)
        env.globals.update(registry.globals)
        env.filters.update(registry.filters)
        env.tests.update(registry.tests)
