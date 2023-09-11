from db import db, urlmap_entities, urlmap_profile, OnDisk, InZip, InMemory

import os.path, time, datetime, sys
server_path = os.path.dirname(__file__)
sys.path.append(server_path + "/vendor") # use bundled copy of bottle, if system has none
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

		tweet = tweet.copy()
		if user:
			tweet["user"] = user
		if entities:
			tweet["entities"] = entities
		if quoted_status:
			tweet["quoted_status"] = quoted_status
		del tweet["original_id"]
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

	def interactions_view(self, uid):
		return [self.get_tweet(twid) for twid in self.db.get_user_interactions(uid)]

	# users

	def get_profile(self, uid):
		if uid not in self.db.profiles:
			return None
		p = self.db.profiles[uid].copy()
		p["user_id_str"] = str(uid)
		p["observer"] = uid in self.db.observers
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

def histogram_from_dates(dates, name):
	histogram = {}
	zeroes = [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
	for date in dates:
		histogram.setdefault(date.year, zeroes[:])[date.month-1] += 1
	if not histogram:
		return None
	min_year = min(histogram.keys())
	max_year = max(histogram.keys())
	max_tweets = max(max(row) for row in histogram.values())
	histogram = [(year, histogram.get(year, zeroes)) for year in range(max_year, min_year-1, -1)]
	return {
		"name": name,
		"max_tweets": max_tweets,
		"histogram": histogram
	}

def paginated_tweets(response):
	def tweet_date(tweet):
		if "created_at" in tweet:
			return datetime.datetime.strptime(tweet["created_at"], "%a %b %d %H:%M:%S %z %Y")
		else:
			return datetime.datetime.fromtimestamp(((int(tweet["id_str"])>>22) + 1288834974657) / 1000.0)

	if "tweets" not in response:
		# profile2 query can return either tweets or profiles
		return response
	q = dict(request.query.decode())
	tweets = response["tweets"]
	dates = []
	for tweet in tweets:
		if tweet:
			dates.append(tweet_date(tweet))
	histogram = histogram_from_dates(dates, "ot")
	if not histogram:
		return response
	response["histograms"] = [histogram]
	qfrom = int(q.get("from", 0))
	quntil = int(q.get("until", 100000000 + time.time()*1000))
	response["tweets"] = [
		tweet for tweet in response["tweets"]
		if not tweet or qfrom <= tweet_date(tweet).timestamp()*1000 < quntil]
	response["tweets"] = response["tweets"][:500]
	return response

@route('/api/profile/<uid:int>')
def profile(uid):
	return paginated_tweets({
		"topProfile": ca.get_profile(uid),
		"tweets": ca.profile_view(uid)
	})

@route('/api/profile2/<who>')
def profile2(who):
	try: uid = int(who)
	except: pass
	else: return profile(uid)

	uids = db.user_by_handle.get(who, set())
	if len(uids) == 1:
		uid, = uids
		return profile(uid)
	else:
		return paginated_tweets({
			"profiles": [ca.get_profile(uid) for uid in uids]
		})

@route('/api/replies/<uid:int>')
def replies(uid):
	return paginated_tweets({
		"topProfile": ca.get_profile(uid),
		"tweets": ca.with_replies_view(uid)
	})

@route('/api/media/<uid:int>')
def media(uid):
	return paginated_tweets({
		"topProfile": ca.get_profile(uid),
		"tweets": ca.media_view(uid)
	})

@route('/api/likes/<uid:int>')
def likes(uid):
	return paginated_tweets({
		"topProfile": ca.get_profile(uid),
		"tweets": ca.likes_view(uid)
	})

@route('/api/bookmarks/<uid:int>')
def bookmarks(uid):
	return paginated_tweets({
		"topProfile": ca.get_profile(uid),
		"tweets": ca.bookmarks_view(uid)
	})

@route('/api/interactions/<uid:int>')
def interactions(uid):
	return paginated_tweets({
		"topProfile": ca.get_profile(uid),
		"tweets": ca.interactions_view(uid)
	})

@route('/api/followers/<uid:int>')
def followers(uid):
	return {
		"topProfile": ca.get_profile(uid),
		"profiles": ca.followers(uid)[:300]
	}

@route('/api/following/<uid:int>')
def following(uid):
	return {
		"topProfile": ca.get_profile(uid),
		"profiles": ca.following(uid)[:300]
	}

@route('/api/everyone')
def everyone():
	return {"profiles": ca.everyone()}

@route('/fonts/<path:path>')
def resources_20230628(path):
	return static_file(path, root=server_path+'/static/20230628/fonts')

@route('/responsive-web/<path:path>')
def resources_20230628(path):
	return static_file(path, root=server_path+'/static/20230628/responsive-web')

@route('/p/<path:path>')
def preact_js(path):
	r = static_file(path, root=server_path+'/node_modules/preact/')
	if isinstance(r, HTTPError) and path == "dist/preact.mjs":
		# fall back to bundled preact copy
		r = static_file('preact.mjs', root=server_path+'/static')
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
		response = static_file(os.path.basename(item.path), root=os.path.dirname(item.path), mimetype=getattr(item, "mime", "auto"))
	elif isinstance(item, InZip):
		with item.open() as f:
			response = static_blob(f.read(), item.mime)
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
	return static_file(name+'.js', root=server_path+'/static')

@route('/favicon.ico')
def favicon():
	return static_file('favicon.ico', root=server_path+'/static')

@route('/')
@route('/<who>')
@route('/everyone')
@route('/thread/<twid:int>')
@route('/profile/<who>')
@route('/profile/<who>/with_replies')
@route('/profile/<who>/media')
@route('/profile/<who>/likes')
@route('/profile/<who>/bookmarks')
@route('/profile/<who>/interactions')
@route('/profile/<who>/followers')
@route('/profile/<who>/following')
def index(**args):
	return static_file('index.html', root=server_path+'/static')

run()
