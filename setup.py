try:
    from setuptools import setup
except ImportError:
    from distutils.core import setup

config = {
        'description': 'Collector of network devices states'
        'author': 'Yakov Shiryaev'
        'url': 'URL to get it at.',
        'download_url': 'Where to download it.',
        'author_email': 'yman@protonmail.ch'
        'version': '0.1',
        'install_requires': [],
        'packages': ['utils'],
        'scripts': [],
        'name': 'WWmode'
        }
setup(**config)
