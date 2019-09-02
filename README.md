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
  
Python, pip and virtualenv also need to be installed

For compiling dependencies `gobject-introspection-1.0` is needed.
The package name varies by distribution:

* Fedora, CentOS, RHEL, etc.: gobject-introspection-devel
* Debian, Ubuntu, Mint, etc.: libgirepository1.0-dev
* Arch: gobject-introspection
* FreeBSD: gobject-introspection

##### Instructions
(Tested on Ubuntu, other operating systems may vary)
- Clone this repo  
`git clone github.com/inuitwallet/psub.git`
- Enter the pSub directory  
`cd psub`
- Create a virtualenv  
`virtualenv ve`  
or  
`python3 -m venv ve`  
- Install pSub  
`ve/bin/pip install .`
- Run pSub  
`ve/bin/pSub`  


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

Here are some animations of the commands in action:  
`psub album` (functions involving a search will accept `*` as a wildcard)   
![](https://github.com/inuitwallet/psub/blob/images/album.gif)  
`psub artist` (the `-r` flag indicates that tracks should be played back in a random order)  
![](https://github.com/inuitwallet/psub/blob/images/artist.gif)  
`psub playlist` (playlist must exist on the Subsonic server first)  
![](https://github.com/inuitwallet/psub/blob/images/playlist.gif)  
`psub radio`  
![](https://github.com/inuitwallet/psub/blob/images/radio.gif)  
`psub random`  
![](https://github.com/inuitwallet/psub/blob/images/random.gif)
