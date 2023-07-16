from db import db, urlmap_entities, urlmap_profile, OnDisk, InMemory

import time
from bottle import parse_date, request, route, run, static_file, HTTPError, HTTPResponse

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
		new_tweet = self.db.tweets.get(twid, tweet)
		if new_tweet == tweet:
			return tweet
		new_tweet = new_tweet.copy()
		new_tweet["context_icon"] = "retweet"
		try:
			new_tweet["context_user"] = self.db.profiles.get(int(tweet["user_id_str"]), {"name": "ERROR"})["name"]
		except:
			pprint(tweet)
			raise
		return new_tweet

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

	def bookmarks_view(self, uid):
		return [self.get_tweet(twid) for twid in self.db.get_user_bookmarks(uid)]

	# users

	def get_profile(self, uid):
		if uid not in self.db.profiles:
			return None
		p = self.db.profiles[uid].copy()
		p["user_id_str"] = str(uid)
		p = urlmap_profile(self.urlmap, p)
		return p

	def followers(self, uid):
		return [self.get_profile(uid) for uid in self.db.followers.get(uid, [])]

	def following(self, uid):
		return [self.get_profile(uid) for uid in self.db.followings.get(uid, [])]

	def everyone(self):
		uids = [(-len(self.db.by_user.get(uid, [])), uid) for uid in self.db.profiles.keys()]
		uids.sort()
		return [self.get_profile(uid) for neg_num_tweets, uid in uids if -neg_num_tweets >= 2]

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

@route('/api/bookmarks/<uid:int>')
def profile(uid):
	return {
		"topProfile": ca.get_profile(uid),
		"tweets": ca.bookmarks_view(uid) #[:200]
	}

@route('/api/followers/<uid:int>')
def thread(uid):
	return {
		"topProfile": ca.get_profile(uid),
		"profiles": ca.followers(uid)[:300]
	}

@route('/api/following/<uid:int>')
def thread(uid):
	return {
		"topProfile": ca.get_profile(uid),
		"profiles": ca.following(uid)[:300]
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

startup_time = time.time()

def static_blob(data, mime, mtime = None):
	mtime = mtime or startup_time

	headers = {}
	headers['Content-Type'] = mime
	lm = time.strftime("%a, %d %b %Y %H:%M:%S GMT", time.gmtime(mtime))
	headers['Last-Modified'] = lm

	ims = request.environ.get('HTTP_IF_MODIFIED_SINCE')
	if ims:
		ims = parse_date(ims.split(";")[0].strip())
	if ims is not None and ims >= int(mtime):
		headers['Date'] = time.strftime("%a, %d %b %Y %H:%M:%S GMT", time.gmtime())
		return HTTPResponse(status=304, **headers)

	body = '' if request.method == 'HEAD' else data
	return HTTPResponse(body, status=200, **headers)

@route('/media/<path:path>')
def media(path):
	item, cacheable = db.media.lookup("https://"+path), True
	if not cacheable and "HTTP_IF_MODIFIED_SINCE" in request.environ:
		del request.environ["HTTP_IF_MODIFIED_SINCE"]
	if isinstance(item, OnDisk):
		response = static_file(os.path.basename(item.path), root=os.path.dirname(item.path))
	elif isinstance(item, InMemory):
		# todo: caching headers, range queries?
		response = static_blob(item.data, item.mime)
	else:
		return HTTPError(404)

	if cacheable:
		response.expires = startup_time + 60 * 60 * 24 # one day?
	return response

@route('/<name>.js')
def client_js(name):
	return static_file(name+'.js', root='static')

@route('/')
@route('/everyone')
@route('/thread/<twid:int>')
@route('/profile/<who>')
@route('/profile/<who>/with_replies')
@route('/profile/<who>/media')
@route('/profile/<who>/likes')
@route('/profile/<who>/bookmarks')
@route('/profile/<who>/followers')
@route('/profile/<who>/following')
def index(**args):
	return static_file('index.html', root='static')

run()
