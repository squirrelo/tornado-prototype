#login code modified from https://gist.github.com/guillaumevincent/4771570

from os.path import splitext
from random import randint
import tornado.auth
import tornado.escape
import tornado.httpserver
import tornado.ioloop
import tornado.options
import tornado.web
import tornado.websocket
from tornado.options import define, options
from hashlib import sha512
from settings import *
from app.tasks import switchboard, delete_job
from push import MessageHandler
from app.utils import MetaAnalysisData
from redis import Redis
from psycopg2 import connect as pg_connect
from psycopg2.extras import DictCursor

try:
    postgres=pg_connect("dbname='qiita' user='defaultuser' \
        password='defaultpassword' host='localhost'")
except:
    raise RuntimeError("ERROR: unable to connect to the POSTGRES database.")

try:
    r_server = Redis(host='localhost')
except:
    raise RuntimeError("ERROR: unable to connect to the REDIS database.")

define("port", default=8888, help="run on the given port", type=int)

metaAnalysis = MetaAnalysisData()

class BaseHandler(tornado.web.RequestHandler):
    def get_current_user(self):
        '''Overrides default method of returning user curently connected'''
        user = self.get_secure_cookie("user")
        if user == None:
            self.clear_cookie("user")
            return ''
        else:
            return user.strip('" ')

    def write_error(self, status_code, **kwargs):
        '''Overrides the error page created by Tornado'''
        from traceback import format_exception
        if self.settings.get("debug") and "exc_info" in kwargs:
            exc_info = kwargs["exc_info"]
            trace_info = ''.join(["%s<br />" % line for line in \
                format_exception(*exc_info)])
            request_info = ''.join(["<strong>%s</strong>: %s<br />" % \
                (k, self.request.__dict__[k]) for k in self.request.__dict__.keys()])
            error = exc_info[1]

            self.render('error.html', error=error, trace_info=trace_info,
                request_info=request_info, user=self.get_current_user())

class MainHandler(BaseHandler):
    '''Index page'''
    @tornado.web.authenticated
    def get(self):
        username = self.current_user
        username = username.strip('" ')
        SQL = "SELECT DISTINCT job, id FROM meta_analysis_jobs WHERE username = '%s'\
        AND done = true ORDER BY job" % username
        pgcursor = postgres.cursor(cursor_factory=DictCursor)
        pgcursor.execute(SQL)
        completedjobs = pgcursor.fetchall()
        if completedjobs == None:
            completedjobs = []
        self.render("index.html", user=username, jobs=completedjobs)


class AuthCreateHandler(BaseHandler):
    '''User Creation'''
    def get(self):
        try:
            errormessage = self.get_argument("error")
        except:
            errormessage = ""
        self.render("create.html", user=self.get_current_user(), 
            errormessage = errormessage)

    def post(self):
        username = self.get_argument("username", "")
        created, error = self.create_user(username, 
            sha512(self.get_argument("password", "")).hexdigest())
        if created:
            self.redirect(self.get_argument("next", u"/"))
        else:
            error_msg = u"?error=" + tornado.escape.url_escape(error)
            self.redirect(u"/auth/create/" + error_msg)

    def create_user(self, username, password):
        if username == "":
            return False, "No username given!"
        if password == sha512("").hexdigest():
            return False, "No password given!"
        try:
            #heck to make sure user does not already exist
            SQL = "SELECT * FROM site_users WHERE username = %s"
            pgcursor = postgres.cursor()
            pgcursor.execute(SQL, (username,))
            exists = pgcursor.fetchall()
        except Exception, e:
            return False, "Database query error! " + str(e)
        if exists != []:
            return False, "Username already exists!"
        try:
            # THIS IS THE ONLY PLACE THAT SHOULD MODIFY THE DB IN THIS CODE!
            #ALL OTHERS GO THROUGH THE MIDDLEWARE!!!!!
            #THIS PROBABLY SHOULD BE MIDDLEWARE TOO!
            SQL = "INSERT INTO site_users (username, password) VALUES (%s, %s)"
            pgcursor.execute(SQL, (username, password))
            postgres.commit()
            pgcursor.close()
            return True, ""
        except Exception, e:
            postgres.rollback()
            return False, "Database set error! " + str(e)


class AuthLoginHandler(BaseHandler):
    '''Login Page'''
    def get(self):
        try:
            errormessage = self.get_argument("error")
        except:
            errormessage = ""
        self.render("login.html", user=self.get_current_user(),
            errormessage = errormessage)

    def check_permission(self, username, password):
        try:
            SQL = "SELECT password from site_users WHERE username = %s"
            pgcursor = postgres.cursor()
            pgcursor.execute(SQL, (username,))
            dbpass = pgcursor.fetchone()[0]
            pgcursor.close()
        except:
            return False
        if password == dbpass:
            return True
        return False
        

    def post(self):
        username = self.get_argument("username", "")
        auth = self.check_permission(username,
            sha512(self.get_argument("password", "")).hexdigest())
        if auth:
            self.set_current_user(username)
            self.redirect(self.get_argument("next", u"/"))
        else:
            error_msg = u"?error=" + tornado.escape.url_escape("Login incorrect")
            self.redirect(u"/auth/login/" + error_msg)

    def set_current_user(self, user):
        if user:
            self.set_secure_cookie("user", tornado.escape.json_encode(user))
        else:
            self.clear_cookie("user")

class AuthLogoutHandler(BaseHandler):
    '''Logout handler, no page necessary'''
    def get(self):
        self.clear_cookie("user")
        self.redirect("/")
        
class WaitingHandler(BaseHandler):
    '''Waiting Page'''
    @tornado.web.authenticated
    def get(self, job):
        username = self.get_current_user()
        SQL = "SELECT done FROM meta_analysis_jobs WHERE username = '%s' AND \
        job = '%s'" % username, job
        try:
            pgcursor = postgres.cursor(cursor_factory=DictCursor)
            pgcursor.execute(SQL)
            jobdone = bool(pgcursor.fetchone()[0])
        except:
            raise SyntaxError("ERROR: JOB INFO CAN NOT BE RETRIEVED:\n" + SQL)
        if jobdone:
            self.redirect('/completed/'+job)
        else:
            pass
            #NEED TO DO SQL QUERY TO GET analyses
            self.render("waiting.html", user=user, job=job, analyses=analyses)

    @tornado.web.authenticated
    #This post function takes care of actual job submission
    def post(self, page):
        user = self.get_current_user()
        r_server.rpush(user + ":jobs", metaAnalysis.get_job())
        analyses = metaAnalysis.options.keys()
        analyses.sort()
        self.render("waiting.html", user=user, job=metaAnalysis.get_job(), 
            analyses=analyses)
        #MUST CALL CELERY AFTER PAGE CALL!
        switchboard.delay(user, metaAnalysis)

class FileHandler(BaseHandler):
    '''File upload handler'''
    def get(self):
        pass

    @tornado.web.authenticated
    def post(self):
        upfile = self.request.files['file'][0]
        fname = upfile['filename']
        extension = splitext(fname)[1]
        newname = self.get_argument('filename')
        if newname == '':
            newname = ''.join([str(randint(0,9)) for x in range(0,10)])
        newname += extension
        output_file = open("uploads/" + newname, 'w')
        output_file.write(upfile['body'])
        output_file.close()
        self.redirect("/")

class ShowJobHandler(BaseHandler):
    '''Completed job page'''
    @tornado.web.authenticated
    def get(self, job):
        user = self.get_current_user()

        SQL = "SELECT * FROM meta_analysis_analyses WHERE EXISTS (SELECT id \
            FROM meta_analysis_jobs WHERE username ='%s' and job = '%s')"\
         % (user, job)
        try:
            pgcursor = postgres.cursor(cursor_factory=DictCursor)
            pgcursor.execute(SQL)
            jobinfo = pgcursor.fetchall()
            pgcursor.close()
            self.render("jobinfo.html", user=user, job = job, jobinfo=jobinfo)
        except Exception, e:
            raise SyntaxError("ERROR:JOB INFO CAN'T BE RETRIEVED:\n"+e+"\n"+SQL)


    @tornado.web.authenticated
    def post(self, page):
        job = self.get_argument('job')
        user = self.get_current_user()
        SQL = "SELECT * FROM meta_analysis_analyses WHERE EXISTS (SELECT id \
            FROM meta_analysis_jobs WHERE username ='%s' and job = '%s') ORDER\
            BY datatype"\
         % (user, job)
        try:
            pgcursor = postgres.cursor(cursor_factory=DictCursor)
            pgcursor.execute(SQL)
            jobinfo = pgcursor.fetchall()
            pgcursor.close()
        except:
            postgres.rollback()
            raise SyntaxError("ERROR: JOB INFO CAN NOT BE RETRIEVED:\n" + SQL)
        self.render("jobinfo.html", user=user, job = job, jobinfo=jobinfo)

class DeleteJobHandler(BaseHandler):
    @tornado.web.authenticated
    def post(self):
        user = self.get_current_user()
        jobid = self.get_argument('jobid')
        delete_job.delay(user, jobid)
        self.redirect('/')


#ANALYSES and COMBINED lists are set in settings.py
class MetaAnalysisHandler(BaseHandler):
    def prepare(self):
        self.user = self.get_current_user()

    @tornado.web.authenticated
    def get(self, page):
        if page != '1':
            self.write('YOU SHOULD NOT ACCESS THIS PAGE DIRECTLY<br \>')
            self.write("You requested form page " + page + '<br \>')
            self.write('<a href="/">Home</a>')
        else:
            #global variable that is wiped when you start a new analysis
            metaAnalysis = MetaAnalysisData()
            metaAnalysis.set_user(self.user)
            self.render('meta1.html', user=self.user)

    @tornado.web.authenticated
    def post(self, page):
        if page == '1':
            pass
        elif page == '2':
            metaAnalysis.set_job(self.get_argument('jobname'))
            metaAnalysis.set_studies(self.get_arguments('studiesView'))
            if  metaAnalysis.get_studies() == []:
                raise ValueError('ERROR: Need at least one study to analyze.')
            metaAnalysis.set_metadata(self.get_arguments('metadataUse'))
            if  metaAnalysis.get_metadata() == []:
                raise ValueError('ERROR: Need at least one metadata selected.')
            metaAnalysis.set_datatypes(self.get_arguments('datatypeView'))
            if  metaAnalysis.get_datatypes() == []:
                raise ValueError('ERROR: Need at least one datatype selected.')
            self.render('meta2.html', user=self.user, 
                datatypes=metaAnalysis.get_datatypes(), single=SINGLE,
                combined=COMBINED)
        elif page == '3':
            for datatype in metaAnalysis.get_datatypes():
                metaAnalysis.set_analyses(datatype, self.get_arguments(datatype))
            self.render('meta3.html', user=self.user, analysisinfo=metaAnalysis)
        elif page == '4':
            #set options
            for datatype in metaAnalysis.get_datatypes():
                for analysis in metaAnalysis.get_analyses(datatype):
                    metaAnalysis.set_options(datatype, analysis,
                        {'opt1': 12, 'opt2': 'Nope'})
            self.render('meta4.html', user=self.user, analysisinfo=metaAnalysis)
        else:
            raise NotImplementedError("MetaAnalysis Page "+page+" missing!")

class MockupHandler(BaseHandler):
    def get(self):
        self.render("mockup.html", user=self.current_user)

class Application(tornado.web.Application):
    def __init__(self):
        handlers = [
            (r"/", MainHandler),
            (r"/auth/login/", AuthLoginHandler),
            (r"/auth/logout/", AuthLogoutHandler),
            (r"/auth/create/", AuthCreateHandler),
            (r"/waiting/(.*)", WaitingHandler),
            (r"/consumer/", MessageHandler),
            (r"/fileupload/", FileHandler),
            (r"/completed/(.*)", ShowJobHandler),
            (r"/meta/([0-9]+)", MetaAnalysisHandler),
            (r"/del/", DeleteJobHandler),
            (r"/mockup/", MockupHandler),
        ]
        settings = {
            "template_path": TEMPLATE_PATH,
            "static_path": STATIC_PATH,
            "debug": DEBUG,
            "cookie_secret": COOKIE_SECRET,
            "login_url": "/auth/login/"
        }
        tornado.web.Application.__init__(self, handlers, **settings)


def main():
    tornado.options.parse_command_line()
    http_server = tornado.httpserver.HTTPServer(Application())
    http_server.listen(options.port)
    tornado.ioloop.IOLoop.instance().start()

if __name__ == "__main__":
    main()