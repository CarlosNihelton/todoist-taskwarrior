# -*- coding: utf-8 -*-

from setuptools import find_packages
from setuptools import setup


setup(
    name='todoist_taskwarrior',
    version='0.1.0.dev0',
    description="Todoist <-> Taskwarrior two-way sync",
    classifiers=[
        "Programming Language :: Python",
        "Programming Language :: Python :: 3.5",
        "Programming Language :: Python :: 3.6",
        "Programming Language :: Python :: 3.7",
    ],
    keywords='Todoist Taskwarrior',
    author='René Jochum',
    author_email='rene@webmeisterei.com',
    url='https://git.webmeisterei.com/webmeisterei/todoist-taskwarrior',
    license='MIT',
    packages=find_packages('.', exclude=['ez_setup']),
    package_dir={'': '.'},
    include_package_data=True,
    zip_safe=True,
    install_requires=[
        'setuptools',
        'Click',
        'todoist-python',
        'taskw',
    ],
    entry_points={
        'console_scripts': [
            'titwsync=todoist_taskwarrior.cli:cli'
        ],
    }
)
