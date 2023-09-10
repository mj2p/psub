from setuptools import find_packages, setup

setup(
    name="pSub",
    version="0.2.1",
    packages=find_packages(),
    install_requires=[
        "rich_click",
        "colorama",
        "pyyaml",
        "packaging",
        "requests[security]",
        "questionary",
        "pygobject",
        "pycairo",
        "py-notifier",
        "python-mpv==v0.4.0",
        "python-vlc",
        "wurlitzer",
    ],
    entry_points={
        "console_scripts": ["psub = cli.psub:psub"],
    },
)
