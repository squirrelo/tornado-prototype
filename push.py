#adapted from https://github.com/leporo/tornado-redis/blob/master/demos/websockets

from tornadoredis import Client
from app.tasks import r_server
from tornado.websocket import WebSocketHandler
import tornado.gen
from json import loads
from psycopg2 import connect as pg_connect

#all messages are in json format. They must have the following format:
# 'job': jobname
# 'msg': message to print
# 'results': list of files created if any


class MessageHandler(WebSocketHandler):
    def __init__(self, *args, **kwargs):
        super(MessageHandler, self).__init__(*args, **kwargs)
        self.redis = Client()
        self.redis.connect()
        try:
            self.postgres=pg_connect("dbname='qiita' user='defaultuser' \
                password='defaultpassword' host='localhost'")
            self.pgcursor = self.postgres.cursor()
        except:
            print "I am unable to connect to the Postgres database."
    def get_current_user(self):
        user = self.get_secure_cookie("user")
        if user == None:
            return ''
        else:
            return user.strip('" ')

    def on_message(self, msg):
        msginfo = loads(msg)
        #listens for handshake from page
        if "user:" in msginfo['msg']:
            self.channel = msginfo['msg'].split(':')[1]
            #need to split the rest off to new func so it can be asynchronous
            self.listen()
        if "done" in msginfo['msg']:
            #handshake the done to avoid lock if job finishes before page loads
            self.completed_job(msginfo)

    def completed_job(self, msginfo):
        job = msginfo['job']
        #wipe job from running list and all messages related to it and
        #add job to completed_jobs postgres table
        r_server.lrem(self.channel + ":jobs", 0, job)
        SQL = "INSERT INTO completed_jobs (username, job, msg, files) VALUES "
        for json in r_server.lrange(self.channel + ":messages", 0, -1):
            jsoninfo = loads(json)
            if jsoninfo['job'] == job: 
                r_server.lrem(self.channel + ":messages", 0, json)
                if jsoninfo['msg'] != 'done':
                    #reformat results to SQL insert format
                    res = '{' + ','.join(jsoninfo['results']) + '}'
                    SQL += "('%s','%s','%s','%s')," % (self.get_current_user(),
                        job, jsoninfo['msg'], res)
        try:
            self.pgcursor.execute(SQL[:-1])
            self.postgres.commit()
        except Exception, e:
            print "ERORR ADDING COMPLETED JOB MESSAGE:\n" + SQL[:-1]
            print e

    #decorator turns the function into an asynchronous generator object
    @tornado.gen.engine
    def listen(self):
        #runs task given, with the yield required to get returned value
        #equivalent of callback/wait pairing from tornado.gen
        yield tornado.gen.Task(self.redis.subscribe, self.channel)
        if not self.redis.subscribed:
            self.write_message('ERROR IN SUBSCRIPTION')
        #listen from tornadoredis makes the listen object asynchronous
        #if using standard redis lib, it blocks while listening
        self.redis.listen(self.callback)
        #try and fight race condition by loading from redis after listen started
        #need to use std redis lib because tornadoredis is in subscribed state
        oldmessages = r_server.lrange(self.channel + ':messages', 0, -1)
        if oldmessages != None:
            for message in oldmessages:
                self.write_message(message)

    def callback(self, msg):
        if msg.kind == 'message':
            self.write_message(str(msg.body))

    @tornado.gen.engine
    def on_close(self):
        yield tornado.gen.Task(self.redis.unsubscribe, self.channel)
        self.redis.disconnect()