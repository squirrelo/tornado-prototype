tornado-prototype
=================

Showing implementation of a tornado-redis-celery setup with a login system, push notifications on celery jobs, and file uploads.

REQUIREMENTS
=================

Programs
> Python 2.7
>
> redis-server
>
>postgreSQL

Python libraries
> tornado
>
> redis
>
> tornado-redis
>
> celery
>
>psycopg2

RUNING THE EXAMPLE
=================
Start the background daemons for redis-server, postgreSQL, and celery
>For celery, run the following from the base folder: celery -A app worker

For the postgres database setup, do the following:
>1) Make a database called 'qiita' and user 'defaultuser' with password 'defaultpassword'
>
>2) Add the following table:
>
>CREATE TABLE completed_jobs (
>    id bigserial PRIMARY KEY,
>    username text NOT NULL,
>    job text NOT NULL,
>    msg text NOT NULL,
>    files text[],
>    date_added timestamp default NULL
>);

Start the webserver by running webserver.py

Navigate to localhost:8888 and create a user/pass to log in with. Everything else should be self explanatory.

KNOWN ISSUES
=================
Websockets issue with Safari in non-localhost setting.
