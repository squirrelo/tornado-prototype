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
from app.tasks import switchboard
from push import MessageHandler
from app.tasks import r_server
from time import localtime
from psycopg2 import connect as pg_connect
from psycopg2.extras import DictCursor

define("port", default=8888, help="run on the given port", type=int)
try:
    postgres=pg_connect("dbname='qiita' user='defaultuser' \
        password='defaultpassword' host='localhost'")
    pgcursor = postgres.cursor(cursor_factory=DictCursor)
except:
    raise RuntimeError("ERROR: unable to connect to the Postgres database.")

class BaseHandler(tornado.web.RequestHandler):
    def get_current_user(self):
        user = self.get_secure_cookie("user")
        if user == None:
            self.clear_cookie("user")
        else:
            return user.strip('" ')

    def write_error(self, status_code, **kwargs):
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
    @tornado.web.authenticated
    def get(self):
        username = self.current_user
        username = username.strip('" ')
        SQL = "SELECT DISTINCT job FROM completed_jobs WHERE username = '%s'"\
            % username
        pgcursor.execute(SQL)
        completedjobs = pgcursor.fetchall()
        if completedjobs == None:
            cjobs = []
        else:
            cjobs = [job[0] for job in completedjobs]
        self.render("index.html", user=username, jobs=cjobs)


class AuthCreateHandler(BaseHandler):
    def get(self):
        try:
            errormessage = self.get_argument("error")
        except:
            errormessage = ""
        self.render("create.html", user=self.current_user, errormessage = errormessage)

    def post(self):
        username = self.get_argument("username", "")
        created, error = self.create_user(username, 
            sha512(self.get_argument("password", "")).digest())
        if created:
            self.redirect(self.get_argument("next", u"/"))
        else:
            error_msg = u"?error=" + tornado.escape.url_escape(error)
            self.redirect(u"/auth/create/" + error_msg)

    def create_user(self, username, password):
        if username == "":
            return False, "No username given!"
        if password == sha512("").digest():
            return False, "No password given!"
        userkey = "user:" + username
        exists = r_server.get("user:"+username)
        if exists:
            return False, "Username already exists!"
        setstatus = r_server.set(userkey, password)
        if setstatus:
            return True, ""
        else:
            return False, "Database set error!"


class AuthLoginHandler(BaseHandler):
    def get(self):
        try:
            errormessage = self.get_argument("error")
        except:
            errormessage = ""
        self.render("login.html", user=self.current_user, errormessage = errormessage)

    def check_permission(self, username, password):
        dbpass = r_server.get("user:"+username)
        if dbpass == False:
            return False
        if password == dbpass:
            return True
        return False
        

    def post(self):
        username = self.get_argument("username", "")
        auth = self.check_permission(username,
            sha512(self.get_argument("password", "")).digest())
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
    def get(self):
        self.clear_cookie("user")
        self.redirect("/")
        
#WAITING PAGE!!!
class WaitingHandler(BaseHandler):
    @tornado.web.authenticated
    def get(self, page):
        self.write("YOU SHOULD NOT BE HERE. HERE THERE BE DRAGONS.")

    @tornado.web.authenticated
    def post(self):
        user = self.get_current_user()
        r_server.rpush(user + ":jobs", metaAnalysis.get_job())
        analyses = metaAnalysis.options.keys()
        analyses.sort()
        self.render("waiting.html", user=user, job=metaAnalysis.get_job(), 
            totalanalyses=len(metaAnalysis.options), analyses=analyses)
        #MUST CALL CELERY AFTER PAGE CALL!
        switchboard.delay(user, metaAnalysis.get_job(), metaAnalysis.options)

class FileHandler(BaseHandler):
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

#Completed job info page
class ShowJobHandler(BaseHandler):
    @tornado.web.authenticated
    def get(self, job):
        user = self.get_current_user()
        SQL = "SELECT * FROM completed_jobs WHERE username ='%s' and job = '%s'"\
         % (user, job)
        try:
            pgcursor.execute(SQL)
            jobinfo = pgcursor.fetchall()
            self.render("jobinfo.html", user=user, job = job, jobinfo=jobinfo)
        except:
            raise SyntaxError("ERROR: JOB INFO CAN NOT BE RETRIEVED:\n" + SQL)


    @tornado.web.authenticated
    def post(self, page):
        job = self.get_argument('job')
        user = self.get_current_user()
        SQL = "SELECT * FROM completed_jobs WHERE username ='%s' and job = '%s'"\
         % (user,job)
        try:
            pgcursor.execute(SQL)
            jobinfo = pgcursor.fetchall()
            self.render("jobinfo.html", user=user, job = job, jobinfo=jobinfo)
        except:
            raise SyntaxError("ERROR: JOB INFO CAN NOT BE RETRIEVED:\n" + SQL)


class MetaAnalysisData():
    def __init__(self):
        self.user = ''
        self.job = ''
        self.studies = []
        self.datatypes = []
        self.metadata = []
        self.analyses = {}
        self.options = {}

    #tornado sends form data in unicode, convert to ascii for ease of use
    def set_user(self, user):
        self.user = user.encode('ascii')

    def set_job(self, job):
        if job == '':
            time = localtime()
            self.job = '-'.join(map(str,[time.tm_year, time.tm_mon, time.tm_mday,
                time.tm_hour, time.tm_min, time.tm_sec]))
        else:
            self.job = job.encode('ascii')

    def set_studies(self, studies):
        self.studies = [study.encode('ascii') for study in studies]

    def set_datatypes(self, datatypes):
        self.datatypes = [datatype.encode('ascii') for datatype in datatypes]

    def set_metadata(self, metadata):
        self.metadata = [m.encode('ascii') for m in metadata]

    def set_analyses(self, datatype, analyses):
        self.analyses[datatype] = [a.encode('ascii') for a in analyses]

    def set_options(self, datatype, analysis, options):
        self.options[datatype + ':' + analysis] = options

    def get_user(self):
        return self.user

    def get_job(self):
        return self.job

    def get_studies(self):
        return self.studies

    def get_datatypes(self):
        return self.datatypes

    def get_metadata(self):
        return self.metadata

    def get_analyses(self, datatype):
        if datatype in self.analyses.keys():
            return self.analyses[datatype]
        else:
            raise ValueError('Datatype not part of analysis!')

    def get_options(self, datatype, analysis):
        if datatype + ':' + analysis in self.options.keys():
            return self.options[datatype + ':' + analysis]
        else:
            raise ValueError('Datatype or analysis passed not part of analysis!')

    def iter_options(self, datatype, analysis):
        if datatype + ':' + analysis in self.options.keys():
            optdict = self.options[datatype + ':' + analysis]
            for opt in optdict:
                yield opt, optdict[opt]
        else:
            raise ValueError('Datatype or analysis passed not part of analysis!')

    def html(self):
        html = '<table width="100%"><tr><td width="34%""><h3>Studies</h3>'
        for study in self.get_studies():
            html += study + "<br />"
        html += '</td><td width="33%"><h3>Metadata</h3>'
        for metadata in self.get_metadata():
            html += metadata + "<br />"
        html += '</td><td width="33%"><h3>Datatypes</h3>'
        for datatype in self.get_datatypes():
            html += datatype + "<br />"
        html += "</td><tr></table>"
        html += '<h3>Option Settings</h3>'
        for datatype in self.get_datatypes():
            for analysis in self.get_analyses(datatype):
                html += ''.join(['<table width=32%" style="display: \
                    inline-block;"><tr><td><b>',datatype,' - ',
                analysis, '</b></td></tr><tr><td>'])
                for opt, value in self.iter_options(datatype, analysis):
                    html += ''.join([opt, ':', str(value), '<br />'])
                html += '</td></tr></table>'
        return html

metaAnalysis = MetaAnalysisData()

#ANALYSES and COMBINED set in settings.py
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