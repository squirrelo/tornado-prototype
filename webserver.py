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
from app.tasks import stall_time
from push import MessageHandler
from app.tasks import r_server
from time import localtime

define("port", default=8888, help="run on the given port", type=int)

class BaseHandler(tornado.web.RequestHandler):
    def get_current_user(self):
        user = self.get_secure_cookie("user")
        if user == None:
            return ''
        else:
            return user.strip('" ')

class MainHandler(BaseHandler):
    @tornado.web.authenticated
    def get(self):
        username = self.current_user
        username = username.strip('" ')
        self.render("index.html", username = username)


class AuthCreateHandler(BaseHandler):
    def get(self):
        try:
            errormessage = self.get_argument("error")
        except:
            errormessage = ""
        self.render("create.html", errormessage = errormessage)

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
            return False, "Databse set error!"


class AuthLoginHandler(BaseHandler):
    def get(self):
        try:
            errormessage = self.get_argument("error")
        except:
            errormessage = ""
        self.render("login.html", errormessage = errormessage)

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
    def get(self):
        user = self.get_current_user()
        if r_server.exists(user + ":jobs"):
            jobs=r_server.lrange(user + ":jobs", 0, -1)
            self.render("waiting.html", user=user, jobs=jobs, totaljobs=len(jobs))
        else:
            self.redirect('/')

    def post(self):
        time = localtime()
        timestamp = '-'.join(map(str,[time.tm_year, time.tm_mon, time.tm_mday,
            time.tm_hour, time.tm_min, time.tm_sec]))
        user = self.get_current_user()
        r_server.rpush(user + ":jobs", timestamp)
        jobs=r_server.lrange(user + ":jobs", 0, -1)
        self.render("waiting.html", user=user, jobs=jobs, totaljobs=len(jobs))
        #MUST CALL CELERY AFTER PAGE CALL!
        stall_time.delay(user, timestamp, 10)

class FileHandler(BaseHandler):
    def get(self):
        pass

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


class Application(tornado.web.Application):
    def __init__(self):
        handlers = [
            (r"/", MainHandler),
            (r"/auth/login/", AuthLoginHandler),
            (r"/auth/logout/", AuthLogoutHandler),
            (r"/auth/create/", AuthCreateHandler),
            (r"/waiting/", WaitingHandler),
            (r"/consumer/", MessageHandler),
            (r"/fileupload/", FileHandler),
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