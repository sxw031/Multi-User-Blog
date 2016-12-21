import os, re, webapp2, jinja2, random, hashlib, hmac
from string import letters
from google.appengine.ext import db

template_dir = os.path.join(os.path.dirname(__file__), 'templates')
jinja_env = jinja2.Environment(loader = jinja2.FileSystemLoader(template_dir), autoescape = True)

secret = 'fart'
################### Base Handler for Convenience ###########################

def render_str(template, **params):
    t = jinja_env.get_template(template)
    return t.render(params)

def make_secure_val(val):
	return '%s|%s' % (val, hmac.new(secret, val).hexdigest())

def check_secure_val(secure_val):
	val = secure_val.split('|')[0]
	if secure_val == make_secure_val(val):
		return val
    
class BaseHandler(webapp2.RequestHandler):

	def write(self, *a, **kw):
		self.response.out.write(*a, **kw) 

	def render_str(self, template, **params):
		params['user'] = self.user
		return render_str(template, **params)

	def render(self, template, **kw):
		self.write(self.render_str(template, **kw))

	def set_secure_cookie(self, name, val):
		cookie_val = make_secure_val(val)
		self.response.headers.add_header('Set-Cookie','%s=%s; Path=/' % (name, cookie_val))

	def read_secure_cookie(self, name):
		cookie_val = self.request.cookies.get(name)
		return cookie_val and check_secure_val(cookie_val)

	def login(self, user):
		self.set_secure_cookie('user_id', str(user.key().id()))

	def logout(self):
		self.response.headers.add_header('Set-Cookie', 'user_id=; Path=/')

	def initialize(self, *a, **kw):
		"""check if the user is login or not"""
		webapp2.RequestHandler.initialize(self, *a, **kw)
		uid = self.read_secure_cookie('user_id')
		self.user = uid and User.by_id(int(uid))

def render_post(response, post):
	response.out.write('<b>' + post.subject + '</br><br>')
	response.out.write(post.content)

############################# Rot13 ########################################

class Rot13(BaseHandler):
	def get(self):
		self.render("rot13.html")

	def post(self):
		rot13=""
		text = self.request.get("text")
		if text:
			rot13 = text.encode("rot13")

		self.render('rot13.html', text = rot13)

############################## Users ######################################
def make_salt(length = 5):
	"""make a string of 5 letters"""
	return ''.join(random.choice(letters) for x in xrange(length))

def make_pw_hash(name, pw, salt = None):
	"""make a password hashed"""
	if not salt:
		salt = make_salt()
	h = hashlib.sha256(name + pw + salt).hexdigest()
	return '%s,%s' % (salt, h)

def valid_pw(name, password, h):
	"""validate password, make sure the hash from the database matches the new hash based on the users entered in """
	salt = h.split(',')[0]
	return h == make_pw_hash(name, password, salt)

def users_key(group = 'default'):
	return db.Key.from_path('users', group)

class User(db.Model):
	name = db.StringProperty(required = True)
	pw_hash = db.StringProperty(required = True)
	email = db.StringProperty()

	@classmethod
	def by_id(cls,uid):
		return User.get_by_id(uid, parent = users_key())

	@classmethod
	def by_name(cls, name):
		u = User.all().filter('name =', name).get()
		return u

	@classmethod
	def register(cls, name, pw, email = None):
		pw_hash = make_pw_hash(name, pw)
		return User(parent = users_key(), name = name, pw_hash = pw_hash, email = email)

	@classmethod
	def login(cls, name, pw):
		u = cls.by_name(name)
		if u and valid_pw(name, pw, u.pw_hash):
			return u

############################# Signup ######################################

USER_RE = re.compile(r"^[a-zA-Z0-9_-]{3,20}$")
def valid_username(username):
	return username and USER_RE.match(username)

PASS_RE = re.compile(r"^.{3,20}$")
def valid_password(password):
	return password and PASS_RE.match(password)

EMAIL_RE  = re.compile(r'^[\S]+@[\S]+\.[\S]+$')
def valid_email(email):
	return not email or EMAIL_RE.match(email)

class Signup(BaseHandler):
	def get(self):
		self.render("signup.html")

	def post(self):
		have_error = False
		self.username = self.request.get("username")
		self.password = self.request.get("password")
		self.verify = self.request.get("verify")
		self.email = self.request.get("email")

		params = dict(username=self.username, password=self.password)

		if not valid_username(self.username):
			params["error_username"] = "Please enter a valid username."
			have_error = True

		if not valid_password(self.password):
			params["error_password"] = "Please enter a valid password."
			have_error = True
		elif self.password != self.verify:
			params["error_verify"] = "Your password didn't match."
			have_error = True

		if not valid_email(self.email):
			params["error_email"] = "That's not a valid email."
			have_error = True

		if have_error:
			self.render("signup.html", **params)
		else:
			self.done()

	def done(self, *a, **kw):
		raise NotImplementedError

class Unit2Signup(Signup):
	def done(self):
		self.redirect('/unit2/welcome?username='  + self.username)

class Register(Signup):
	def done(self):
		# make sure the user doesn't already exist
		u = User.by_name(self.username)
		if u:
			msg = 'That user already exists.'
			self.render('signup.html', error_username = msg)
		else:
			u = User.register(self.username, self.password, self.email)
			u.put()

			self.login(u)
			self.redirect('unit3/welcome')

class Login(BaseHandler):
	def get(self):
		self.render('login.html')

	def post(self):
		username = self.request.get('username')
		password = self.request.get('password')

		u = User.login(username, password)
		if u:
			self.login(u)
			self.redirect('/blog')
		else:
			msg = 'Invalid login'
			self.render('login.html', error = msg)

class Logout(BaseHandler):
	def get(self):
		self.logout()
		self.redirect('/signup')

############################## Blog ######################################

def blog_key(name = 'default'):
	"""define the blogs's parent"""
	return db.Key.from_path('blogs', name)

class Post(db.Model):
	subject = db.StringProperty(required = True)
	content = db.TextProperty(required = True)
	created = db.DateTimeProperty(auto_now_add = True)
	last_modified = db.DateTimeProperty(auto_now = True)

	def render(self):
		self._render_text = self.content.replace('\n', '</br>')
		return render_str("post.html", p = self)

class BlogFront(BaseHandler):
	def get(self):
		posts = Post.all().order('-created') ## db.GqlQuery("select * from Post order by created desc limit 10")
		self.render("font.html", posts = posts)

class PostPage(BaseHandler):
	def get(self, post_id):
		key = db.Key.from_path('Post', int(post_id), parent = blog_key())
		post = db.get(key)

		if not post:
			self.error(404)
			return

		self.render("permalink.html", post = post)

class NewPage(BaseHandler):
	def get(self):
		if self.user:
			self.render("newpost.html")
		else:
			self.redirect("/login")

	def post(self):
		if not self.user:
			self.redirect('/blog')

		subject = self.request.get('subject')
		content = self.request.get('content')

		if subject and content:
			p = Post(parent = blog_key(), subject = subject, content = content)
			p.put()
			self.redirect('/blog/%s' % str(p.key().id()))
		else:
			error = "subject anf content, please!"
			self.render("newpost.html", subject = subject, content = content, error = error)

class Unit3Welcome(BaseHandler):
	def get(self):
		if self.user:
			self.render('welcome.html', username = self.user.name)
		else:
			self.redirect('/signup')

class Welcome(BaseHandler):
	def get(self):
		username = self.request.get('username')
		if valid_username(username):
			self.render('welcome.html', username = username)
		else:
			self.redirect('signup')

class MainPage(BaseHandler):
	def get(self):
		self.write('Hello, Udacity! It is a happy learning!')

app = webapp2.WSGIApplication([('/unit2/rot13', Rot13), 
							   ('/unit2/signup', Unit2Signup), 
							   ('/unit2/welcome', Welcome),
							   ('/unit3/welcome', Unit3Welcome),
							   ('/blog/?', BlogFront),
							   ('/blog/([0-9]+)',PostPage),
							   ('/blog/newpost', NewPage),
							   ('/signup', Register),
							   ('/login', Login),
							   ('/logout', Logout),
							   ('/', MainPage)
							   ], debug=True)




