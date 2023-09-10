```
          _________    ___.
  ______ /   _____/__ _\_ |__
  \____ \\_____  \|  |  \ __ \
  |  |_> >        \  |  / \_\ \
  |   __/_______  /____/|___  /
  |__|          \/          \/

```
## CLI Subsonic Client

I was looking for a way to play music from my [Subsonic](https://subsonic.org) server without needing a whole browser open and thought that a CLI tool might be fun.
After a quick search I didn't find what I was after so I decided to build something.

pSub is intended to be very simple and focus just on playing music easily. Don't expect to be able to access advanced configuration of a Subsonic server or playlist management.

pSub is written in Python (written with 3.5 but 2.7 should work) using [Click](http://click.pocoo.org/6/)  to build the CLI and [Requests](http://docs.python-requests.org) to handle the communication with the Subsonic API.
It should run on most operating systems too but this hasn't been tested.


#### Installation
##### Dependencies
pSub uses [ffplay](https://ffmpeg.org/ffplay.html) to handle the streaming of music so that needs to be installed and available as a command line executable before using pSub. (you'll be prompted to download ffplay if pSub can't launch it correctly)

Python3.8 and pipenv need to be installed

For compiling, some additional dependencies are required (install them with your system package manager; atpt, yum, pacman etc.):
The package names vary by distribution:

* Fedora, CentOS, RHEL, etc.: gobject-introspection-devel cairo-devel pkg-config python3-devel
* Debian, Ubuntu, Mint, etc.: libgirepository1.0-dev libcairo2-dev pkg-config python3-dev
* Arch: gobject-introspection cairo pkgconf

The dependencies are [PyGObject](https://pygobject.readthedocs.io/) and [Pycairo](https://pycairo.readthedocs.io/).
See their websites for more info if the instruction above are out of date.


##### Instructions
- Clone this repo
`git clone github.com/inuitwallet/psub.git`
- Enter the pSub directory
`cd psub`
- Sync the dependencies
`pipenv sync`
- Link the psub binary to `/usr/bin` to allow for running pSub from any other directory
`sudo ln -sf $(pipenv --venv)/bin/pSub /usr/bin/psub`
- Run pSub
`psub`

#### Usage
On first run you will be prompted to edit your config file. pSub will install a default config file and then open it for editing in your default text editor. You need to specify the url, username and password of your Subsonic server at a minimum.
There are also some settings for adjusting your playback options. The settings are all described in detail in the config file itself.
pSub will run a connection test once your config been saved to make sure it can communicate correctly with Subsonic.
You can edit your config or run the connection test at any time with the -c and -t command line flags.

Once pSub is properly configured, you can start playing music by running any of the commands shown below.
```
Usage: pSub [OPTIONS] COMMAND [ARGS]...

Options:
  -c, --config  Edit the config file
  -t, --test    Test the server configuration
  -h, --help    Show this message and exit.

Commands:
  album     Play songs from chosen Album
  artist    Play songs from chosen Artist
  playlist  Play a chosen playlist
  radio     Play endless Radio based on a search
  random    Play random tracks
```
