from db import db, urlmap_entities, urlmap_profile, OnDisk, InMemory

from bottle import route, run, static_file, HTTPError, HTTPResponse

use_twitter_cdn_for_images = False

class ClientAPI:
	def __init__(self, db):
		self.db = db

	# tweets

	def urlmap(self, url):
		if self.db.media.lookup(url):
			return "/media" + url[7:] # /media/pbs.twitter.com/...
		if use_twitter_cdn_for_images:
			return url

	def patch(self, tweet):
		if not tweet:
			return

		user = self.get_profile(int(tweet.get("user_id_str", -1)))

		entities = None
		if "entities" in tweet:
			entities = urlmap_entities(self.urlmap, tweet["entities"])

		quoted_status = None
		if "quoted_status_id_str" in tweet:
			quoted_status = self.get_tweet(int(tweet["quoted_status_id_str"]))

		if user or entities or quoted_status:
			tweet = tweet.copy()
			if user:
				tweet["user"] = user
			if entities:
				tweet["entities"] = entities
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
		p = urlmap_profile(self.urlmap, p)
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
	r = static_file(path, root='node_modules/preact/')
	if isinstance(r, HTTPError) and path == "dist/preact.mjs":
		# fall back to bundled preact copy
		r = static_file('preact.mjs', root='static')
	return r

@route('/media/<path:path>')
def media(path):
	item = db.media.lookup("https://"+path)
	if isinstance(item, OnDisk):
		return static_file(os.path.basename(item.path), root=os.path.dirname(item.path))
	elif isinstance(item, InMemory):
		# todo: caching headers, range queries?
		return HTTPResponse(item.data, status=200, **{"Content-Type": item.mime})
	else:
		return HTTPError(404)

@route('/<name>.js')
def client_js(name):
	return static_file(name+'.js', root='static')

@route('/')
def index():
	return static_file('index.html', root='static')

run()
