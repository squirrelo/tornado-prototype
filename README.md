tornado-prototype
=================

Showing implementation of a tornado-redis-celery setup with a login system, push notifications on celery jobs, and file uploads.

REQUIREMENTS
=================

Programs
> Python 2.7
> reddis-server

Python libraries
> tornado
> redis
> tornado-redis
> celery

RUNING THE EXAMPLE
=================
Start the background daemons for redis-server and celery
>For celery, run the following from the base folder: celery -A app worker

Start the webserver by running webserver.py

Navigate to localhost:8888 and create a user/pass to log in with. Everything else should be self explanatory.
