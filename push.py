#adapted from https://github.com/leporo/tornado-redis/blob/master/demos/websockets

from tornadoredis import Client
from tornado.websocket import WebSocketHandler
import tornado.gen


class MessageHandler(WebSocketHandler):
    def __init__(self, *args, **kwargs):
        super(MessageHandler, self).__init__(*args, **kwargs)
        self.client = Client()
        self.client.connect()

    def on_message(self, msg):
        #listens for handshake from page
        if "channel:" in msg: 
            self.channel = msg.split(':')[1]
            #need to split the rest off to new func so it can be asynchronous
            self.listen()

    #decorator turns the function into an asynchronous generator object
    @tornado.gen.engine
    def listen(self):
        #runs task given, with the yield required to get returned value
        #equivalent of callback/wait pairing from tornado.gen
        yield tornado.gen.Task(self.client.subscribe, self.channel)
        if self.client.subscribed:
            #self.write_message used to send message to client
            self.write_message("Subscribed to " + self.channel)
        else:
            self.write_message('ERROR IN SUBSCRIPTION')
        #listen from tornadoredis makes the listen object asynchronous
        #if using standard redis lib, it blocks while listening
        self.client.listen(self.callback)
        #try and fight race condition by loading from redis after listen started
        oldmessages = yield tornado.gen.Task(self.client.lrange, 
            self.channel, 0, -1)
        if oldmessages != None:
            for message in oldmessages:
                self.write_message(message)

    def callback(self, msg):
        if msg.kind == 'message':
            self.write_message(str(msg.body))

    @tornado.gen.engine
    def on_close(self):
        yield tornado.gen.Task(self.client.unsubscribe, self.channel)
        self.client.disconnect()