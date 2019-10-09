import click
import os
import sys
import datetime
import dateutil.parser
import io

import yaml
from taskw import TaskWarrior
from todoist.api import TodoistAPI
from . import errors, log, utils, validation

# This is the location where the todoist
# data will be cached.
TODOIST_CACHE = '~/.todoist-sync/'
TITWSYNCRC = '~/.titwsyncrc.yaml'


config = None
todoist = None
taskwarrior = None

""" CLI Commands """


@click.group()
def cli():
    """Two-way sync of Todoist and Taskwarrior. """
    global config, todoist, taskwarrior

    is_help_cmd = '-h' in sys.argv or '--help' in sys.argv
    rcfile = os.path.expanduser(TITWSYNCRC)

    if os.path.exists(rcfile):
        with open(rcfile, 'r') as stream:
            config = yaml.safe_load(stream)

        if 'todoist' not in config or 'api_key' not in config['todoist'] \
                and not is_help_cmd:
            log.error('Run configure first. Exiting.')
            exit(1)

        todoist = TodoistAPI(config['todoist']['api_key'], cache=TODOIST_CACHE)

        # Create the TaskWarrior client, overriding config to
        # create a `todoist_id` field which we'll use to
        # prevent duplicates
        taskwarrior = TaskWarrior(config_overrides={
            'uda.todoist_id.type': 'string',
            'uda.todoist_sync.type': 'date',
        })


@cli.command()
@click.option('-p', '--map-project', metavar='SRC=DST', multiple=True,
              callback=validation.validate_map,
              help='Project names specified will be translated '
              'from SRC to DST. '
              'If DST is omitted, the project will be unset when SRC matches.')
@click.option('-t', '--map-tag', metavar='SRC=DST', multiple=True,
              callback=validation.validate_map,
              help='Tags specified will be translated from SRC to DST. '
              'If DST is omitted, the tag will be removed when SRC matches.')
@click.argument('todoist_api_key')
def configure(map_project, map_tag, todoist_api_key):
    """Configure sync.

    Use --map-project to change or remove the project. Project hierarchies will
    be period-delimited during conversion. For example in the following,
    'Work Errands' and 'House Errands' will be both be changed to 'errands',
    'Programming.Open Source' will be changed to 'oss', and the project will be
    removed when it is 'Taxes':
    \r
    --map-project 'Work Errands'=errands
    --map-project 'House Errands'=errands
    --map-project 'Programming.Open Source'=oss
    --map-project Taxes=
    """
    data = {'todoist': {'api_key': todoist_api_key}, 'taskwarrior': {}}
    data['todoist']['project_map'] = map_project
    data['todoist']['tag_map'] = map_tag
    data['taskwarrior']['project_sync'] = {
        k: True for k in map_project.values()}

    rcfile = os.path.expanduser(TITWSYNCRC)
    with io.open(rcfile, 'w', encoding='utf8') as outfile:
        yaml.dump(data, outfile, default_flow_style=False, allow_unicode=True)


@cli.command()
def synchronize():
    """Update the local Todoist task cache.

    This command accesses Todoist via the API and updates a local
    cache before exiting. This can be useful to pre-load the tasks,
    and means `migrate` can be run without a network connection.

    NOTE - the local Todoist data cache is usually located at:

        ~/.todoist-sync
    """
    with log.with_feedback('Syncing tasks with todoist'):
        todoist.sync()


@cli.command()
@click.confirmation_option(
    prompt=f'Are you sure you want to delete {TODOIST_CACHE}?')
def clean():
    """Remove the data stored in the Todoist task cache.

    NOTE - the local Todoist data cache is usually located at:

        ~/.todoist-sync
    """
    cache_dir = os.path.expanduser(TODOIST_CACHE)

    # Delete all files in directory
    for file_entry in os.scandir(cache_dir):
        with log.with_feedback(f'Removing file {file_entry.path}'):
            os.remove(file_entry)

    # Delete directory
    with log.with_feedback(f'Removing directory {cache_dir}'):
        os.rmdir(cache_dir)


@cli.command()
@click.pass_context
def sync(ctx):
    """Sync tasks between Todoist and Taskwarrior.

    This command can be run multiple times and will not duplicate tasks.
    This is tracked in Taskwarrior by setting and detecting the
    `todoist_id` property on the task.
    """

    # Sync todoist to cache
    ctx.invoke(synchronize)

    ti_project_list = _ti_project_list()
    default_project = utils.try_map(config['todoist']['project_map'], 'Inbox')

    config_ps = config['taskwarrior']['project_sync']

    # Sync Taskwarrior->Todoist
    tw_tasks = taskwarrior.load_tasks()
    log.important(f'Starting to sync tasks from Taskwarrior...')
    for tw_task in tw_tasks['pending']:
        if 'project' not in tw_task:
            tw_task['project'] = default_project

        desc = tw_task['description']
        project = tw_task['project']

        if (tw_task['project'] not in config_ps or
                not config_ps[tw_task['project']]):
            log.warn(f'Ignoring Task {desc} ({project})')
            continue

        # Log message
        log.important(f'Sync Task {desc} ({project})')

        if 'todoist_id' in tw_task:
            ti_task = todoist.items.get_by_id(tw_task['todoist_id'])
            if ti_task is None:
                # Ti task has been deleted
                taskwarrior.task_delete(uuid=tw_task['uuid'])
                continue

            ti_task = ti_task['item']
            c_ti_task = _convert_ti_task(ti_task, ti_project_list)

            # Sync Todoist with Taskwarrior task
            _sync_task(tw_task, c_ti_task, ti_project_list)
            continue

        # Add Todoist task
        _ti_add_task(tw_task, ti_project_list)

    with log.with_feedback('Syncing tasks with todoist'):
        todoist.commit()
        todoist.sync()

    # Sync Todoist->Taskwarrior
    tasks = todoist.items.all()
    log.important(f'Starting sync of {len(tasks)} tasks from Todoist...')
    for idx, ti_task in enumerate(tasks):
        c_ti_task = _convert_ti_task(ti_task, ti_project_list)

        desc = c_ti_task['description']
        project = c_ti_task['project']

        if (c_ti_task['project'] not in config_ps or
                not config_ps[c_ti_task['project']]):
            log.warn(f'Ignoring Task {desc} ({project})')
            continue

        # Log message
        log.important(f'Sync Task {desc} ({project})')

        # Sync Todoist with Taskwarrior task
        _, tw_task = taskwarrior.get_task(todoist_id=ti_task['id'])
        if bool(tw_task):
            if 'project' not in tw_task:
                tw_task['project'] = default_project
            _sync_task(tw_task, c_ti_task, ti_project_list)
            continue

        # Add Taskwarrior task
        _tw_add_task(c_ti_task)

    with log.with_feedback('Syncing tasks with todoist'):
        todoist.commit()
        todoist.sync()


def _convert_ti_task(ti_task, ti_project_list):
    data = {}
    data['tid'] = ti_task['id']
    data['description'] = ti_task['content']

    # Project
    project_name = ''
    for project_name, p in ti_project_list.items():
        if p['id'] == ti_task['project_id']:
            break

    data['project'] = project_name

    # Priority
    data['priority'] = utils.ti_priority_to_tw(ti_task['priority'])

    # Tags
    data['tags'] = [
        utils.try_map(config['todoist']['tag_map'],
                      todoist.labels.get_by_id(l_id)['name'])
        for l_id in ti_task['labels']
    ]

    # Dates
    data['entry'] = utils.parse_date(ti_task['date_added'])
    data['due'] = utils.parse_due(utils.try_get_model_prop(ti_task, 'due'))
    data['recur'] = parse_recur_or_prompt(
        utils.try_get_model_prop(ti_task, 'due'))

    data['status'] = 'completed' if ti_task['checked'] == 1 else 'pending'

    return data


def _sync_task(tw_task, ti_task, ti_project_list):
    if 'todoist_sync' in tw_task:
        ti_stamp = dateutil.parser.parse(tw_task['todoist_sync']).timestamp()
        tw_stamp = dateutil.parser.parse(tw_task['modified']).timestamp()

        if tw_stamp > ti_stamp:
            _ti_update_task(tw_task, ti_project_list)
        else:
            _tw_update_task(tw_task, ti_task)
    else:
        _tw_update_task(tw_task, ti_task)


def _tw_add_task(ti_task):
    """Add a taskwarrior task from todoist task

    Returns the taskwarrior task.
    """
    description = ti_task['description']
    project = ti_task['project']
    with log.with_feedback(f"Taskwarrior add '{description}' ({project})"):
        return taskwarrior.task_add(
            ti_task['description'],
            project=ti_task['project'],
            tags=ti_task['tags'],
            priority=ti_task['priority'],
            entry=ti_task['entry'],
            due=ti_task['due'],
            recur=ti_task['recur'],
            status=ti_task['status'],
            todoist_id=ti_task['tid'],
            todoist_sync=datetime.datetime.now(),
        )


def _tw_update_task(tw_task, ti_task):

    def _compare_value(item):
        return ((ti_task[item] and item not in tw_task) or
                (item in tw_task and tw_task[item] != ti_task[item]))

    description = ti_task['description']
    project = ti_task['project']
    with log.on_error(f"TW updating '{description}' ({project})"):
        changed = False

        if tw_task['description'] != ti_task['description']:
            tw_task['description'] = ti_task['description']
            changed = True

        if tw_task['project'] != ti_task['project']:
            tw_task['project'] = ti_task['project']
            changed = True

        if _compare_value('tags'):
            tw_task['tags'] = ti_task['tags']
            changed = True

        if _compare_value('priority'):
            tw_task['priority'] = ti_task['priority']
            changed = True

        if _compare_value('entry'):
            tw_task['entry'] = ti_task['entry']
            changed = True

        if _compare_value('due'):
            tw_task['due'] = ti_task['due']
            changed = True

        if _compare_value('recur'):
            tw_task['recur'] = ti_task['recur']
            changed = True

        if tw_task['status'] != ti_task['status']:
            tw_task['status'] = ti_task['status']
            changed = True

        if changed:
            tid = ti_task['tid']
            log.info(f'TW updating (todoist_id={tid})...', nl=False)
            log.success('OK')

            tw_task['todoist_sync'] = datetime.datetime.now()
            taskwarrior.task_update(tw_task)


def _ti_update_task(tw_task, ti_project_list):
    description = tw_task['description']
    project = tw_task['project']
    with log.on_error(f"Todoist update '{description}' ({project})"):
        changed = False

        ti_task = todoist.items.get_by_id(tw_task['todoist_id'])

        if tw_task['description'] != ti_task['item']['content']:
            ti_task['item']['content'] = tw_task['description']
            changed = True

        project = ti_project_list[tw_task['project']]
        if ti_task['item']['project_id'] != project['id']:
            changed = True

        priority = 0
        if 'priority' in tw_task:
            priority = utils.tw_priority_to_ti(tw_task['priority'])
        if ti_task['item']['priority'] != priority:
            ti_task['item']['priority'] = priority
            changed = True

        if ((ti_task['item']['checked'] == 0 and
                tw_task['status'] == 'completed') or
                (ti_task['item']['checked'] == 1 and
                 tw_task['status'] == 'pending')):
            changed = True

        if changed:
            tid = ti_task['item']['id']

            log.info(f'Updating (todoist_id={tid})', nl=False)
            log.success('OK')

            todoist.items.update(tid, **ti_task)

            # Move to another project
            if ti_task['item']['project_id'] != project['id']:
                todoist.items.move(tid, project_id=project['id'])

            # Open/close ti task
            if ti_task['item']['checked'] == 1 and \
                    tw_task['status'] == 'pending':
                todoist.items.uncomplete(tid)
            elif ti_task['item']['checked'] == 0 and \
                    tw_task['status'] == 'completed':
                todoist.items.complete(tid)
            elif tw_task['status'] == 'waiting':
                # taskwarrior doesn't like status=waiting
                del(tw_task['status'])

            tw_task['todoist_sync'] = datetime.datetime.now().isoformat()
            taskwarrior.task_update(tw_task)
        else:
            # Always set latest sync time so no more sync accures
            tid = ti_task['item']['id']
            log.info(f'TI updating (todoist_id={tid})...', nl=False)
            log.success('OK')

            # taskwarrior doesn't like status=waiting
            if tw_task['status'] == 'waiting':
                del(tw_task['status'])

            tw_task['todoist_sync'] = datetime.datetime.now().isoformat()
            taskwarrior.task_update(tw_task)


def _ti_add_task(tw_task, ti_project_list):
    description = tw_task['description']
    project = tw_task['project']
    with log.on_error(f"Todoist add '{description}' ({project})"):
        # Add the item and commit the change
        data = {}

        if tw_task['project'] not in ti_project_list:
            project = tw_task['project']
            log.error(f'Project "{project}" not found on Todoist.')
            return

        data['project_id'] = ti_project_list[tw_task['project']]['id']
        if 'priority' in tw_task:
            data['priority'] = utils.tw_priority_to_ti(tw_task['priority'])

        ti_task = todoist.items.add(tw_task['description'], **data)
        todoist.commit()

        tid = ti_task['id']
        log.info(f'TI add (todoist_id={tid})')

        tw_task['todoist_id'] = tid
        tw_task['todoist_sync'] = datetime.datetime.now()
        taskwarrior.task_update(tw_task)


def _ti_project_list():
    result = {}
    for p in todoist.projects.all():
        project_hierarchy = [p]
        pp = p
        while pp['parent_id']:
            pp = todoist.projects.get_by_id(p['parent_id'])
            project_hierarchy.insert(0, pp)

        project_name = '.'.join(p['name'] for p in project_hierarchy)
        project_name = utils.try_map(
            config['todoist']['project_map'],
            project_name
        )
        result[utils.maybe_quote_ws(project_name)] = p

    return result


def parse_recur_or_prompt(due):
    try:
        return utils.parse_recur(due)
    except errors.UnsupportedRecurrence:
        log.error(
            "Unsupported recurrence: '%s'. "
            "Please enter a valid value" % due['string'])
        return log.prompt(
            'Set recurrence (todoist style)',
            default='',
            value_proc=validation.validate_recur,
        )


""" Entrypoint """

if __name__ == '__main__':
    cli()
