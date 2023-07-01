from db import db

from bottle import route, run, static_file

class ClientAPI:
	def __init__(self, db):
		self.db = db

	# tweets

	def patch(self, tweet):
		if not tweet:
			return

		user = self.get_profile(int(tweet.get("user_id_str", -1)))

		quoted_status = None
		if "quoted_status_id_str" in tweet:
			quoted_status = self.get_tweet(int(tweet["quoted_status_id_str"]))

		if user or quoted_status:
			tweet = tweet.copy()
			if user:
				tweet["user"] = user
			if quoted_status:
				tweet["quoted_status"] = quoted_status
		return tweet

	def get_original(self, tweet):
		twid = tweet["original_id"]
		return self.db.tweets.get(twid, tweet)

	def get_tweet(self, twid):
		tweet = self.db.tweets.get(twid, None)
		if not tweet:
			return
		tweet = self.get_original(tweet)
		return self.patch(tweet)

	def profile_view(self, uid):
		return [self.get_tweet(twid) for twid in self.db.get_user_tweets(uid)]

	def with_replies_view(self, uid):
		return [self.get_tweet(twid) for twid in self.db.get_user_with_replies(uid)]

	def media_view(self, uid):
		return [self.get_tweet(twid) for twid in self.db.get_user_media(uid)]

	def likes_view(self, uid):
		return [self.get_tweet(twid) for twid in self.db.get_user_likes(uid)]

	# users

	def get_profile(self, uid):
		if uid not in self.db.profiles:
			return None
		p = self.db.profiles[uid].copy()
		p["user_id_str"] = str(uid)
		return p

	def everyone(self):
		return [self.get_profile(uid) for uid in self.db.profiles.keys()]

ca = ClientAPI(db)

@route('/api/profile/<uid:int>')
def profile(uid):
	return {
		"topProfile": ca.get_profile(uid),
		"tweets": ca.profile_view(uid) #[:200]
	}

@route('/api/replies/<uid:int>')
def profile(uid):
	return {
		"topProfile": ca.get_profile(uid),
		"tweets": ca.with_replies_view(uid) #[:200]
	}

@route('/api/media/<uid:int>')
def profile(uid):
	return {
		"topProfile": ca.get_profile(uid),
		"tweets": ca.media_view(uid) #[:200]
	}

@route('/api/likes/<uid:int>')
def profile(uid):
	return {
		"topProfile": ca.get_profile(uid),
		"tweets": ca.likes_view(uid) #[:200]
	}

@route('/api/everyone')
def thread():
	return {"profiles": ca.everyone()}

@route('/fonts/<path:path>')
def resources_20230628(path):
	return static_file(path, root='static/20230628/fonts')

@route('/responsive-web/<path:path>')
def resources_20230628(path):
	return static_file(path, root='static/20230628/responsive-web')

@route('/p/<path:path>')
def preact_js(path):
	return static_file(path, root='node_modules/preact/')

@route('/<name>.js')
def client_js(name):
	return static_file(name+'.js', root='static')

@route('/')
def index():
	return static_file('index.html', root='static')

run()
