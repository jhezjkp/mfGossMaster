#GossMaster [![Build Status](https://secure.travis-ci.org/jhezjkp/mfGossMaster.png)](http://travis-ci.org/jhezjkp/mfGossMaster) [![endorse](http://api.coderwall.com/jhezjkp/endorsecount.png)](http://coderwall.com/jhezjkp)

Goss Master is the master part of the Goss(Game Operation Support System), which enables people manage their game servers easier.

#Features

+ start/stop game apps
+ update game apps(multi apps which distributed on multi physical servers update is supported)
+ update game scripts(multi scripts which distributed on multi physical servers update is supported)
+ game server console view support
+ view multi game server consoles is supported, which is called console wall
+ configurations switch
+ database backup
+ agents status view support

#Screenshots

![Index Page](https://raw.githubusercontent.com/jhezjkp/mfGossMaster/master/screenshot/index.png)
![Agent status](https://raw.githubusercontent.com/jhezjkp/mfGossMaster/master/screenshot/agentStatus.png)
![Console log realtime monit](https://raw.githubusercontent.com/jhezjkp/mfGossMaster/master/screenshot/consoleWall.png)


#Get started

You should have [virtualenv](http://www.virtualenv.org "virtualenv") and [virtualenvwrapper](http://virtualenvwrapper.readthedocs.org/en/latest/index.html "virtualenvwrapper") installed on your system before you start.

    $ git clone git://github.com/jhezjkp/mfGossMaster.git
    $ cd mfGossMaster
    $ mkvirtualenv mfGossMaster
    $ pip install -r requirements.txt
    $ sh start.sh

