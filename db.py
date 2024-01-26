import sys, json, os, base64, os.path, re, zipfile, mimetypes
import datetime
import seqalign
from urllib.parse import urlparse, urlunparse, parse_qs, unquote
from har import HarStore, OnDisk, InZip, InMemory

class Sizes:
	def __init__(self, sizes):
		self.sizes = sizes
		self.by_name = {}
		for i, (w, h, *names) in enumerate(sizes):
			for name in names:
				self.by_name[name] = (i, w, h)

	def valid_name(self, size):
		return size in self.by_name

media_sizes = Sizes([
	(64, 64, "tiny"),
	(120, 120, "120x120"),
	(240, 240, "240x240"),
	(360, 360, "360x360"),
	(680, 680, "small"),
	(900, 900, "900x900"),
	(1200, 1200, "medium"),
	(2048, 2048, "large"),
	(4096, 4096, "4096x4096", "orig")
])

profile_images_sizes = Sizes([
	(24, 24, "_mini"),
	(48, 48, "_normal"),
	(73, 73, "_bigger"),
	(96, 96, "_x96"),
	(128, 128, "_reasonably_small"),
	(200, 200, "_200x200"),
	(400, 400, "_400x400"),
	(4096, 4096, "") # assumed maximum
])

profile_banners_sizes = Sizes([ # aspect ratio 3:1
	(300, 100, "/300x100"),
	(600, 200, "/600x200"),
	(1080, 360, "/1080x360"),
	(1500, 500, "/1500x500"),
	(4096, 4096, "")
])

no_sizes = Sizes([
	(None, None, None)
])

def decode_twimg(orig_url):
	url = urlparse(orig_url)
	if url.netloc == "abs.twimg.com":
		assert url.path == "" or url.path[0] == "/"
		base = url.netloc + url.path
		return base, (None, None), (None, None)

	elif url.netloc == "video.twimg.com":
		if url.path.startswith("/ext_tw_video/"):
			m = re.fullmatch(r"/ext_tw_video/[0-9]+/p(?:r|u)/(?:pl|vid(?:/avc1)?/[0-9]+x[0-9]+)/([A-Za-z0-9_-]+)\.(mp4|m3u8)", url.path)
			assert m, url.path
			base = "{}/{}.{}".format(url.netloc, m.group(1), m.group(2))

		elif url.path.startswith("/tweet_video/"):
			m = re.fullmatch(r"/tweet_video/([A-Za-z0-9_-]+)\.(mp4)", url.path)
			assert m, url.path
			base = "{}/{}.{}".format(url.netloc, m.group(1), m.group(2))

		elif url.path.startswith("/amplify_video/"):
			m = re.fullmatch(r"/amplify_video/[0-9]+/(?:pl|vid(?:/avc1)?/[0-9]+x[0-9]+)/([A-Za-z0-9_-]+)\.(mp4|m3u8)", url.path)
			assert m, url.path
			base = "{}/{}.{}".format(url.netloc, m.group(1), m.group(2))

		else:
			assert False, url.path

		return base, (None, None), (None, None)

	assert url.netloc in ("pbs.twimg.com", ""), orig_url

	query = parse_qs(url.query)
	assert all(len(values)==1 for values in query.values())
	query = {k: v[0] for k, v in query.items()}

	ext = None
	size = None
	sizes = media_sizes
	fullres_fmt = "{base}?format={ext}&name=orig"

	if url.path.startswith("/profile_images/"):
		# commented out because some twitter users set their profile picture before twitter renamed images to a random letter string
		# m = re.fullmatch(r"/profile_images/([0-9]+)/([A-Za-z0-9_-]+?)(_(normal|bigger|x96|reasonably_small|mini|200x200|400x400))?\.([A-Za-z0-9]{1,5})", url.path)
		m = re.fullmatch(r"(/profile_images/([0-9]+)/(.+?))(_(normal|bigger|x96|reasonably_small|mini|200x200|400x400))?\.([A-Za-z0-9]{1,5})", url.path)
		assert m, url.path
		size = m.group(4) or ""
		ext = m.group(6)
		sizes = profile_images_sizes
		fullres_fmt = "{base}.{ext}"
		default_size = ""
		assert not query, query

	elif url.path.startswith("/profile_banners/"):
		m = re.fullmatch(r"(/profile_banners/([0-9]+)/([0-9]+))(/(300x100|600x200|1080x360|1500x500))?", url.path)
		assert m, url.path
		size = m.group(4) or ""
		sizes = profile_banners_sizes
		fullres_fmt = "{base}"
		default_size = ""
		assert not query, query

	elif url.path.startswith("/media/"):
		m = re.fullmatch(r"(/media/([A-Za-z0-9_-]+))(\.([A-Za-z0-9]{1,5}))?(:([a-z0-9_]+))?", url.path)
		assert m, url.path
		ext = m.group(4)
		size = m.group(5)
		default_size = "medium" # sometimes

	elif url.path.startswith("/amplify_video_thumb/"):
		m = re.fullmatch(r"(/amplify_video_thumb/([0-9]+)/img/([A-Za-z0-9_-]+))(\.([A-Za-z0-9]{1,5}))?", url.path)
		assert m, url.path
		ext = m.group(5)
		default_size = "medium" # maybe

	elif url.path.startswith("/ext_tw_video_thumb/"):
		m = re.fullmatch(r"(/ext_tw_video_thumb/([0-9]+)/p[ur]/img/([A-Za-z0-9_-]+))(\.([A-Za-z0-9]{1,5}))?", url.path)
		assert m, url.path
		ext = m.group(5)
		default_size = "medium"

	elif url.path.startswith("/tweet_video_thumb/"):
		m = re.fullmatch(r"(/tweet_video_thumb/([A-Za-z0-9_-]+))(\.([A-Za-z0-9]{1,5}))?", url.path)
		assert m, url.path
		ext = m.group(4)
		default_size = "medium" # probably

	elif url.path.startswith("/card_img/"):
		m = re.fullmatch(r"(/card_img/([0-9]+)/([A-Za-z0-9_-]+))", url.path)
		assert m, url.path
		default_size = None # won't load without size

	elif url.path.startswith("/semantic_core_img/"):
		m = re.fullmatch(r"(/semantic_core_img/([0-9]+)/([A-Za-z0-9_-]+))", url.path)
		assert m, url.path
		default_size = None # won't load without size

	elif url.path.startswith("/ad_img/"):
		m = re.fullmatch(r"(/ad_img/([0-9]+)/([A-Za-z0-9_-]+))", url.path)
		assert m, url.path
		default_size = None # won't load without size

	elif orig_url == "https://pbs.twimg.com/static/dmca/video-preview-img.png":
		m = re.fullmatch(r"(/static/.*)", url.path)
		sizes = no_sizes
		default_size = None

	else:
		assert False, orig_url

	base = m.group(1)

	if "format" in query:
		assert not ext, orig_url
		ext = query.pop("format")
		assert ext is None or ext in ("jpg", "png"), ext
	elif ext and ext.lower() == "jpeg":
		ext = "jpg"

	if "name" in query:
		assert not size, orig_url
		size = query.pop("name")

	size = size or default_size

	assert size is None or sizes.valid_name(size), (orig_url, size, sizes)
	assert ext is None or ext.lower() in ("jpg", "jpeg", "png", "gif"), ext # more allowed when part of filename
	assert not query, orig_url
	fullres = "https://pbs.twimg.com"+fullres_fmt.format(base=base, ext=ext, size=size)

	return base, (ext, size), (sizes, fullres)

class ImageSet:
	def __init__(self):
		self.entries = []
		self.have_largest = False # TODO

	def add(self, blob, variant, image_set_info):
		ext, variant_name = variant

		# assign at first opportunity
		if hasattr(self, "sizes"): assert self.sizes == image_set_info[0]
		if hasattr(self, "fullres"): assert self.fullres == image_set_info[1]
		self.sizes, self.fullres = image_set_info

		self.entries.append((ext, variant_name, blob))
		self.entries.sort(key=lambda ext_variant_blob:
			self.sizes.by_name[ext_variant_blob[1]][0])

	def get_variant(self, ext, variant_name):
		if ext:
			entries = [entry for entry in self.entries if entry[0] == ext]
		else:
			entries = self.entries
		if not entries:
			return None, False
		for _, entry_variant_name, blob, *_ in entries:
			if variant_name == entry_variant_name:
				return blob, True
		return entries[-1][2], self.have_largest

class MediaStore:
	def __init__(self):
		self.media_by_url = {}
		self.media_by_name = {}

	# add images

	def add_from_archive(self, fs, tweets_media):
		r = re.compile(r"(\d+)-([A-Za-z0-9_\-]+)\.(.*)")
		for media_fname in fs.listdir(tweets_media):
			m = r.match(media_fname)
			if not m:
				print("what about", media_fname)
				continue
			if m.group(3) == "mp4":
				cache_key = "video.twimg.com/" + m.group(2) + ".mp4"
			else:
				cache_key = "/media/"+m.group(2)
			imageset = self.media_by_url.setdefault(cache_key, ImageSet())
			fmt = m.group(3)
			path = tweets_media+"/"+media_fname
			fullres = "https://pbs.twimg.com{}?format={}&name=orig".format(cache_key, fmt)
			if isinstance(fs, ZipFS):
				item = InZip(fs.zipf, path)
				item.mime = mimetypes.guess_type(path)
			else:
				item = OnDisk(path)
			imageset.add(item, (fmt, "medium"), (media_sizes, fullres))

	def add_http_snapshot(self, url, item):
		cache_key, variant, image_set_info = decode_twimg(url)
		imageset = self.media_by_url.setdefault(cache_key, ImageSet())
		imageset.add(item, variant, image_set_info)

	# check store

	def lookup(self, url):
		if url is None:
			return None, False
		cache_key, (fmt, variant_name), (sizes, _) = decode_twimg(url)
		imageset = self.media_by_url.get(cache_key, None)
		if imageset:
			return imageset.get_variant(fmt, variant_name)
		return None, False

# replace urls in tweet/user objects

def urlmap_list(urlmap, f, l):
	l2 = []
	any_patched = False
	for m in l:
		m2 = f(urlmap, m)
		if m2:
			l2.append(m2)
			any_patched = True
		else:
			l2.append(m)
	if any_patched:
		return l2

def urlmap_variant(urlmap, variant):
	if "url" in variant:
		url = variant["url"]
		url2 = urlmap(url)
		if url != url2:
			v = variant.copy()
			v["url"] = url2
			return v

def urlmap_variants(urlmap, variants):
	return urlmap_list(urlmap, urlmap_variant, variants)

def urlmap_media(urlmap, media):
	m = None
	if "media_url_https" in media:
		url = media["media_url_https"]
		url2 = urlmap(url)
		if url != url2:
			m = media.copy()
			m["media_url_https"] = url2
	if "video_info" in media and "variants" in media["video_info"]:
		v2 = urlmap_variants(urlmap, media["video_info"]["variants"])
		if v2:
			vi = media["video_info"].copy()
			vi["variants"] = v2
			if m is None:
				m = media.copy()
			m["video_info"] = vi
	return m

def urlmap_media_list(urlmap, media_list):
	return urlmap_list(urlmap, urlmap_media, media_list)

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

class NativeFS:
	def exists(self, path): return os.path.exists(path)
	def open(self, *args, **kwargs): return open(*args, **kwargs)
	def getmtime(self, path): return os.path.getmtime(path)
	def listdir(self, path): return os.listdir(path)

class ZipFS:
	def __init__(self, zipf):
		self.zipf = zipf
	def exists(self, path):
		try: self.zipf.getinfo(path)
		except KeyError: return False
		return True
	def open(self, *args, **kwargs):
		return self.zipf.open(*args, **kwargs)
	def getmtime(self, path):
		# path is ignored
		return os.path.getmtime(self.zipf.filename)
	def listdir(self, path):
		if not path.endswith("/"):
			path += "/"
		for name in self.zipf.namelist():
			if name.startswith(path) and name != path:
				yield name[len(path):]

def unscramble(likes):
	class Node:
		capacity = 10
		def __init__(self, index, count):
			self.index = index
			self.count = count
			self.children = []

	n = len(likes)
	new_likes = [None] * len(likes)

	queue = []
	for i in range(0, n, 25):
		ntweets = min(n-i, 25)
		child = Node(i, ntweets)
		if queue:
			parent = queue[0]
			parent.children.append(child)
			if len(parent.children) == parent.capacity:
				queue.pop(0)
		else:
			root = child
			root.capacity = 9 # whyever
		queue.append(child)

	i = 0
	def visit(node):
		nonlocal i
		for j in range(node.count):
			new_likes[node.index + j] = likes[i]
			i += 1
		for child in node.children:
			visit(child)
	visit(root)

	return new_likes

class DB:
	def __init__(self):
		self.tweets = {}
		self.profiles = {}
		self.followers = {} # could be part of .profiles
		self.followings = {} # could be part of .profiles
		self.by_user = {}
		self.user_by_handle = {}
		self.media = MediaStore()
		self.har = HarStore("harstore")
		self.likes_snapshots = {}
		self.likes_sorted = {}
		self.likes_unsorted = {}
		self.bookmarks_map = {}
		self.bookmarks_sorted = {}
		self.interactions_sorted = {}
		self.observers = set()
		self.conversations = {}

		# context
		self.time = None
		self.uid = None

	def sort_profiles(self):
		# collect by user
		for twid, tweet in self.tweets.items():
			uid = tweet.get("user_id_str", None)
			if uid is not None:
				self.by_user.setdefault(int(uid), []).append(twid)

		# tweets in reverse chronological order
		for tids in self.by_user.values():
			tids[:] = set(tids)
			tids.sort(key=lambda twid: -twid)

		# likes in reverse chronological order
		for uid, likes_snapshots in self.likes_snapshots.items():
			l = seqalign.align(
				sorted(likes_snapshots, key=lambda snap: -snap.time),
				evid_lower_bound_for_itid=lambda twid: ((twid >> 22) + 1288834974657) << 20
			)

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
		for uid, likes in self.likes_sorted.items():
			if uid in self.observers:
				for likeid, twid in likes:
					if twid in self.tweets:
						tweet = self.tweets[twid]
						if "user_id_str" in tweet:
							u = int(tweet["user_id_str"])
							self.interactions_sorted.setdefault(u, []).append(twid)

		# interactions in reverse chronological order
		for tids in self.interactions_sorted.values():
			tids[:] = set(tids)
			tids.sort(key=lambda twid: -twid)

		# sort dm messages
		for c in self.conversations.values():
			c["messages"].sort(key=lambda m: -int(m.get("messageCreate", {}).get("id", 0)))

		# generally all tweets in a conversation need to belong to the same circle
		for twid, tweet in self.tweets.items():
			if "circle" in tweet:
				continue
			if "conversation_id_str" in tweet:
				ctwid = int(tweet["conversation_id_str"])
				ctweet = self.tweets.get(ctwid, None)
				if ctweet:
					if "limited_actions" in ctweet and "limited_actions" not in tweet:
						print("inferred that", twid, "must have limited actions")
						tweet["limited_actions"] = ctweet["limited_actions"]
					if "circle" in ctweet and "circle" not in tweet:
						print("inferred that", twid, "must belong to", ctweet["circle"]["screen_name"]+"'s", "circle")
						tweet["circle"] = ctweet["circle"]
					if tweet.get("limited_actions", None) == "limit_trusted_friends_tweet" and "circle" not in ctweet:
						# the circle is generally determined by OP
						if "user_id_str" in ctweet:
							user = self.profiles.get(int(ctweet["user_id_str"]), None)
							if user:
								tweet["circle"] = ctweet["circle"] = {
									"screen_name": user["screen_name"],
									"user": user["name"]
								}
								print("inferred that", twid, "must belong to", user["screen_name"]+"'s", "circle")

	# queries

	def get_user_tweets(self, uid):
		pinned_tweet = [int(twid_str) for twid_str in self.profiles.get(uid, {}).get("pinned_tweet_ids_str", [])]
		regular_tweets = [twid for twid in self.by_user.get(uid, []) if
			"in_reply_to_status_id_str" not in self.tweets.get(twid, {})
		]
		return pinned_tweet + regular_tweets

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

	def search(self, query):
		# naive implementation
		words = query.split(" ")
		return {
			twid for twid, tweet in self.tweets.items()
			# 1. match full-text
			# 2. match media urls
			if all(word in tweet.get("full_text", "") for word in words)
			or any(query in media["media_url_https"] for media in tweet.get("extended_entities", {}).get("media", []))
		}

	# twitter archives

	def load_with_prefix(self, fs, fname, expected_prefix):
		with fs.open(os.path.join(fs.base, fname)) as f:
			prefix = f.read(len(expected_prefix))
			if isinstance(prefix, bytes): prefix = prefix.decode("utf-8")
			assert prefix == expected_prefix, (prefix, expected_prefix)
			return json.load(f)

	def load(self, base):
		if not isinstance(base, str):
			fs = ZipFS(base)
			base = ""
		else:
			fs = NativeFS()

		if fs.exists(os.path.join(base, "data", "tweets.js")):
			# browsable archives from ~2022
			base = os.path.join(base, "data")
			fs.base = base
			tweets = self.load_with_prefix(fs, "tweets.js", "window.YTD.tweets.part0 = ")
			tweets_media = os.path.join(base, "tweets_media")

		elif fs.exists(os.path.join(base, "data", "tweet.js")):
			# browsable archives from ~2020
			base = os.path.join(base, "data")
			fs.base = base
			tweets = self.load_with_prefix(fs, "tweet.js", "window.YTD.tweet.part0 = ")
			tweets_media = os.path.join(base, "tweet_media")

		elif fs.exists(os.path.join(base, "data", "js", "tweet_index.js")):
			# browsable archives from ~2019
			fs.base = base
			self.load_2019(fs)
			return

		elif fs.exists(os.path.join(base, "tweet.js")):
			# raw archives from ~2018
			fs.base = base
			tweets = self.load_with_prefix(fs, "tweet.js", "window.YTD.tweet.part0 = ")
			tweets_media = os.path.join(base, "tweet_media")
			tweets_media = None # the filenames don't allow any association back to their tweets



		likes = self.load_with_prefix(fs, "like.js", "window.YTD.like.part0 = ")
		account = self.load_with_prefix(fs, "account.js", "window.YTD.account.part0 = ")[0]["account"]
		profile = self.load_with_prefix(fs, "profile.js", "window.YTD.profile.part0 = ")[0]["profile"]
		uid = account["accountId"]

		if fs.exists(os.path.join(base, "manifest.js")):
			manifest = self.load_with_prefix(fs, "manifest.js", "window.__THAR_CONFIG = ")
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

		likes = unscramble(likes)

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
				if "full_text" in self.tweets[twid]:
					continue
				self.tweets[twid].update(fake_tweet)
			else:
				self.tweets[twid] = fake_tweet

		snapshot = seqalign.Items(like_twids)
		snapshot.time = self.time
		self.likes_snapshots.setdefault(self.uid, []).append(snapshot)

		# no merging happening yet
		conversations = self.load_with_prefix(fs, "direct-messages.js", "window.YTD.direct_messages.part0 = ")
		conversations += self.load_with_prefix(fs, "direct-messages-group.js", "window.YTD.direct_messages_group.part0 = ")

		if False: # validate format
			mckeys_g = set("reactions urls text mediaUrls senderId id createdAt".split(" "))
			mckeys = mckeys_g | {"recipientId"}

			for c in conversations:
				c = c["dmConversation"]
				for m in c["messages"]:
					assert len(m) == 1, m
					mty, = m.keys()

					if mty == "messageCreate":
						mc = m["messageCreate"]
						is_group = "-" not in c["conversationId"]
						assert set(mc.keys()) == (mckeys_g if is_group else mckeys), mc

					elif mty == "joinConversation":
						mjc = m["joinConversation"]
						assert set(mjc.keys()) == {'initiatingUserId', 'participantsSnapshot', 'createdAt'}

					elif mty == "participantsLeave":
						mpl = m["participantsLeave"]
						assert set(mpl.keys()) == {'userIds', 'createdAt'}

					else:
						assert False, m

		for c in conversations:
			# sometimes a conversation is split over multiple entries in the array in the json
			# but the conversationId remains the same
			c = c["dmConversation"]
			cid = c["conversationId"]
			ic = self.conversations.setdefault(cid, {
				"messages": [],
				"message_ids": set()
			})
			icm = ic["messages"]
			icmi = ic["message_ids"]
			for message in c["messages"]:
				try:
					mid = int(message["messageCreate"]["id"])
				except:
					continue
				if mid in icmi:
					continue
				icm.append(message)
				icmi.add(mid)

		if tweets_media:
			self.media.add_from_archive(fs, tweets_media)

	def load_2019(self, fs):
		payload_details = self.load_with_prefix(fs, "data/js/payload_details.js", "var payload_details = ")
		# ignore payload_details["tweets"]
		# ignore payload_details["lang"]
		if "created_at" in payload_details:
			generation_date = payload_details["created_at"] # 2019-04-30 23:59:59 +0000
			generation_date = datetime.datetime.strptime(generation_date, "%Y-%m-%d %H:%M:%S %z")
			self.time = generation_date.timestamp() * 1000
		else:
			self.time = fs.getmtime(fs.base) * 1000

		user_details = self.load_with_prefix(fs, "data/js/user_details.js", "var user_details = ")
		# ignore user_details["location"]
		# ignore user_details["created_at"]
		uid = user_details["id"]
		self.uid = int(uid)
		user = {
			"screen_name": user_details["screen_name"],
			"name": user_details["full_name"],
			"description": user_details["bio"],
			"user_id_str": uid
		}
		self.observers.add(int(uid))
		self.add_legacy_user(user, uid)

		tweet_index = self.load_with_prefix(fs, "data/js/tweet_index.js", "var tweet_index = ")
		known_keys = {
			"source", "entities", "geo", "id_str", "text", "id", "created_at", "user",
			"in_reply_to_screen_name",
			"in_reply_to_status_id",
			"in_reply_to_status_id_str",
			"in_reply_to_user_id",
			"in_reply_to_user_id_str"
		}
		for chunk in tweet_index:
			# ignore chunk["year"]
			# ignore chunk["month"]
			# ignore chunk["tweet_count"]
			fname = chunk["file_name"]
			varname = "Grailbird.data.{} = ".format(chunk["var_name"])
			tweets = self.load_with_prefix(fs, fname, varname)
			for tweet in tweets:
				retweeted_status = tweet.pop("retweeted_status", None)
				unknown_keys = set(tweet.keys()) - known_keys
				assert not unknown_keys, unknown_keys

				if retweeted_status:
					rtid = int(retweeted_status["id_str"])
					retweeted_status["original_id"] = rtid
					self.add_legacy_tweet_2019(retweeted_status)
					tweet["original_id"] = rtid
					self.add_legacy_tweet_2019(tweet)
				else:
					tid = int(tweet["id_str"])
					tweet["original_id"] = tid
					self.add_legacy_tweet_2019(tweet)

	# general loading

	def add_legacy_tweet(self, tweet):
		twid = int(tweet["id_str"])
		bookmarked = tweet.pop("bookmarked", False)
		favorited = tweet.pop("favorited", False)
		retweeted = tweet.pop("retweeted", False)
		if "in_reply_to_status_id_str" in tweet:
			reply_to_status = tweet["in_reply_to_status_id_str"]
			reply_to_user = tweet["in_reply_to_user_id_str"]
			reply_to_tweet = self.tweets.setdefault(int(reply_to_status), {"id_str": reply_to_status})
			reply_to_tweet["user_id_str"] = reply_to_user
			reply_to_tweet.setdefault("original_id", int(reply_to_status)) # UI generally doesn't let one reply to a RT
			reply_to_screen_name = tweet.get("in_reply_to_screen_name", None)
			if reply_to_screen_name:
				self.profiles.setdefault(int(reply_to_user), {})["screen_name"] = reply_to_screen_name
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

	def add_legacy_tweet_2019(self, tweet):
		user = tweet.pop("user", None)
		if user:
			self.add_legacy_user(user, user["id_str"])
			tweet["user_id_str"] = user["id_str"]

		# rewrite date format
		if "created_at" in tweet:
			created_at = tweet["created_at"]
			created_at = datetime.datetime.strptime(created_at, "%Y-%m-%d %H:%M:%S %z")
			created_at = created_at.strftime("%a %b %d %H:%M:%S %z %Y")
			tweet["created_at"] = created_at

		tweet["full_text"] = tweet.pop("text")

		self.add_legacy_tweet(tweet)

	def add_legacy_user(self, user, uid):
		if user == {}: # in UsersVerifiedAvatars for example
			return
		uid = int(uid)
		#print("added @{}".format(user["screen_name"]))
		dbuser = self.profiles.setdefault(uid, {})
		dbuser.update(user)

		self.user_by_handle.setdefault(user["screen_name"], set()).add(uid)

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
		heuristically_circle_tweet = False
		tn = tweet.get("__typename", None)
		if tn == "TweetWithVisibilityResults":
			assert frozenset(tweet.keys()) in {
				frozenset({"__typename", "tweet", "limitedActionResults"}),
				frozenset({"__typename", "tweet", "tweetInterstitial"}),
				frozenset({"__typename", "tweet", "limitedActionResults", "tweetInterstitial"})
			}, json.dumps(tweet)
			heuristically_circle_tweet = "Circle" in json.dumps(tweet.get("limitedActionResults"))
			tweet = tweet["tweet"]
		elif tn == "TweetTombstone":
			return

		user = tweet["core"]["user_results"]["result"]
		card = tweet.pop("card", None)
		legacy = tweet["legacy"]
		if card:
			card = card["legacy"]
			assert card["name"] in ("player", "summary", "summary_large_image", "promo_image_convo", "poll2choice_text_only",
				"poll3choice_text_only", "poll4choice_text_only", "unified_card") or \
				card["name"].endswith(":live_event") or \
				card["name"].endswith(":audiospace"), (tweet, card, card["name"])
			card["binding_values"] = {
				keyvalue["key"]: keyvalue["value"]
				for keyvalue in card["binding_values"]
			}
			legacy["card"] = card

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

		# circle tweets
		if "trusted_friends_info_result" in tweet:
			# one step of normalization: if limited_actions=limit_trusted_friends_tweet was suppressed, add it back
			if "limited_actions" not in legacy:
				legacy["limited_actions"] = "limit_trusted_friends_tweet"

			# finally push trusted_friends_info_result down into legacy object, so it is stored in the db
			trusted_friends = tweet["trusted_friends_info_result"]
			assert trusted_friends["__typename"] == "ApiTrustedFriendsInfo"
			assert set(trusted_friends.keys()) == {"__typename", "owner_results"}
			trusted_friends = trusted_friends["owner_results"]
			assert set(trusted_friends.keys()) == {"result"}
			trusted_friends = trusted_friends["result"]
			assert trusted_friends["__typename"] == "User"
			assert set(trusted_friends.keys()) == {"__typename", "legacy"}
			trusted_friends = trusted_friends["legacy"]
			assert set(trusted_friends.keys()) == {"screen_name", "name"}

			assert "circle" not in legacy, "overwriting something"
			legacy["circle"] = trusted_friends

		elif legacy.get("limited_actions") != "limit_trusted_friends_tweet" and heuristically_circle_tweet:
			# close call
			print("no machine readable way to tell that", legacy["id_str"], "was a circle tweet")
			legacy["limited_actions"] = "limit_trusted_friends_tweet"

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
		elif ct == "TimelineTombstone":
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
			pass # this one is okay, sometimes, scrolling down a users profile will have some of their tweets marked with this

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
				entry = i["entry"]
				it = self.add_timeline_add_entry(entry["content"], entry.get("entryId", None), cursors)
				if it:
					it = (int(entry["sortIndex"]),) + it
				layout.append(it)
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
		uid = None
		if "twid" in cookies:
			uid = unquote(cookies["twid"])
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
		elif path.endswith("/UnfavoriteTweet"):
			pass
		elif path.endswith("/AudioSpaceById"):
			pass
		elif path.endswith("/CreateRetweet"):
			pass # todo
		elif path.endswith("/FollowersYouKnow"):
			pass # todo
		elif path.endswith("/CreateBookmark"):
			pass # todo
		elif path.endswith("/articleNudgeDomains"):
			pass # todo
		elif path.endswith("/useFetchProfileBlocks_profileExistsQuery"):
			pass # todo
		else:
			assert False, path

	def load_api(self, fname, item, context):
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
			if isinstance(item, InMemory) and item.data == "":
				print("empty   ", fname, path)
				return # why
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
				self.load_api(fname, item, context)

		if any_missing:
			print("\nfor firefox consider setting devtools.netmonitor.responseBodyLimit higher\n")

# gather inputs

paths = []

def add_file(path):
	ext = os.path.splitext(path)[1]
	if ext in (".zip", ".har"):
		paths.append(path)

def add_path(path):
	if os.path.isdir(path):
		is_archive = os.path.exists(os.path.join(path, "data")) or os.path.exists(os.path.join(path, "tweet.js"))
		if is_archive:
			paths.append(path)
		else:
			for fname in os.listdir(path):
				add_file(os.path.join(path, fname) if path != "." else fname)
	else:
		add_file(path)

def add_list(path):
	try:
		with open("exports.txt") as f:
			lines = f.readlines()
	except:
		return

	for l in lines:
		l = l.strip()
		if l and not l.startswith("#"):
			add_path(l)

if len(sys.argv) >= 2:
	for arg in sys.argv[1:]:
		add_path(arg)

else:
	add_list("exports.txt")
	add_path(".")

# archive data is broken for RTs so apply HAR later to overwrite that
paths.sort(key=lambda path: 1 if path.endswith(".har") else 0)

# load inputs

db = DB()

for path in paths:
	print(path)
	if path.endswith(".har"):
		db.har.add(path, skip_if_exists=True)
		db.load_har(path)
	elif path.endswith(".zip"):
		db.load(zipfile.ZipFile(path))
	else:
		db.load(path)

# post-processing

db.sort_profiles()

# print how many tweets by who are in the archive
z = [(len(v), db.profiles[k]["screen_name"] if k in db.profiles else str(k), k) for k, v in db.by_user.items()]
z.sort()
for count, name, uid in z:
	print("{:4d} {}".format(count, name))
