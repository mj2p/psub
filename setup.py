from setuptools import setup

setup(
    name='pSub',
    version='0.1',
    py_modules=['pSub'],
    install_requires=[
        'click',
        'colorama',
        'pyyaml',
        'requests[security]',
        'packaging',
    ],
    entry_points='''
        [console_scripts]
        pSub=pSub:cli
    ''',
)
