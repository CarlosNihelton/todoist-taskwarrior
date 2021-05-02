
import click
import os
import sys
import datetime
import dateutil.parser
import io

import yaml

from tasklib import TaskWarrior

bad_id = 4775090814
another = 4600832030
third = 4600832030
oneMore = 4596606350
shouldWork = 4169764276
id = 4589599856

tw = TaskWarrior('~/.task')

task = tw.tasks.filter(todoist_id=bad_id)

print('\t', task)

tasks = tw.tasks.pending()

print(tasks[0])
