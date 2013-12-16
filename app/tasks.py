from __future__ import absolute_import

from app.celery import celery
from celery import signature, group
from time import sleep
from json import dumps
from random import randint
from app.database_connections import r_server, postgres
from psycopg2.extras import DictCursor


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


def finish_job(user, jobname, jobid, results):
    #wipe out all messages from redis list so no longer pushed to user
    for message in r_server.lrange(user+':messages', 0, -1):
        if '"job": "'+jobname in str(message):
            r_server.lrem(user+':messages', message)
    #update job to done in job table
    pgcursor = postgres.cursor(cursor_factory=DictCursor)
    SQL = "UPDATE meta_analysis_jobs SET done = true WHERE id = %s"
    try:
        pgcursor.execute(SQL, (jobid,))
        postgres.commit()
    except Exception, e:
        postgres.rollback()
        raise Exception("Can't finish off job!\n"+str(e)+\
            "\n"+SQL)
    #convert list of files to SQL formatted list
    for result in results:
        result[0] = "{"+','.join(result[0])+"}"
        result.append(str(jobid))
    #update all analyses in analysis table to done and with their results
    SQL = "UPDATE meta_analysis_analyses SET done = true, results = %s  WHERE \
    datatype = %s AND analysis = %s AND job = %s"
    try:
        pgcursor.executemany(SQL, results)
        postgres.commit()
        pgcursor.close()
    except Exception, e:
        postgres.rollback()
        for result in results:
            print SQL % result
        raise Exception("Can't finish off job!\n"+str(e)+"\n")
    #finally, push finisjed state
    push_notification(user, jobname, 'done', 'allcomplete')


@celery.task
def delete_job(user, jobid):
    SQL = 'DELETE FROM meta_analysis_jobs WHERE id = %s;' % jobid
    SQL += 'DELETE FROM meta_analysis_analyses WHERE job = %s;' % jobid
    try:
        pgcursor.execute(SQL)
        postgres.commit()
    except Exception, e:
        postgres.rollback()
        raise Exception("Can't remove metaanalysis from database!\n"+str(e)+\
            "\n"+SQL)


@celery.task
def switchboard(user, analysis_data):
    '''Fires off all analyses for a given job.

    INPUTS:
        user: username of user requesting job
        analysis_data: MetaAnalysisData object with all information in it.

    OUTPUT: NONE '''
    pgcursor = postgres.cursor(cursor_factory=DictCursor)
    jobname = analysis_data.get_job()
    #insert job into the postgres database
    SQL = "INSERT INTO meta_analysis_jobs (username, job, studies, metadata, \
        date_added) VALUES ('%s', '%s', '%s', '%s', 'now') RETURNING id" % (user, jobname,
        "{"+','.join(analysis_data.get_studies())+"}", 
        "{"+','.join(analysis_data.get_metadata())+"}")
    try:
        pgcursor.execute(SQL)
        jobid = pgcursor.fetchone()[0]
        postgres.commit()
    except Exception, e:
        postgres.rollback()
        raise Exception("Can't add metaanalysis to database!\n"+str(e)+\
            "\n"+SQL)

    #insert analyses into options database
    SQL="INSERT INTO meta_analysis_analyses (job, datatype, analysis, options) VALUES "
    for datatype in analysis_data.get_datatypes():
        for analysis in analysis_data.get_analyses(datatype):
            SQL += "(%i,'%s','%s','%s')," % (jobid, datatype, analysis, 
            dumps(analysis_data.get_options(datatype, analysis)))
    SQL = SQL[:-1]

    try:
        pgcursor.execute(SQL)
        postgres.commit()
        pgcursor.close()
    except Exception, e:
        postgres.rollback()
        print "Can't add metaanalysis options to database!\n"+str(e)+\
            "\n"+SQL

    #setup analysis
    analgroup = []
    for datatype in analysis_data.get_datatypes():
        for analysis in analysis_data.get_analyses(datatype):
            s = signature('app.tasks.'+analysis, args=(user, jobname, datatype,
                analysis_data.get_options(datatype, analysis)))
            analgroup.append(s)
    job = group(analgroup)
    res = job()
    results = res.get()
    finish_job(user, jobname, jobid, results)


@celery.task
def OTU_Table(user, jobname, datatype, opts):
    push_notification(user, jobname, datatype + ':OTU_Table', 'Running')
    try:
        sleep(randint(5,20))
        results = ['file%s.txt' % str(x) for x in range(0,randint(0,3))]
        push_notification(user, jobname, datatype + ':OTU_Table', 'Completed',
            results, done=True)
    except Exception, e:
        push_notification(user, jobname, datatype + ':OTU_Table',
            'ERROR: ' + str(e), done=True)
    #MUST RETURN IN FORMAT (results, datatype, analysis)
    return [results, datatype, 'OTU_Table']


@celery.task
def TopiaryExplorer_Visualization(user, jobname, datatype, opts):
    push_notification(user, jobname, 
        datatype + ':TopiaryExplorer_Visualization', 'Running')
    try:
        sleep(randint(5,20))
        results = ['file%s.txt' % str(x) for x in range(0,randint(0,3))]
        push_notification(user, jobname, 
            datatype + ':TopiaryExplorer_Visualization', 'Completed',
            results, done=True)
    except Exception, e:
        push_notification(user, jobname, datatype + ':TopiaryExplorer_Visualization',
            'ERROR: ' + str(e), done=True)
    #MUST RETURN IN FORMAT (results, datatype, analysis)
    return [results, datatype, 'TopiaryExplorer_Visualization']


@celery.task
def Heatmap(user, jobname, datatype, opts):
    push_notification(user, jobname, datatype + ':Heatmap', 'Running')
    try:
        sleep(randint(5,20))
        results = ['file%s.txt' % str(x) for x in range(0,randint(0,3))]
        push_notification(user, jobname, datatype + ':Heatmap', 'Completed',
            results, done=True)
    except Exception, e:
        push_notification(user, jobname, datatype + ':Heatmap',
            'ERROR: ' + str(e), done=True)
    #MUST RETURN IN FORMAT (results, datatype, analysis)
    return [results, datatype, 'Heatmap']


@celery.task
def Heatmap(user, jobname, datatype, opts):
    push_notification(user, jobname, datatype + ':Heatmap', 'Running')
    try:
        sleep(randint(5,20))
        results = ['file%s.txt' % str(x) for x in range(0,randint(0,3))]
        push_notification(user, jobname, datatype + ':Heatmap', 'Completed',
            results, done=True)
    except Exception, e:
        push_notification(user, jobname, datatype + ':Heatmap',
            'ERROR: ' + str(e), done=True)
    #MUST RETURN IN FORMAT (results, datatype, analysis)
    return [results, datatype, 'Heatmap']


@celery.task
def Heatmap(user, jobname, datatype, opts):
    push_notification(user, jobname, datatype + ':Heatmap', 'Running')
    try:
        sleep(randint(5,20))
        results = ['file%s.txt' % str(x) for x in range(0,randint(0,3))]
        push_notification(user, jobname, datatype + ':Heatmap', 'Completed',
            results, done=True)
    except Exception, e:
        push_notification(user, jobname, datatype + ':Heatmap',
            'ERROR: ' + str(e), done=True)
    #MUST RETURN IN FORMAT (results, datatype, analysis)
    return [results, datatype, 'Heatmap']


@celery.task
def Taxonomy_Summary(user, jobname, datatype, opts):
    push_notification(user, jobname, datatype + ':Taxonomy_Summary', 'Running')
    try:
        sleep(randint(5,20))
        results = ['file%s.txt' % str(x) for x in range(0,randint(0,3))]
        push_notification(user, jobname, datatype + ':Taxonomy_Summary', 'Completed',
            results, done=True)
    except Exception, e:
        push_notification(user, jobname, datatype + ':Taxonomy_Summary',
            'ERROR: ' + str(e), done=True)
    #MUST RETURN IN FORMAT (results, datatype, analysis)
    return [results, datatype, 'Taxonomy_Summary']


@celery.task
def Alpha_Diversity(user, jobname, datatype, opts):
    push_notification(user, jobname, datatype + ':Alpha_Diversity', 'Running')
    try:
        sleep(randint(5,20))
        results = ['file%s.txt' % str(x) for x in range(0,randint(0,3))]
        push_notification(user, jobname, datatype + ':Alpha_Diversity', 'Completed',
            results, done=True)
    except Exception, e:
        push_notification(user, jobname, datatype + ':Alpha_Diversity',
            'ERROR: ' + str(e), done=True)
    #MUST RETURN IN FORMAT (results, datatype, analysis)
    return [results, datatype, 'Alpha_Diversity']


@celery.task
def Beta_Diversity(user, jobname, datatype, opts):
    push_notification(user, jobname, datatype + ':Beta_Diversity', 'Running')
    try:
        sleep(randint(5,20))
        results = ['file%s.txt' % str(x) for x in range(0,randint(0,3))]
        push_notification(user, jobname, datatype + ':Beta_Diversity', 'Completed',
            results, done=True)
    except Exception, e:
        push_notification(user, jobname, datatype + ':Beta_Diversity',
            'ERROR: ' + str(e), done=True)
    #MUST RETURN IN FORMAT (results, datatype, analysis)
    return [results, datatype, 'Beta_Diversity']


@celery.task
def Procrustes(user, jobname, datatype, opts):
    push_notification(user, jobname, datatype + ':Procrustes', 'Running')
    try:
        sleep(randint(5,20))
        results = ['file%s.txt' % str(x) for x in range(0,randint(0,3))]
        push_notification(user, jobname, datatype + ':Procrustes', 'Completed',
            results, done=True)
    except Exception, e:
        push_notification(user, jobname, datatype + ':Procrustes',
            'ERROR: ' + str(e), done=True)
    #MUST RETURN IN FORMAT (results, datatype, analysis)
    return [results, datatype, 'Procrustes']


@celery.task
def Network_Analysis(user, jobname, datatype, opts):
    push_notification(user, jobname, datatype + ':Network_Analysis', 'Running')
    try:
        sleep(randint(5,20))
        results = ['file%s.txt' % str(x) for x in range(0,randint(0,3))]
        push_notification(user, jobname, datatype + ':Network_Analysis', 'Completed',
            results, done=True)
    except Exception, e:
        push_notification(user, jobname, datatype + ':Network_Analysis',
            'ERROR: ' + str(e), done=True)
    #MUST RETURN IN FORMAT (results, datatype, analysis)
    return [results, datatype, 'Network_Analysis']