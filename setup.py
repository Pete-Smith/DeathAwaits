import datetime

from setuptools import setup, find_packages

setup_args = {
    'name': "Death Awaits",
    'version': datetime.datetime.now().strftime("%Y-%m-%d"),
    'packages': find_packages(),
    'author': 'P.F. Smith',
    'author_email': 'pete at anagogical dot net',
    'install_requires': ['pyqt5', 'matplotlib', 'python-dateutil'],
    'tests_require': ['pytest'],
    'entry_points': {
        'gui_scripts': [
            'death_awaits = death_awaits.main:run'
        ]
    },
    'package_data': {
        'viewframes': ['icons/*'],
    },
}

setup(**setup_args)
