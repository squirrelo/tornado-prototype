from __future__ import absolute_import

from app.celery import celery
from celery import signature, group, task
from redis import StrictRedis
from time import sleep
from json import dumps
from random import randint

r_server = StrictRedis(host='localhost')

def push_notification(user, job, analysis, msg, files=[], done=False):
    '''Creates JSON and takes care of push notification'''
    jsoninfo = {
        'job': job,
        'analysis': analysis,
        'msg': msg,
        'results': files,
    }
    if done:
        jsoninfo['done'] = 1
    else:
        jsoninfo['done'] = 0
    jsoninfo = dumps(jsoninfo)
    #need the rpush and publish for leaving page and if race condition
    r_server.rpush(user + ":messages", jsoninfo)
    r_server.publish(user, jsoninfo)


@celery.task
def switchboard(user, jobname, analyses):
    '''Fires off all analyses for a given job.

    INPUTS:
        user: username of user requesting job
        jobname: jobname for this set of analyses
        analyses: dictionary of jobs, with keys formatted as "datatype:analysis"
                and values as dictionary formatted {option: value}

    OUTPUT: NONE '''
    analgroup = []
    for a in analyses:
        analysisinfo = a.split(':')
        analysis = analysisinfo[1]
        datatype = analysisinfo[0]
        s = signature('app.tasks.'+analysis, args=(user, jobname, datatype, analyses[a]))
        analgroup.append(s)
    print analgroup
    job = group(analgroup)
    result = job.apply_async()


@celery.task
def Alpha_Diversity(user, jobname, datatype, opts):
    print datatype, "ALPHA_DIV"
    push_notification(user, jobname, datatype + ':Alpha_Diversity', 'Running')
    #try:
    sleep(20)
    results = ['file%s.txt' % str(x) for x in range(0,randint(0,3))]
    push_notification(user, jobname, datatype + ':Alpha_Diversity', 'Done',
        results, done=True)
    #except Exception, e:
    #    push_notification(user, jobname, datatype + ':Alpha_Diversity',
    #        'ERROR: ' + e, results, done=True)

@celery.task
def OTU_Table(user, jobname, datatype, opts):
    print datatype, "OTU_TABLE"
    push_notification(user, jobname, datatype + ':OTU_Table', 'Running')
    #try:
    sleep(5)
    results = ['file%s.txt' % str(x) for x in range(0,randint(0,3))]
    push_notification(user, jobname, datatype + ':OTU_Table', 'Done',
        results, done=True)
    #except Exception, e:
    #    push_notification(user, jobname, datatype + ':OTU_Table',
    #        'ERROR: ' + e, results, done=True)
