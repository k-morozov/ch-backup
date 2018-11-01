"""
Utility functions.
"""

import collections
import logging
import re
import string
from functools import wraps
from random import choice as random_choise
from types import SimpleNamespace


def merge(original, update):
    """
    Recursively merge update dict into original.
    """
    for key in update:
        recurse_conditions = [
            key in original,
            isinstance(original.get(key), dict),
            isinstance(update.get(key), collections.Mapping),
        ]
        if all(recurse_conditions):
            merge(original[key], update[key])
        else:
            original[key] = update[key]
    return original


def format_object(obj, **replacements):
    """
    Replace format placeholders with actual values
    """
    if isinstance(obj, str):
        obj = obj.format(**replacements)
    elif isinstance(obj, collections.Mapping):
        for key, value in obj.items():
            obj[key] = format_object(value, **replacements)
    elif isinstance(obj, collections.Iterable):
        for idx, val in enumerate(obj):
            obj[idx] = format_object(val, **replacements)
    return obj


def env_stage(event, fail=False):
    """
    Nicely logs env stage.
    """

    def wrapper(fun):
        @wraps(fun)
        def _wrapped_fun(*args, **kwargs):
            stage_name = '{0}.{1}'.format(fun.__module__, fun.__name__)
            logging.info('initiating %s stage %s', event, stage_name)
            try:
                return fun(*args, **kwargs)
            except Exception as e:
                logging.error('%s failed: %s', stage_name, e)
                if fail:
                    raise

        return _wrapped_fun

    return wrapper


def strip_query(query_text):
    """
    Remove query without newlines and duplicate whitespaces.
    """
    return re.sub(r'\s{2,}', ' ', query_text.replace('\n', ' ')).strip()


def generate_random_string(length=64):
    """
    Generate random alphanum sequence.
    """
    return ''.join(
        random_choise(string.ascii_letters + string.digits)
        for _ in range(length))


def context_to_dict(context):
    """
    Convert context to dict representation.

    The context type can be either types.SimpleNamespace or behave.Context.
    """
    if isinstance(context, SimpleNamespace):
        return context.__dict__

    result = {}
    for frame in context._stack:  # pylint: disable=protected-access
        for key, value in frame.items():
            if key not in result:
                result[key] = value

    return result