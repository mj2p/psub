```
          _________    ___.    
  ______ /   _____/__ _\_ |__  
  \____ \\_____  \|  |  \ __ \ 
  |  |_> >        \  |  / \_\ \
  |   __/_______  /____/|___  /
  |__|          \/          \/
   
```
### CLI Subsonic Client

I was looking for a way to play music from my Subsonic server without needing a whole browser open and thought that a CLI tool might be fun.
After a quick search I didn't find what I was after so I decided to build something.  

pSub is intended to be very simple and focus just on playing music easily. Don't expect to be able to access advanced configuration of a Subsonic server or playlist management.
  
pSub is written in Python (written with 3.5 but 2.7 should work) using Click (the Command Line Interface Creation Kit) and requests to handle the communication with the Subsonic API.  

#### Installation
##### Dependencies
pSub uses [ffplay](https://ffmpeg.org/ffplay.html) to handle the streaming of music so that needs to be installed and available as a command line executable before using pSub. (you'll be prompted to download ffplay if pSub can't launch it correctly)
  
Python, pip and virtualenv also need to be installed
##### Instructions
(Tested on Ubuntu)
- Clone this repo  
`git clone github.com/inuitwallet/psub.git`
- Enter the pSub directory  
`cd psub`
- Create a virtualenv  
`virtualenv ve`
- Install pSub  
`pip install --editable .`
- Run pSub  
`ve/bin/pSub`  
