from __future__ import absolute_import

from app.celery import celery
from redis import StrictRedis
from time import sleep
from json import dumps
from random import randint

r_server = StrictRedis(host='localhost')

@celery.task
def stall_time(user, job, time=5):
    for i in range(0,5):
        results = ['file%s.txt' % str(x) for x in range(0,randint(0,3))]
        jsoninfo = {
            'job': job,
            'msg': 'Task %s complete!' % str(i),
            'results': results
        }
        jsoninfo = dumps(jsoninfo)
        #need the rpush and publish for leaving page and if race condition
        r_server.rpush(user + ":messages", jsoninfo)
        r_server.publish(user, jsoninfo)
        sleep(time)
    jsoninfo = {
        'job': job,
        'msg': 'done',
        'results': []
    }
    jsoninfo = dumps(jsoninfo)
    r_server.rpush(user + ":messages", jsoninfo)
    r_server.publish(user, jsoninfo)
