from __future__ import absolute_import

from app.celery import celery
from redis import StrictRedis
from time import sleep

r_server = StrictRedis(host='localhost')

@celery.task
def stall_time(channel, time=5):
    for i in range(0,5):
        msg = 'Task %s complete!' % i
        #the two prints not needed in normal use, just for demoing
        print msg
        r_server.rpush(channel, msg)
        r_server.publish(channel, msg)
        sleep(time)
    print 'done'
    r_server.publish(channel, 'done')
    r_server.rpush(channel, 'done')
    #expire, not delete, so if task finishes before page load 
    #it will still get done signal
    r_server.expire(channel, 5)
