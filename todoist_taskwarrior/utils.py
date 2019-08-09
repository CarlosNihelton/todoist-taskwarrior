import click
import re
import dateutil.parser
from .errors import UnsupportedRecurrence


""" Mappings """

def try_map(m, value):
    """Maps/translates `value` if it is present in `m`. """
    if value in m:
        return m[value]
    else:
        return value


def try_get_model_prop(m, key, default=None):
    """ The todoist models don't seem to have the `get()` method and throw KeyErrors """
    try:
        return m[key]
    except KeyError:
        return default


""" Priorities """

TI_PRIORITY_MAP = {1: None, 2: 'L', 3: 'M', 4: 'H'}

def ti_priority_to_tw(priority):
    """ Converts a priority from Todoist to Taskwarrior.

    Todoist saves priorities as 1, 2, 3, 4, whereas Taskwarrior uses L, M, H.
    These values map very easily to eachother, as Todoist priority 1 indicates that
    no priority has been set.
    """
    return TI_PRIORITY_MAP[int(priority)]

def tw_priority_to_ti(priority):
    tw_priority_map = dict(map(reversed, TI_PRIORITY_MAP.items()))

    return tw_priority_map[priority]

""" Strings """

def maybe_quote_ws(value):
    """Surrounds a value with single quotes if it contains whitespace. """
    if value is None:
        return value

    if any(x == ' ' or x == '\t' for x in value):
        return "'" + value + "'"
    return value


""" Dates """

def parse_due(due):
    """Parse a due date from the due object.

    e.g. {
        "date": "2016-12-0T12:00:00",
        "timezone": null,
        "string": "every day at 12",
        "lang": "en",
        "is_recurring": true
    }
    """
    if not due:
        return None

    return parse_date(due['date'])


def parse_date(date):
    """ Converts a date from Todoist to Taskwarrior.

    Todoist: Fri 26 Sep 2014 08:25:05 +0000 (what is this called)?
    taskwarrior: ISO-8601
    """
    if not date:
        return None
 
    naive = dateutil.parser.parse(date)
    dt = naive.replace(tzinfo=None)
    return dt.strftime('%Y%m%dT%H%M%SZ')


def parse_recur(due):
    """Given a due object, extracts the recur """
    if not due or not due['is_recurring']:
        return None
    return parse_recur_string(due['string'])


def parse_recur_string(date_string):
    """ Parses a Todoist `date_string` to extract a `recur` string for Taskwarrior.

    Field:
    - Todoist: date_string
    - taskwarrior: recur

    Examples:
    - every other `interval` `period` -> 2 `period`
    - every `interval` `period`       -> `interval` `period`
    - every `day of week`             -> weekly

    _Note_: just because Todoist sets `date_string` doesn't mean
    that the task is repeating. Mostly it just indicates that the
    user input via string and not date selector.
    """
    if not date_string:
        return
    # Normalize:
    # - trim leading, trailing, and, duplicate spaces
    # - convert to lowercase
    date_string = ' '.join(date_string.lower().strip().split())
    result = (
        _recur_single_cycle(date_string) or
        _recur_multi_cycle(date_string) or
        _recur_day_of_week(date_string) or
        _recur_day_of_month(date_string) or
        _recur_special(date_string)
    )
    if not result:
        raise UnsupportedRecurrence(date_string)
    return result


# Atoms
_PERIOD = r'(?P<period>hour|day|week|month|year)s?'
_EVERY = r'ev(ery)?'
_CYCLES = r'((?P<cycles>\d+)(st|nd|rd|th)?)'
_OTHER  = r'(?P<other>other)'
_SIMPLE = r'(?P<simple>daily|weekly|monthly|yearly)'
_DOW = (
    r'((?P<dayofweek>('
    r'mo(n(day)?)?'
    r'|tu(e(s(day)?)?)?'
    r'|we(d(s|(nes(day)?)?)?)?|th(u(rs(day)?)?)?'
    r'|fr(i(day)?)?'
    r'|sa(t(urday)?)?'
    r'|su(n(day)?)?'
    r')))'
)
_IGNORED = r'(\sat (\d{1,2}:\d{1,2})|(\d{1,2}(am|pm)))?'

# A single cycle recurrence is one of:
# - daily, weekly, monthly, yearly
# - every day, every week, every month, every year
# - every 1 day, every 1 week, every 1 month, every 1 year
RE_SINGLE_CYCLE = re.compile(
    fr'^(({_EVERY}\s(1\s)?{_PERIOD})|{_SIMPLE}){_IGNORED}$'
)

# A multi cycle recurrence is of the form: every N <period>s
RE_MULTI_CYCLE = re.compile(
    fr'^{_EVERY}\s({_CYCLES}|other)\s{_PERIOD}{_IGNORED}$'
)


# A day of week recurrence is of the form:
# - every (monday | tuesday | ...)
# - every Nth (monday | tuesday | ...)
RE_EVERY_DOW = re.compile(
    fr'^{_EVERY}\s(({_CYCLES}|{_OTHER})\s)?{_DOW}{_IGNORED}$'
)


# A day of month recurrence is of the form: every Nth
RE_EVERY_DOM = re.compile(
    fr'^{_EVERY}\s{_CYCLES}{_IGNORED}$'
)


# Other patterns that don't fit in with the others
RE_SPECIAL = re.compile(
    fr'^{_EVERY}\s(?P<label>morning|evening|weekday|workday|last\sday)$'
)


PERIOD_TO_SIMPLE = {
    'hour': 'hourly',
    'day': 'daily',
    'week': 'weekly',
    'month': 'monthly',
    'year': 'yearly',
}


def _recur_single_cycle(date_string):
    match = RE_SINGLE_CYCLE.match(date_string)
    if not match:
        return None

    groups = match.groupdict()
    if groups['simple']:
        return match.group('simple')

    period = match.group('period')
    return PERIOD_TO_SIMPLE[period]


def _recur_multi_cycle(date_string):
    match =  RE_MULTI_CYCLE.match(date_string)
    if not match:
        return

    groups = match.groupdict()
    period = groups['period']
    if groups['cycles']:
        cycles = groups['cycles']
    else:
        # 'other' matched
        cycles = 2

    return f'{cycles} {period}s'


def _recur_day_of_week(date_string):
    match =  RE_EVERY_DOW.match(date_string)
    if not match:
        return

    groups = match.groupdict()
    day_of_week = groups['dayofweek']

    if groups['cycles']:
        cycles = groups['cycles']
    elif groups['other']:
        cycles = 2
    else:
        cycles = 1

    return 'weekly' if cycles == 1 else f'{cycles} weeks'


def _recur_day_of_month(date_string):
    match =  RE_EVERY_DOM.match(date_string)
    if not match:
        return
    return 'monthly'


def _recur_special(date_string):
    match =  RE_SPECIAL.match(date_string)
    if not match:
        return

    label = match.group('label')
    if label == 'morning' or label == 'evening':
        return 'daily'
    elif label == 'weekday' or label == 'workday':
        return 'weekdays'
    elif label == 'last day':
        return 'monthly'

