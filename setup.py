try:
    from setuptools import setup
except ImportError:
    from distutils.core import setup

config = {
        'description': 'Network devices scanner'
        'author': 'Yakov Shiryaev'
        'url': 'https://github.com/yman45/wwmode',
        'download_url': 'https://github.com/yman45/wwmode.git',
        'author_email': 'yman@protonmail.ch'
        'version': '0.1',
        'install_requires': [],
        'packages': ['utils', 'lexicon'],
        'scripts': ['wwmode.bin'],
        'name': 'WWmode'
        }
setup(**config)
