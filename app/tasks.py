from __future__ import absolute_import

from app.celery import celery
from redis import StrictRedis
from time import sleep

r_server = StrictRedis(host='localhost')

@celery.task
def stall_time(user, job, time=5):
    for i in range(0,5):
        msg = '%s:Task %s complete!' % (job, str(i))
        #the two prints not needed in normal use, just for demoing
        print msg
        #need the rpush and publish for leaving page and if race condition
        r_server.rpush(user + ":messages", msg)
        r_server.publish(user, msg)
        sleep(time)
    print 'done'
    r_server.publish(user, 'done:' + job)
    r_server.rpush(user + ":messages", 'done:' + job)
