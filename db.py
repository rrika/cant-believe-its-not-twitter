import json, os, base64, os.path, re
import datetime
import seqalign
from urllib.parse import urlparse, urlunparse, parse_qs
from har import HarStore, OnDisk, InMemory

class MediaStore:
	def __init__(self):
		self.media_by_url = {}
		self.media_by_name = {}

	# add images

	def add_from_archive(self, tweet_media):
		r = re.compile(r"(\d+)-([A-Za-z0-9_\-]+)\.(.*)")
		for media_fname in os.listdir(tweet_media):
			m = r.match(media_fname)
			if not m:
				print("what about", media_fname)
				continue
			name = m.group(2)+"."+m.group(3)
			imageset = self.media_by_name.setdefault(name, [])
			#fmt = m.group(2)
			#size = "medium"
			path = tweet_media+"/"+media_fname
			#imageset.append((fmt, size, path))
			imageset.append(OnDisk(path))

	def add_http_snapshot(self, url, item):
		urlparts = urlparse(url)
		cleanurl = urlunparse(urlparts._replace(query=None, fragment=None))
		name = os.path.basename(urlparts.path)
		imageset = self.media_by_url.setdefault(cleanurl, [])
		imageset.append(item)

	# check store

	def lookup(self, url):
		urlparts = urlparse(url)
		cleanurl = urlunparse(urlparts._replace(query=None, fragment=None))
		noexturl = cleanurl.rsplit(".", 1)[0]
		name = os.path.basename(urlparts.path)
		imageset = (
			self.media_by_url.get(cleanurl, []) +
			self.media_by_url.get(noexturl, []) +
			self.media_by_name.get(name, []))
		if imageset:
			return imageset[0]

# replace urls in tweet/user objects

def urlmap_media(urlmap, media):
	if "media_url_https" in media:
		url = media["media_url_https"]
		url2 = urlmap(url)
		if url != url2:
			m = media.copy()
			m["media_url_https"] = url2
			return m

def urlmap_media_list(urlmap, media_list):
	l = []
	any_patched = False
	for m in media_list:
		m2 = urlmap_media(urlmap, m)
		if m2:
			l.append(m2)
			any_patched = True
		else:
			l.append(m)
	if any_patched:
		return l

def urlmap_entities(urlmap, entities):
	if "media" in entities:
		media_list = urlmap_media_list(urlmap, entities["media"])
		if media_list:
			entities = entities.copy()
			entities["media"] = media_list
			return entities

def urlmap_profile(urlmap, user):
	user = user.copy()
	for key in ("profile_image_url_https", "profile_banner_url"):
		if key in user:
			user[key] = urlmap(user[key])
	return user

class DB:
	def __init__(self):
		self.tweets = {}
		self.profiles = {}
		self.followers = {} # could be part of .profiles
		self.followings = {} # could be part of .profiles
		self.by_user = {}
		self.media = MediaStore()
		self.har = HarStore("harstore")
		self.likes_snapshots = {}
		self.likes_sorted = {}
		self.likes_unsorted = {}
		self.bookmarks_map = {}
		self.bookmarks_sorted = {}
		self.interactions_sorted = {}
		self.observers = set()

		# context
		self.time = None
		self.uid = None

	def sort_profiles(self):
		# tweets in reverse chronological order
		for tids in self.by_user.values():
			tids[:] = set(tids)
			tids.sort(key=lambda twid: -twid)

		# likes in reverse chronological order
		for uid, likes_snapshots in self.likes_snapshots.items():
			l = seqalign.align(sorted(likes_snapshots, key=lambda snap: -snap.time))

			# 
			have_twid = set()
			for sort_index, twid in l:
				tweet = self.tweets.get(twid, {})
				original_id = tweet.get("original_id", twid)
				have_twid.add(original_id)

			for twid in self.likes_unsorted.get(uid, []):
				tweet = self.tweets[twid]
				twid = tweet["original_id"]
				if tweet["original_id"] in have_twid:
					continue
				have_twid.add(twid)
				timestamp = (twid >> 22) + 1288834974657
				synthesized_like_id = timestamp << 20
				l.append((synthesized_like_id, twid))

			l.sort(key=lambda a: -a[0])
			l = [twid for sort_index, twid in l]
			self.likes_sorted[uid] = l

		# bookmarks in reverse chronological order
		for uid, bookmarks in self.bookmarks_map.items():
			l = sorted(bookmarks.items(), key=lambda a: -a[1])
			l = [twid for twid, sort_index in l]
			self.bookmarks_sorted[uid] = l

		# replies hint at followings
		for twid, tweet in self.tweets.items():
			if "in_reply_to_user_id_str" in tweet:
				a = int(tweet["user_id_str"])
				b = int(tweet["in_reply_to_user_id_str"])
				if b in self.profiles and self.profiles[b].get("protected", False):
					if a != b:
						self.add_follow(a, b)

		# likes are interactions
		def likes_are_interactions(uid, likes):
			if uid in self.observers:
				for twid in likes:
					if twid in self.tweets:
						tweet = self.tweets[twid]
						if "user_id_str" in tweet:
							u = int(tweet["user_id_str"])
							self.interactions_sorted.setdefault(u, []).append(twid)
		for uid, likes in self.likes_sorted.items():
			likes_are_interactions(uid, likes)
		for uid, likes in self.likes_unsorted.items():
			likes_are_interactions(uid, likes)

		# interactions in reverse chronological order
		for tids in self.interactions_sorted.values():
			tids[:] = set(tids)
			tids.sort(key=lambda twid: -twid)

	# queries

	def get_user_tweets(self, uid):
		return [twid for twid in self.by_user.get(uid, []) if
			"in_reply_to_status_id_str" not in self.tweets.get(twid, {})
		]

	def get_user_with_replies(self, uid):
		return self.by_user.get(uid, [])

	def get_user_media(self, uid):
		media_tweets = []
		for twid in self.by_user.get(uid, []):
			tweet = self.tweets.get(twid, {})
			if len(tweet.get("entities", {}).get("media", [])) == 0:
				continue
			otwid = tweet["original_id"]
			tweet = self.tweets.get(otwid, tweet)
			if int(tweet["user_id_str"]) != uid:
				continue
			media_tweets.append(twid)
		return media_tweets

	def get_user_likes(self, uid):
		return self.likes_sorted.get(uid, [])

	def get_user_interactions(self, uid):
		return self.interactions_sorted.get(uid, [])

	def get_user_bookmarks(self, uid):
		return self.bookmarks_sorted.get(uid, [])

	# twitter archives

	def load_with_prefix(self, base, fname, expected_prefix):
		with open(os.path.join(base, fname)) as f:
			prefix = f.read(len(expected_prefix))
			assert prefix == expected_prefix
			return json.load(f)

	def load(self, base):
		if os.path.exists(os.path.join(base, "data", "tweets.js")):
			# browsable archives from ~2022
			base = os.path.join(base, "data")
			tweets = self.load_with_prefix(base, "tweets.js", "window.YTD.tweets.part0 = ")
			tweets_media = os.path.join(base, "tweets_media")

		elif os.path.exists(os.path.join(base, "data", "tweet.js")):
			# browsable archives from ~2020
			base = os.path.join(base, "data")
			tweets = self.load_with_prefix(base, "tweet.js", "window.YTD.tweet.part0 = ")
			tweets_media = os.path.join(base, "tweet_media")

		elif os.path.exists(os.path.join(base, "data", "js", "tweet_index.js")):
			# browsable archives from ~2019
			print("unsupported archive format:", base)
			return

		elif os.path.exists(os.path.join(base, "tweet.js")):
			# raw archives from ~2018
			tweets = self.load_with_prefix(base, "tweet.js", "window.YTD.tweet.part0 = ")
			tweets_media = os.path.join(base, "tweet_media")
			tweets_media = None # the filenames don't allow any association back to their tweets

		likes = self.load_with_prefix(base, "like.js", "window.YTD.like.part0 = ")
		account = self.load_with_prefix(base, "account.js", "window.YTD.account.part0 = ")[0]["account"]
		profile = self.load_with_prefix(base, "profile.js", "window.YTD.profile.part0 = ")[0]["profile"]
		uid = account["accountId"]

		if os.path.exists(os.path.join(base, "manifest.js")):
			manifest = self.load_with_prefix(base, "manifest.js", "window.__THAR_CONFIG = ")
			generation_date = manifest["archiveInfo"]["generationDate"] # 2020-12-31T23:59:59.999Z
			generation_date = datetime.datetime.fromisoformat(generation_date)
			self.time = generation_date.timestamp() * 1000
		else:
			self.time = os.path.getmtime(base) * 1000

		self.uid = int(uid)

		user = {
			"screen_name": account["username"],
			"name": account["accountDisplayName"],
			"description": profile["description"]["bio"],
			"user_id_str": uid,
			#"followed_by":
			#"protected":
		}
		if "headerMediaUrl" in profile:
			user["profile_banner_url"] = profile["headerMediaUrl"]

		if "avatarMediaUrl" in profile:
			user["profile_image_url_https"] = profile["avatarMediaUrl"]

		self.observers.add(int(uid))
		self.add_legacy_user(user, uid)

		for i, entry in enumerate(tweets):
			tweet = entry.get("tweet", entry) # wrapped from ~2020 onwards
			for attr in [
				"in_reply_to_screen_name",
				"in_reply_to_status_id",
				"in_reply_to_status_id_str",
				"in_reply_to_user_id",
				"in_reply_to_user_id_str"
			]:
				if attr in tweet and tweet[attr] is None:
					del tweet[attr] # normalize old tweet format from 2018
			tweet["user_id_str"] = uid
			tweet["original_id"] = int(tweet["id_str"])
			self.add_legacy_tweet(tweet)

		like_twids = []

		for like in likes:
			like = like["like"]
			twid = int(like["tweetId"])
			like_twids.append(twid)
			if "fullText" not in like:
				continue
			#elif like["fullText"] == "You’re unable to view this Tweet because this account owner limits who can view their Tweets. {learnmore}":
			#	continue
			fake_tweet = {
				"full_text": like["fullText"],
				"id_str": like["tweetId"],
				"original_id": twid
			}
			if twid in self.tweets:
				continue
			self.tweets[twid] = fake_tweet

		snapshot = seqalign.Items(like_twids)
		snapshot.time = self.time
		self.likes_snapshots.setdefault(self.uid, []).append(snapshot)

		if tweets_media:
			self.media.add_from_archive(tweets_media)

	# general loading

	def add_legacy_tweet(self, tweet):
		twid = int(tweet["id_str"])
		bookmarked = tweet.pop("bookmarked", False)
		favorited = tweet.pop("favorited", False)
		retweeted = tweet.pop("retweeted", False)
		if twid in self.tweets:
			self.tweets[twid].update(tweet)
			dbtweet = self.tweets[twid]
		else:
			dbtweet = self.tweets[twid] = tweet
		if self.uid:
			observer = str(self.uid)
			if bookmarked:
				g = dbtweet.setdefault("bookmarkers", [])
				if observer not in g: g.append(observer)
			if favorited:
				g = dbtweet.setdefault("favoriters", [])
				if observer not in g: g.append(observer)
				self.likes_unsorted.setdefault(self.uid, set()).add(twid) # unknown like
			if retweeted:
				g = dbtweet.setdefault("retweeters", [])
				if observer not in g: g.append(observer)
		uid = int(tweet["user_id_str"])
		self.by_user.setdefault(uid, []).append(twid)

	def add_legacy_user(self, user, uid):
		if user == {}: # in UsersVerifiedAvatars for example
			return
		uid = int(uid)
		#print("added @{}".format(user["screen_name"]))
		dbuser = self.profiles.setdefault(uid, {})
		dbuser.update(user)

		if self.uid is not None and user.get("followed_by", False):
			self.add_follow(uid, self.uid)

	def add_user(self, user, give_timeline_v1=False, give_timeline_v2=False):
		if "legacy" in user:
			self.add_legacy_user(user["legacy"], user["rest_id"])
		if "timeline" in user:
			assert give_timeline_v1
			return user["timeline"]
		if "timeline_v2" in user:
			assert give_timeline_v2
			return user["timeline_v2"]

	def add_tweet(self, tweet):
		tn = tweet.get("__typename", None)
		if tn == "TweetWithVisibilityResults":
			tweet = tweet["tweet"]
		elif tn == "TweetTombstone":
			return

		user = tweet["core"]["user_results"]["result"]
		legacy = tweet["legacy"]

		# retweets
		rt = legacy.pop("retweeted_status_result", None)
		if rt:
			legacy["original_id"] = self.add_tweet(rt["result"])
		else:
			legacy["original_id"] = int(legacy["id_str"])

		# quote tweets
		quoted = tweet.get("quoted_status_result", None)
		if quoted:
			self.add_tweet(quoted["result"])

		# finish
		self.add_user(user)
		self.add_legacy_tweet(legacy)
		return legacy["original_id"]

	def add_follow(self, follower, following):
		assert follower != following
		self.followers.setdefault(following, set()).add(follower)
		self.followings.setdefault(follower, set()).add(following)

	def add_item_content(self, content, name, cursors=None):
		ct = content["__typename"]
		if ct == "TimelineUser":
			user = content["user_results"]["result"]
			self.add_user(user)
			return int(user["rest_id"])
		elif ct == "TimelineTweet":
			if "promotedMetadata" in content:
				return
			tweet_results = content["tweet_results"]
			if not tweet_results: # happens in /Likes
				assert content == {'itemType': 'TimelineTweet', '__typename': 'TimelineTweet', 'tweet_results': {}, 'tweetDisplayType': 'Tweet'}
				return
			tweet = tweet_results["result"]
			self.add_tweet(tweet)
			if tweet.get("__typename", None) == "TweetWithVisibilityResults":
				tweet = tweet["tweet"]
			if tweet.get("__typename", None) == "TweetTombstone":
				return None
			return int(tweet["rest_id"])
		elif ct == "TimelineTimelineCursor":
			# cursors for /TweetDetails take this path
			if cursors is not None:
				cursors.append((name, content))
		elif ct == "TimelineTweetComposer":
			pass
		else:
			assert False, ct

	def add_module_entry(self, entry, name):
		return self.add_item_content(entry["itemContent"], name)

	def add_module_item(self, item):
		name = item.get("entryId", None)
		return (None, name, self.add_module_entry(item["item"], name))

	def add_timeline_add_entry(self, item, name=None, cursors=None):
		et = item["entryType"]

		cei_component = item.get("clientEventInfo", {}).get("component", None)
		if cei_component == "suggest_promoted":
			return None # ad
		if cei_component == "related_tweet":
			return None # garbage
		if cei_component == "suggest_ranked_organic_tweet":
			return None # COMPUTER: thats too hard. heres some tweets i think are good.

		if et == "TimelineTimelineItem":
			return (name, self.add_item_content(item["itemContent"], name, cursors))
		elif et == "TimelineTimelineModule":
			return (name, [self.add_module_item(entry) for entry in item["items"]])
		elif et == "TimelineTimelineCursor":
			# cursors for /Likes take this path
			if cursors is not None:
				cursors.append((name, item))
		else:
			assert False, et

	def add_with_instructions(self, data):
		layout = []
		cursors = []
		ins = data["instructions"]
		for i in ins:
			t = i["type"]
			if t == "TimelineClearCache":
				pass
			elif t == "TimelineTerminateTimeline":
				pass
			elif t == "TimelineShowAlert":
				pass
			elif t == "TimelinePinEntry":
				pass
			elif t == "TimelineReplaceEntry":
				pass # todo
			elif t == "TimelineAddToModule":
				# i["moduleEntryId"]
				# i["prepend"]
				for modit in i["moduleItems"]:
					self.add_module_entry(modit["item"], modit["entryId"])
			elif t == "TimelineAddEntries":
				for entry in i["entries"]:
					it = self.add_timeline_add_entry(entry["content"], entry.get("entryId", None), cursors)
					if it:
						it = (int(entry["sortIndex"]),) + it
					layout.append(it)
			else:
				assert False, t
		return layout, cursors

	def add_list(self, list_):
		print("found list named", list_["name"])

	def get_query(self, context):
		if not context:
			return
		if "url" not in context:
			return
		url = urlparse(context["url"])
		return parse_qs(url.query)

	def get_gql_vars(self, context):
		q = self.get_query(context)
		if q and "variables" in q:
			return json.loads(q["variables"][0])

	def load_gql(self, path, data, context):
		self.time = context and context["timeStamp"]

		if context and context.get("cookies", None):
			cookies = {entry["name"]: entry["value"] for entry in context["cookies"]}
		else:
			cookies = {}
		uid = cookies.get("twid", None)
		if uid:
			uid = int(uid[2:])
		self.uid = uid
		if uid: self.observers.add(uid)

		if "data" not in data:
			return

		data = data["data"]
		if path.endswith("/GetUserClaims"):
			pass
		elif path.endswith("/DataSaverMode"):
			pass
		elif path.endswith("/CommunitiesTabBarItemQuery"):
			pass
		elif path.endswith("/ListPins"):
			viewer = data["viewer"]
			for list_ in viewer.get("pinned_lists", []):
				self.add_list(list_)
		elif path.endswith("/DMPinnedInboxQuery"):
			assert data == {"labeled_conversation_slice":{"items":[],"slice_info":{}}}
		elif path.endswith("/UserByRestId"):
			self.add_user(data["user"]["result"])
		elif path.endswith("/UserByScreenName"):
			self.add_user(data["user"]["result"])
		elif path.endswith("/HomeLatestTimeline"):
			self.add_with_instructions(data["home"]["home_timeline_urt"])
		elif path.endswith("/HomeTimeline"):
			self.add_with_instructions(data["home"]["home_timeline_urt"])
		elif path.endswith("/TweetDetail"):
			self.add_with_instructions(data["threaded_conversation_with_injections_v2"])
		elif path.endswith("/ProfileSpotlightsQuery"):
			#self.add_user(data["user_result_by_screen_name"]["result"])
			pass
		elif path.endswith("/UserTweets"):
			tweet_timeline = self.add_user(data["user"]["result"], give_timeline_v2=True)
			self.add_with_instructions(tweet_timeline["timeline"])
		elif path.endswith("/UserTweetsAndReplies"):
			tweet_timeline = self.add_user(data["user"]["result"], give_timeline_v2=True)
			self.add_with_instructions(tweet_timeline["timeline"])
		elif path.endswith("/UserMedia"):
			media_timeline = self.add_user(data["user"]["result"], give_timeline_v2=True)
			self.add_with_instructions(media_timeline["timeline"])
		elif path.endswith("/Likes"):
			gql_vars = self.get_gql_vars(context) or {}
			whose_likes = int(gql_vars["userId"])
			likes_timeline = self.add_user(data["user"]["result"], give_timeline_v2=True)
			layout, cursors = self.add_with_instructions(likes_timeline["timeline"])

			likes = []
			for entry in layout:
				if entry is None:
					continue # non-tweet timeline item
				sort_index, name, twid = entry
				if twid is None:
					continue # tweet deleted or on locked account
				assert isinstance(twid, int)
				likes.append((sort_index, twid))
			cursors = [(cname, cdata["value"]) for cname, cdata in cursors]

			snapshot = seqalign.Events(likes)
			snapshot.time = self.time
			snapshot.continue_from = gql_vars.get("cursor", None)

			snapshots = self.likes_snapshots.setdefault(whose_likes, [])
			snapshots.append(snapshot)

		elif path.endswith("/Bookmarks"):
			layout, cursors = self.add_with_instructions(data["bookmark_timeline_v2"]["timeline"])
			user_bookmarks = self.bookmarks_map.setdefault(uid, {})
			for entry in layout:
				if entry is None:
					continue # non-tweet timeline item
				sort_index, name, twid = entry
				if twid is None:
					continue # tweet deleted or on locked account
				assert isinstance(twid, int)
				user_bookmarks[twid] = max(sort_index, user_bookmarks.get(twid, sort_index))

		elif path.endswith("/Following"):
			gql_vars = self.get_gql_vars(context) or {}
			whose_followings = int(gql_vars["userId"])
			followings_timeline = self.add_user(data["user"]["result"], give_timeline_v1=True)
			layout, cursors = self.add_with_instructions(followings_timeline["timeline"])
			for entry in layout:
				if entry is None:
					continue
				sort_index, name, following_uid = entry
				self.add_follow(whose_followings, following_uid)

		elif path.endswith("/Followers"):
			gql_vars = self.get_gql_vars(context) or {}
			whose_followers = int(gql_vars["userId"])
			followers_timeline = self.add_user(data["user"]["result"], give_timeline_v1=True)
			layout, cursors = self.add_with_instructions(followers_timeline["timeline"])
			for entry in layout:
				if entry is None:
					continue
				sort_index, name, follower_uid = entry
				self.add_follow(follower_uid, whose_followers)

		elif path.endswith("/UsersVerifiedAvatars"):
			for result in data["usersResults"]:
				self.add_user(result["result"])
		elif path.endswith("/getAltTextPromptPreference"):
			assert data == {}
		elif path.endswith("/Favoriters"):
			self.add_with_instructions(data["favoriters_timeline"]["timeline"])
		elif path.endswith("/Retweeters"):
			self.add_with_instructions(data["retweeters_timeline"]["timeline"])
		elif path.endswith("/FetchDraftTweets"):
			assert data == {"viewer":{"draft_list":{"response_data":[]}}}
		elif path.endswith("/FetchScheduledTweets"):
			assert data == {"viewer":{"scheduled_tweet_list":[]}}
		elif path.endswith("/AuthenticatedUserTFLists"): # circles
			for circle in data["authenticated_user_trusted_friends_lists"]:
				print("found circle named", circle["name"], "with", circle["member_count"], "people")
		elif path.endswith("/CheckTweetForNudge"):
			assert data == {"create_nudge":{}}
		elif path.endswith("/CreateTweet"):
			self.add_tweet(data["create_tweet"]["tweet_results"]["result"])
		elif path.endswith("/UsersByRestIds"):
			for user in data["users"]:
				self.add_user(user)
		elif path.endswith("/SearchTimeline"):
			self.add_with_instructions(data["search_by_raw_query"]["search_timeline"]["timeline"])
		elif path.endswith("/FavoriteTweet"):
			pass
		elif path.endswith("/CreateRetweet"):
			pass # todo
		elif path.endswith("/FollowersYouKnow"):
			pass # todo
		elif path.endswith("/CreateBookmark"):
			pass # todo
		elif path.endswith("/articleNudgeDomains"):
			pass # todo
		else:
			assert False, path

	def load_api(self, item, context):
		url = context["url"]
		path = urlparse(url).path

		if path in (
			"/1.1/account/multi/list.json",
			"/1.1/account/multi/switch.json",
			"/1.1/account/settings.json",
			"/1.1/help/settings.json",
			"/live_pipeline/events",
		):
			return # not plain json

		if path in (
			"/1.1/live_pipeline/update_subscriptions",
			"/i/api/1.1/jot/",
			"/i/api/2/badge_count/badge_count.json",
			"/i/api/2/notifications/all.json",
			"/i/api/fleets/"
		):
			return # also not interesting for now

		if url.startswith("https://pbs.twimg.com/"):
			print("media   ", fname, path)
			self.media.add_http_snapshot(url, item)
			return

		try:
			data = json.load(item.open())
		except:
			print("not json", fname, path)
			return

		if url.startswith("https://twitter.com/i/api/graphql/"):
			print("adding  ", fname, path)
			self.load_gql(path, data, context)
		else:
			print("skipping", fname, path)

	def load_har(self, fname):
		lhar = self.har.load(fname)
		any_missing = False
		for entry in lhar["log"]["entries"]:
			url = entry["request"]["url"]
			if "video.twimg.com/ext_tw_video" in url:
				continue # firefox HAR says base64 encoding even though that's a lie
			response = entry["response"]["content"]
			if response:
				time = datetime.datetime.fromisoformat(entry["startedDateTime"])
				item = self.har.get_lhar_entry(entry)
				if not item:
					print("missing ", url)
					if "comment" in response:
						print(" ", response["comment"])
					any_missing = True
					continue
				context = {
					"url": url,
					"timeStamp": time.timestamp() * 1000,
					"cookies": entry["request"]["cookies"]
				}
				self.load_api(item, context)

		if any_missing:
			print("\nfor firefox consider setting devtools.netmonitor.responseBodyLimit higher\n")

db = DB()

try:
	archive_paths = []
	with open("exports.txt") as f:
		archive_paths = [l.strip() for l in f.readlines()]
finally:
	pass

for l in archive_paths:
	if l and not l.startswith("#"):
		print(l)
		db.load(l)

# archive data is broken for RTs so apply HAR later to overwrite that
for fname in os.listdir("."):
	if fname.endswith(".har"):
		db.har.add(fname, skip_if_exists=True)
		db.load_har(fname)

db.sort_profiles()

# print how many tweets by who are in the archive
z = [(len(v), db.profiles[k]["screen_name"], k) for k, v in db.by_user.items()]
z.sort()
for count, name, uid in z:
	print("{:4d} {}".format(count, name))
	p = db.profiles[uid]
