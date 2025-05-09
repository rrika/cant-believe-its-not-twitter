import sys, json, os, base64, os.path, re, zipfile, mimetypes, http.cookies
import datetime, importlib.util
import contextlib, tempfile, subprocess # for video reencoding
import seqalign
from urllib.parse import urlparse, urlunparse, parse_qs, unquote
from har import HarStore, OnDisk, InZip, InMemory, InWarc, read_warc

try:
	datetime.datetime.fromisoformat("2020-12-31T23:59:59.999Z")
	fromisoformat = datetime.datetime.fromisoformat
except:
	# cpython 3.9 and pypy 7.3.17 (using a 3.10 stdlib) struggle with the Z
	def fromisoformat(x):
		return datetime.datetime.fromisoformat(x.rstrip("Z"))

class TwitterCookie(http.cookies.SimpleCookie):

	# twitter has quotes in the middle of cookies, like
	# Cookie: remember_checked_on=1; g_state={\"i_p\":999999999,\"i_l\":3}; d_prefs=...

	LegalKeyChars  = r"\w\d!#%&'~_`><@,:/\$\*\+\-\.\^\|\)\(\?\}\{\="
	LegalValueChars = LegalKeyChars + r'\[\]'
	CookiePattern = re.compile(r"""
	    \s*                            # Optional whitespace at start of cookie
	    (?P<key>                       # Start of group 'key'
	    [""" + LegalKeyChars + r"""]+?   # Any word of at least one letter
	    )                              # End of group 'key'
	    (                              # Optional group: there may not be a value.
	    \s*=\s*                          # Equal Sign
	    (?P<val>                         # Start of group 'val'
	    "(?:[^\\"]|\\.)*"                  # Any doublequoted string
	    |                                  # or
	    \w{3},\s[\w\d\s-]{9,11}\s[\d:]{8}\sGMT  # Special case for "expires" attr
	    |                                  # or
	    [""" + LegalValueChars + r"""]     # Any word
	    [""" + LegalValueChars + r"""\"]*  # including with quotes in the middle
	    |                                  # or empty string
	    )                                # End of group 'val'
	    )?                             # End of optional value group
	    \s*                            # Any number of spaces.
	    (\s+|;|$)                      # Ending either at space, semicolon, or EOS.
	    """, re.ASCII | re.VERBOSE)    # re.ASCII may be removed if safe.

	def load(self, rawdata):
		return self._BaseCookie__parse_string(rawdata, self.CookiePattern)

def json_object_pairs_hook(p):
	return {
		sys.intern(k) if type(k) is str else k:
		sys.intern(v) if type(v) is str else v
		for k, v in p
	}

json_load_args = {"object_pairs_hook": json_object_pairs_hook}

dicts = {}

def intern_dict(d):
	if not d:
		return d
	f = frozenset(d)
	return dicts.setdefault(f, d)

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
	(626, 313, "/ipad"),
	(1080, 360, "/1080x360"),
	(1500, 500, "/1500x500"),
	(4096, 4096, "")
])

card_image_sizes = Sizes([
	(100, 100, "100x100"),
	(100, 100, "100x100_2"),
	(144, 144, "144x144"),
	(144, 144, "144x144_2"),
	(120, 120, "120x120"),
	(240, 240, "240x240"),
	(280, 150, "280x150"), # non-square
	(280, 280, "280x280"),
	(280, 280, "280x280_2"),
	(360, 360, "360x360"),
	(386, 202, "386x202"), # non-square
	(400, 400, "400x400"),
	(420, 420, "420x420_1"),
	(420, 420, "420x420_2"),
	(600, 314, "600x314"), # non-square
	(600, 600, "600x600"),
	(680, 680, "small"), # assume it means the same thing as in media_sizes
	(800, 320, "800x320_1"), # non-square
	(800, 419, "800x419"), # non-square
	(900, 900, "900x900"),
	(1000, 1000, "1000x1000"),
	(1200, 627, "1200x627"), # non-square
	(1200, 1200, "medium"), # assume it means the same thing as in media_sizes
	(2048, 2048, "2048x2048_2_exp"),
	(2048, 2048, "large"), # assume it means the same thing as in media_sizes
	(4096, 4096, "4096x4096", "orig")
])

no_sizes = Sizes([
	(None, None, None)
])

def decode_twimg(orig_url):
	url = urlparse(orig_url)
	if url.netloc == "abs.twimg.com" or orig_url in (
		"https://pbs.twimg.com/cards/player-placeholder.png",
		"https://pbs.twimg.com/lex/placeholder_live_nomargin.png"
	):
		assert url.path == "" or url.path[0] == "/"
		base = url.netloc + url.path
		return base, (None, None), (no_sizes, None)

	elif url.netloc in ("video.twimg.com", "video-ft.twimg.com", "video-cf.twimg.com"): # when are -ft and -cf used?
		if url.path.startswith("/ext_tw_video/"):
			#m = re.fullmatch(r"/ext_tw_video/[0-9]+/p(?:r|u)/(?:pl|vid(?:/avc1)?)(?:/[0-9]+x[0-9]+)?/([A-Za-z0-9_-]+)\.(mp4|m3u8)", url.path)
			m = re.fullmatch(r"/ext_tw_video/[0-9]+/.*/([A-Za-z0-9_-]+)\.(mp4|m4s|m3u8|ts)", url.path)
			assert m, url.path
			base = "{}/{}.{}".format(url.netloc, m.group(1), m.group(2))

		elif url.path.startswith("/tweet_video/"):
			m = re.fullmatch(r"/tweet_video/([A-Za-z0-9_-]+)\.(mp4)", url.path)
			assert m, url.path
			base = "{}/{}.{}".format(url.netloc, m.group(1), m.group(2))

		elif url.path.startswith("/subtitles/"):
			base = url.netloc + url.path # TODO

		elif url.path.startswith("/dm_gif/"):
			m = re.fullmatch(r"/dm_gif/([0-9]+)/([A-Za-z0-9_-]+)\.(mp4)", url.path)
			assert m, url.path
			base = url.netloc + url.path # TODO

		elif url.path.startswith("/dm_video/"):
			m = re.fullmatch(r"/dm_video/[0-9]+/.*/([A-Za-z0-9_-]+)\.(mp4|m4s|m3u8)", url.path)
			assert m, url.path
			base = url.netloc + url.path # TODO

		elif url.path.startswith("/amplify_video/"):
			#m = re.fullmatch(r"/amplify_video/[0-9]+/(?:pl|vid(?:/avc1)?/[0-9]+x[0-9]+)/([A-Za-z0-9_-]+)\.(mp4|m3u8)", url.path)
			m = re.fullmatch(r"/amplify_video/[0-9]+/.*/([A-Za-z0-9_-]+)\.(mp4|m4s|m3u8)", url.path)
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
		m = re.fullmatch(r"(/profile_images/([0-9]+)/(.+?))(_(normal|bigger|x96|reasonably_small|mini|200x200|400x400))?(\.([A-Za-z0-9]{1,5}))?", url.path)
		assert m, url.path
		size = m.group(4) or ""
		ext = m.group(7) # sometimes this is missing
		sizes = profile_images_sizes
		fullres_fmt = "{base}.{ext}"
		default_size = ""
		assert not query, query

	elif url.path.startswith("/profile_banners/"):
		m = re.fullmatch(r"(/profile_banners/([0-9]+)/([0-9]+))(/(300x100|600x200|1080x360|1500x500|ipad))?", url.path)
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
		size = m.group(6)
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
		sizes = card_image_sizes
		default_size = None # won't load without size

	elif url.path.startswith("/semantic_core_img/"):
		m = re.fullmatch(r"(/semantic_core_img/([0-9]+)/([A-Za-z0-9_-]+))", url.path)
		assert m, url.path
		default_size = None # won't load without size

	elif url.path.startswith("/ad_img/"):
		m = re.fullmatch(r"(/ad_img/([0-9]+)/([A-Za-z0-9_-]+))", url.path)
		assert m, url.path
		default_size = None # won't load without size

	elif url.path.startswith("/community_banner_img/"):
		m = re.fullmatch(r"(/community_banner_img/([0-9]+)/([A-Za-z0-9_-]+))", url.path)
		assert m, url.path
		sizes = media_sizes
		default_size = None # won't load without size

	elif url.path.startswith("/list_banner_img/"):
		m = re.fullmatch(r"(/list_banner_img/([0-9]+)/([A-Za-z0-9_-]+))", url.path)
		assert m, url.path
		sizes = media_sizes # guess
		default_size = None # won't load without size

	elif url.path.startswith("/dm_gif_preview/"):
		m = re.fullmatch(r"(/dm_gif_preview/([0-9]+)/([A-Za-z0-9_-]+))(\.([A-Za-z0-9]{1,5}))?", url.path)
		assert m, url.path
		ext = m.group(5)
		default_size = "small"

	elif url.path.startswith("/dm_video_preview/"):
		m = re.fullmatch(r"(/dm_video_preview/([0-9]+)/img/([A-Za-z0-9_\-]+))(\.([A-Za-z0-9]{1,5}))?", url.path)
		assert m, url.path
		ext = m.group(5)
		default_size = None

	elif url.path.startswith("/grok-img-share/"):
		m = re.fullmatch(r"/grok-img-share/([0-9]+)\.([A-Za-z0-9]{1,5})", url.path)
		assert m, url.path
		ext = m.group(2)
		sizes = no_sizes
		default_size = None

	elif orig_url == "https://pbs.twimg.com/static/dmca/video-preview-img.png" or \
	     orig_url == "https://pbs.twimg.com/static/dmca/dmca-med.jpg":

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
	assert ext is None or ext.lower() in ("jpg", "jpeg", "png", "gif", "bmp"), ext # more allowed when part of filename
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

class VideoSet:
	# logic is currently external, refactor this
	def __init__(self):
		self.entries = []

	def add(self, blob):
		self.entries.append(blob)

	def get_variant(self, *ignore):
		return self.entries[0], False

def merge_m3u8(m3u, get):
	with contextlib.ExitStack() as stack:
		rewritten = []
		def urlmap(url):
			_, ext = os.path.splitext(urlparse(url).path)
			chunk = get(url)
			if isinstance(chunk, OnDisk):
				return os.path.abspath(chunk.path)
			else:
				chunkfile = stack.enter_context(tempfile.NamedTemporaryFile(suffix=ext))
				with chunk.open() as f:
					chunkfile.write(f.read())
					chunkfile.flush()
				return chunkfile.name

		for line in m3u.splitlines():
			if m := re.match(r'#EXT-X-MAP:URI="(.*)"', line):
				rewritten.append('#EXT-X-MAP:URI="{}"'.format(urlmap(m.group(1))))
			elif line and not line.startswith("#"):
				rewritten.append(urlmap(line))
			else:
				rewritten.append(line)

		rewritten = "\n".join(rewritten) + "\n"
		with tempfile.NamedTemporaryFile(mode="w", suffix=".m3u8") as rewritten_m3u:
			rewritten_m3u.write(rewritten)
			rewritten_m3u.flush()
			#rewritten_m3u.close()
			with tempfile.NamedTemporaryFile(mode="rb", suffix=".mp4") as merged_mp4:
				subprocess.check_call(["ffmpeg", "-y", "-allowed_extensions", "ALL", "-i", rewritten_m3u.name, "-c", "copy", "-strict", "-2", merged_mp4.name])
				return merged_mp4.read()

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

			path = tweets_media+"/"+media_fname
			if isinstance(fs, ZipFS):
				item = InZip(fs.zipf, path)
				item.mime = mimetypes.guess_type(path)
			else:
				item = OnDisk(path)

			fmt = m.group(3)
			if fmt == "mp4":
				cache_key = "video.twimg.com/" + m.group(2) + ".mp4"
				videoset = self.media_by_url.setdefault(cache_key, VideoSet())
				videoset.add(item)
			else:
				cache_key = "/media/"+m.group(2)
				imageset = self.media_by_url.setdefault(cache_key, ImageSet())
				fullres = "https://pbs.twimg.com{}?format={}&name=orig".format(cache_key, fmt)
				imageset.add(item, (fmt, "medium"), (media_sizes, fullres))

	def add_http_snapshot(self, url, item):
		if url == "https://pbs.twimg.com/favicon.ico":
			return
		if url == "https://video.twimg.com/favicon.ico":
			return
		cache_key, variant, image_set_info = decode_twimg(url)
		if url.startswith("https://video.twimg.com"): # HACK
			videoset = self.media_by_url.setdefault(cache_key, VideoSet())
			videoset.add(item)
		else:
			imageset = self.media_by_url.setdefault(cache_key, ImageSet())
			imageset.add(item, variant, image_set_info)

	# check store

	def lookup(self, url):
		if url is None:
			return None, False
		if urlparse(url).path.endswith(".m3u8.mp4"): # HACK
			return self.lookup_video(url)
		cache_key, (fmt, variant_name), (sizes, _) = decode_twimg(url)
		imageset = self.media_by_url.get(cache_key, None)
		if imageset:
			return imageset.get_variant(fmt, variant_name)
		return None, False

	# remux video

	def lookup_video(self, url):

		def get(url):
			# awkward because this class is designed for imagesets and not videos
			if url.startswith("/"):
				url = "https://video.twimg.com" + url
			cache_key, _, _ = decode_twimg(url)
			if cache_key not in self.media_by_url:
				return None
			item, _ = self.media_by_url[cache_key].get_variant(None, None)
			return item

		assert url
		top_m3u_item = get(url.replace(".m3u8.mp4", ".m3u8"))
		top_m3u = top_m3u_item.open().read()
		if isinstance(top_m3u, bytes):
			top_m3u = top_m3u.decode("ascii")
		sub_m3u_urls = [line for line in top_m3u.splitlines() if line and not line.startswith("#")]

		for sub_m3u_url in sub_m3u_urls:
			sub_m3u_item = get(sub_m3u_url)
			if not sub_m3u_item:
				continue
			with sub_m3u_item.open() as sub_m3u_file:
				sub_m3u = sub_m3u_file.read()
			if isinstance(sub_m3u, bytes):
				sub_m3u = sub_m3u.decode("ascii")
			is_complete = True
			for line in sub_m3u.splitlines():
				if line and not line.startswith("#") and not get(line):
					is_complete = False
			if not is_complete:
				continue

			merged_video = merge_m3u8(sub_m3u, get)
			item = InMemory(merged_video)
			item.mime = "video/mp4"
			return item, False

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

def urlmap_binding_value(urlmap, bv):
	if "type" not in bv:
		# eg. {'scribe_key': 'publisher_id'}
		return bv
	if bv["type"] == "IMAGE":
		bv = bv.copy()
		bv["image_value"] = bv["image_value"].copy()
		bv["image_value"]["ourl"] = bv["image_value"]["url"]
		bv["image_value"]["url"] = urlmap(bv["image_value"]["url"])
	return bv

def urlmap_card(urlmap, card):
	card = card.copy()
	card["binding_values"] = {
		key: urlmap_binding_value(urlmap, value)
		for key, value in card["binding_values"].items()
	}
	return card

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
		self.replies = {}
		self.profiles = {}
		self.followers = {} # could be part of .profiles
		self.followings = {} # could be part of .profiles
		self.user_by_handle = {}
		self.media = MediaStore()
		self.har = HarStore("harstore")
		self.warc_responses = {} # to allow warc references across files
		self.likes_snapshots = {}
		self.likes_unsorted = {}
		self.bookmarks_map = {}
		self.observers = set()
		self.conversations = {}

		# indices
		self.by_user = None
		self.likes_sorted = None
		self.bookmarks_sorted = None
		self.interactions_sorted = None

		# context
		self.time = None
		self.uid = None

		# settings
		self.ignore_urls = set()

	def sort_profiles(self):
		self.by_user = {}
		self.likes_sorted = {}
		self.bookmarks_sorted = {}
		self.interactions_sorted = {}

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
		for uid in set(self.likes_snapshots.keys()) | set(self.likes_unsorted.keys()):
			likes_snapshots = self.likes_snapshots.get(uid, [])
			likes_snapshots = sorted(likes_snapshots, key=lambda snap: -snap.time)
			if False:
				continue_index = {}
				for snap in likes_snapshots:
					if hasattr(snap, "cursor_bottom"):
						continue_index[snap.cursor_bottom] = snap
				for snap in likes_snapshots:
					if hasattr(snap, "continue_from"):
						from_snap = continue_index.get(snap.continue_from, None)
						if isinstance(from_snap, seqalign.Items) and isinstance(snap, seqalign.Items):
							from_snap.items = from_snap.items + snap.items
							snap.items = None
						else:
							del snap.continue_from
				likes_snapshots = [snap for snap in likes_snapshots if not hasattr(snap, "continue_from")]

			l = seqalign.align(
				likes_snapshots,
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
			l = [(sort_index, twid) for twid, sort_index in l]
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
			return json.load(f, **json_load_args)

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
			generation_date = fromisoformat(generation_date)
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

	def reload(self):
		pass # for user to override

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
		if "entities" in tweet:
			if "media" in tweet["entities"]:
				for media in tweet["entities"]["media"]:
					if "sizes" in media:
						media["sizes"] = {k: intern_dict(v) for k, v in media["sizes"].items()}
					if "features" in media:
						del media["features"]
					if "original_info" in media:
						del media["original_info"]
		if "extended_entities" in tweet:
			if "media" in tweet["extended_entities"]:
				for media in tweet["extended_entities"]["media"]:
					if "sizes" in media:
						media["sizes"] = {k: intern_dict(v) for k, v in media["sizes"].items()}
					if "features" in media:
						del media["features"]
					if "original_info" in media:
						del media["original_info"]
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
		if "in_reply_to_status_id_str" in tweet:
			rtwid = int(tweet["in_reply_to_status_id_str"])
			r = self.replies.setdefault(rtwid, [])
			if twid not in r: r.append(twid)
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

		if self.uid is not None and user.get("following", False):
			self.add_follow(self.uid, uid)
		if self.uid is not None and user.get("followed_by", False):
			self.add_follow(uid, self.uid)

	def add_user(self, user, give_timeline_v1=False, give_timeline_v2=False):
		if "legacy" in user:
			self.add_legacy_user(user["legacy"], user["rest_id"])
		if "timeline" in user and give_timeline_v2: # HACK necessary since 2025 Apr 3
			return user["timeline"]
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
				frozenset({"__typename", "tweet", "limitedActionResults", "tweetInterstitial"}),
				frozenset({"__typename", "tweet", "limitedActionResults", "softInterventionPivot"})
			}, json.dumps(tweet)
			heuristically_circle_tweet = "Circle" in json.dumps(tweet.get("limitedActionResults"))
			tweet = tweet["tweet"]
		elif tn == "TweetTombstone":
			return
		elif tn == "TweetUnavailable":
			return

		assert "core" in tweet, (tn, list(tweet))
		user = tweet["core"]["user_results"]["result"]
		card = tweet.pop("card", None)
		if "legacy" not in tweet and "errors" in self.toplevel:
			return # TODO, but expected
		assert "legacy" in tweet, tweet
		legacy = tweet["legacy"]
		if card:
			card = card["legacy"]
			assert card["name"] in ("player", "summary", "summary_large_image", "promo_image_convo", "poll2choice_text_only",
				"poll3choice_text_only", "poll4choice_text_only", "unified_card", "promo_video_convo", "amplify") or \
				card["name"].endswith(":live_event") or \
				card["name"].endswith(":broadcast") or \
				card["name"].endswith(":message_me") or \
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
			if "result" not in content["user_results"]:
				return
			user = content["user_results"]["result"]
			self.add_user(user)
			return int(user["rest_id"])
		elif ct == "TimelineTweet":
			if "promotedMetadata" in content:
				return
			display_type = content.pop("tweetDisplayType")
			assert display_type in ("Tweet", "SelfThread", "MediaGrid", "CondensedTweet"), display_type
			tweet_results = content["tweet_results"]
			if not tweet_results: # happens in /Likes
				content.pop("hasModeratedReplies", None)
				assert content == {'itemType': 'TimelineTweet', '__typename': 'TimelineTweet', 'tweet_results': {}}, content
				return
			tweet = tweet_results["result"]
			self.add_tweet(tweet)
			if tweet.get("__typename", None) == "TweetWithVisibilityResults":
				tweet = tweet["tweet"]
			if tweet.get("__typename", None) == "TweetTombstone":
				return None
			if tweet.get("__typename", None) == "TweetUnavailable":
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
		elif ct == "TimelineCommunity":
			pass # todo
		elif ct == "TimelineMessagePrompt":
			pass # todo
		elif ct == "TimelineLabel": # eg. More replies
			pass # todo
		elif ct == "TimelinePrompt":
			pass # todo
		elif ct == "TimelineSpelling":
			pass # todo
		elif ct == "TimelineTrend":
			pass # todo
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
			elif t == "TimelineShowCover":
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
			return json.loads(q["variables"][0], **json_load_args)

	def apply_context(self, context):
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

	def load_gql(self, path, data, context):
		self.apply_context(context)

		if "data" not in data:
			return

		self.toplevel = data
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
			if "result" in data["user"]:
				self.add_user(data["user"]["result"])
		elif path.endswith("/UserByScreenName"):
			if data == {}:
				return
			self.add_user(data["user"]["result"])
		elif path.endswith("/HomeLatestTimeline"):
			if "home" in data:
				if "home_timeline_urt" in data["home"]:
					self.add_with_instructions(data["home"]["home_timeline_urt"])
		elif path.endswith("/HomeTimeline"):
			self.add_with_instructions(data["home"]["home_timeline_urt"])
		elif path.endswith("/TweetDetail"):
			if data == {}:
				return
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
			if media_timeline == {}:
				return
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

			if not likes:
				return

			if len(likes) > 1 and likes[0][0] != likes[1][0]+1:
				snapshot = seqalign.Events(likes)
			else:
				snapshot = seqalign.Items([twid for sort_index, twid in likes])
			snapshot.time = self.time
			snapshot.continue_from = gql_vars.get("cursor", None)
			for cname, value in cursors:
				if cname.startswith("cursor-bottom-"):
					snapshot.cursor_bottom = value
					break
			del cname, value

			snapshots = self.likes_snapshots.setdefault(whose_likes, [])
			snapshots.append(snapshot)

		elif path.endswith("/Bookmarks"):
			layout, cursors = self.add_with_instructions(data["bookmark_timeline_v2"]["timeline"])
			user_bookmarks = self.bookmarks_map.setdefault(self.uid, {})
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
			#assert data == {"viewer":{"draft_list":{"response_data":[]}}}
			pass
		elif path.endswith("/FetchScheduledTweets"):
			assert data == {"viewer":{"scheduled_tweet_list":[]}}
		elif path.endswith("/AuthenticatedUserTFLists"): # circles
			for circle in data["authenticated_user_trusted_friends_lists"]:
				print("found circle named", circle["name"], "with", circle["member_count"], "people")
		elif path.endswith("/CheckTweetForNudge"):
			assert data == {"create_nudge":{}}
		elif path.endswith("/CreateTweet"):
			if "create_tweet" in data:
				self.add_tweet(data["create_tweet"]["tweet_results"]["result"])
		elif path.endswith("/UsersByRestIds"):
			for user in data["users"]:
				self.add_user(user)
		elif path.endswith("/SearchTimeline"):
			search_timeline = data["search_by_raw_query"]["search_timeline"]
			if "timeline" in search_timeline:
				self.add_with_instructions(search_timeline["timeline"])
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
		elif path.endswith("/BlueVerifiedFollowers"):
			pass # todo
		elif path.endswith("/CreateBookmark"):
			pass # todo
		elif path.endswith("/articleNudgeDomains"):
			pass # todo
		elif path.endswith("/useFetchProfileBlocks_profileExistsQuery"):
			pass # todo
		elif path.endswith("/PinnedTimelines"):
			pass # todo
		elif path.endswith("/ExploreSidebar"):
			pass # todo
		elif path.endswith("/ExplorePage"):
			pass # todo
		elif path.endswith("/UserPreferences"):
			pass # todo
		elif path.endswith("/useTypingNotifierMutation"):
			pass # todo
		elif path.endswith("/AccountSwitcherDelegateQuery"):
			pass # todo
		elif path.endswith("/DelegatedAccountListQuery"):
			pass # todo
		elif path.endswith("/SensitiveMediaSettingsQuery"):
			pass # todo
		elif path.endswith("/fetchDownloadSettingAllowedQuery"):
			pass # todo
		elif path.endswith("/ListsManagementPageTimeline"):
			pass # todo
		elif path.endswith("/ListLatestTweetsTimeline"):
			pass # todo
		elif path.endswith("/BroadcastQuery"):
			pass # todo
		elif path.endswith("/PutClientEducationFlag"):
			pass # todo
		elif path.endswith("/ConnectTabTimeline"):
			pass # todo
		elif path.endswith("/TweetResultByRestId"):
			pass # todo
		elif path.endswith("/TweetResultsByRestIds"):
			for tweet_result in data["tweetResult"]:
				if "result" in tweet_result:
					self.add_tweet(tweet_result["result"])
		elif path.endswith("/ModeratedTimeline"):
			pass # todo
		elif path.endswith("/PremiumSignUpQuery"):
			pass # todo
		elif path.endswith("/useSubscriptionProductDetailsQuery"):
			pass # todo
		elif path.endswith("/ListProductSubscriptions"):
			pass # todo
		elif path.endswith("/CommunitiesCreateButtonQuery"):
			pass # todo
		elif path.endswith("/CarouselQuery"):
			pass # todo
		elif path.endswith("/CommunitiesMainPageTimeline"):
			pass # todo
		elif path.endswith("/RemoveFollower"):
			pass # todo
		elif path.endswith("/ListOwnerships"):
			pass # todo
		elif path.endswith("/ListAddMember"):
			pass # todo
		elif path.endswith("/DeleteTweet"):
			pass # todo
		elif path.endswith("/ConversationControlChange"):
			pass # todo
		elif path.endswith("/DeleteRetweet"):
			pass # todo
		elif path.endswith("/PinTweet"):
			pass # todo
		elif path.endswith("/UnpinTweet"):
			pass # todo
		elif path.endswith("/useDMReactionMutationAddMutation"):
			pass # todo
		elif path.endswith("/DeleteBookmark"):
			pass # todo
		elif path.endswith("/CommunitiesFetchOneQuery"):
			pass # todo
		elif path.endswith("/BlueVerifiedProfileEditCalloutQuery"):
			pass # todo
		elif path.endswith("/ReportDetailQuery"):
			pass # todo
		elif path.endswith("/BirdwatchFetchAuthenticatedUserProfile"):
			pass # todo
		elif path.endswith("/BirdwatchFetchOneNote"):
			pass # todo
		elif path.endswith("/BirdwatchFetchAliasSelfSelectStatus"):
			pass # todo
		elif path.endswith("/BirdwatchFetchNotes"):
			pass # todo
		elif path.endswith("/usePricesQuery"):
			pass # todo
		elif path.endswith("/useVerifiedOrgFeatureHelperQuery"):
			pass # todo
		elif path.endswith("/useProductSkuQuery"):
			pass # todo
		elif path.endswith("/TranslationFeedbackProvideFeedbackMutation"):
			pass # todo
		elif path.endswith("/UserHighlightsTweets"):
			pass # todo
		elif path.endswith("/UserAccountLabel"):
			pass # todo
		elif path.endswith("/GenericTimelineById"):
			pass # todo
		elif path.endswith("/BookmarkSearchTimeline"):
			pass # todo
		elif path.endswith("/useRelayDelegateDataPendingQuery"):
			pass # todo
		elif path.endswith("/TrendRelevantUsers"):
			pass # todo
		elif path.endswith("/AiTrendByRestId"):
			pass # todo
		elif path.endswith("/FollowHostButtonQuery"):
			pass # todo
		elif path.endswith("/useFetchAnalyticsQuery"):
			pass # todo
		elif path.endswith("/AuthenticatePeriscope"):
			pass # todo
		elif path.endswith("/QuickPromoteEligibility"):
			pass # todo
		elif path.endswith("/TweetActivityQuery"):
			pass # todo
		elif path.endswith("/PremiumContentQuery"):
			pass # todo
		elif path.endswith("/SubscriptionProductDetails"):
			pass # todo
		elif path.endswith("/useFetchProfileSections_profileQuery"):
			pass # todo
		elif path.endswith("/GrokHome"):
			pass # todo
		elif path.endswith("/Viewer"):
			pass # todo
		elif path.endswith("/ViewerUserQuery"):
			pass # todo
		elif path.endswith("/affiliatesQuery"):
			pass # todo
		elif path.endswith("/BenefitsBadgeCardQuery"):
			pass # todo
		elif path.endswith("/CreateGrokConversation"):
			pass # todo
		elif path.endswith("/useFetchProfileSections_canViewExpandedProfileQuery"):
			pass # todo
		elif path.endswith("/SupportedLanguages"):
			pass # todo
		elif path.endswith("/GetGrokCustomizationSettingQuery"):
			pass # todo
		elif path.endswith("/feedbackMutation"):
			pass # todo
		elif path.endswith("/personalityHooksAllPersonalitiesQuery"):
			pass # todo
		elif path.endswith("/TopicCarouselQuery"):
			pass # todo
		elif path.endswith("/CommunitiesRankedTimeline"):
			pass # todo
		elif path.endswith("/CommunitiesExploreTimeline"):
			pass # todo
		elif path.endswith("/isEligibleForVoButtonUpsellQuery"):
			pass # todo
		elif path.endswith("/GrokHistory"):
			pass # todo
		elif path.endswith("/GrokConversationItemsByRestId"):
			pass # todo
		elif path.endswith("/isEligibleForAnalyticsUpsellQuery"):
			pass # todo
		elif path.endswith("/SidebarUserRecommendations"):
			pass # todo
		elif path.endswith("/NotificationsTimeline"):
			pass # todo
		else:
			assert False, path

	def load_notifications(self, data, context):
		self.apply_context(context)
		if "errors" in data and "globalObjects" not in data:
			return
		assert "globalObjects" in data, data
		global_objects = data["globalObjects"]
		users = global_objects.get("users", {})
		tweets = global_objects.get("tweets", {})
		notifications = global_objects.get("notifications", {})
		timline = data["timeline"]
		# with self.Tracer():
		for uid, user in users.items():
			self.add_legacy_user(user, uid)
		for twid, tweet in tweets.items():
			# in notifications some fields are set to null rather than removed
			for empty_key in (
				"in_reply_to_status_id",
				"in_reply_to_status_id_str",
				"in_reply_to_user_id",
				"in_reply_to_user_id_str",
				"in_reply_to_screen_name",
				"geo",
				"coordinates",
				"place",
				"contributors"
			):
				if tweet.get(empty_key, True) is None:
					del tweet[empty_key]
			tweet["original_id"] = int(tweet.get("retweeted_status_id_str", twid))
			self.add_legacy_tweet(tweet)

		for nid, notif in notifications.items():
			icon_id = notif["icon"]["id"]
			timestamp = int(notif["timestampMs"])
			message = notif["message"]
			template = notif["template"]
			assert len(template) == 1
			(kind, t), = template.items()
			assert kind in ("aggregateUserActionsV1",)
			assert icon_id in (
				"heart_icon", "safety_icon", "retweet_icon", "person_icon",
				"topic_icon", "bell_icon", "milestone_icon", "recommendation_icon",
				"histogram_icon", "bird_icon", "spaces_icon", "live_icon",
				"birdwatch_icon", "lightning_bolt_icon", "trending_icon",
				"play_icon"), icon_id
			if icon_id == "heart_icon":
				users = [int(entry["user"]["id"]) for entry in t["fromUsers"]] # confirm empty else
				targets = [int(entry["tweet"]["id"]) for entry in t["targetObjects"]] # confirm empty else
				for nuid in users:
					for twid in targets:
						self.likes_unsorted.setdefault(nuid, set()).add(twid)

	def load_api(self, fname, item, context):
		url = context["url"]
		path = urlparse(url).path

		if url in self.ignore_urls:
			return

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
			"/i/api/fleets/"
		):
			return # also not interesting for now

		if url.startswith("https://pbs.twimg.com/") or url.startswith("https://video.twimg.com/"):
			if isinstance(item, InMemory) and item.data == "":
				print("empty   ", fname, path)
				return # why
			print("media   ", fname, path)
			self.media.add_http_snapshot(url, item)
			return

		item_file = item.open()
		try:
			data = json.load(item_file, **json_load_args)
		except:
			print("not json", fname, path)
			return

		if url.startswith("https://twitter.com/i/api/graphql/") or url.startswith("https://x.com/i/api/graphql/"):
			print("adding  ", fname, path)
			self.load_gql(path, data, context)
		elif path == "/i/api/2/notifications/all.json":
			self.load_notifications(data, context)
		else:
			print("skipping", fname, path)

	def load_har(self, fname):
		lhar = self.har.load(fname)
		any_missing = False
		for entry in lhar["log"]["entries"]:
			url = entry["request"]["url"]
			response = entry["response"]["content"]
			if response:
				time = fromisoformat(entry["startedDateTime"])
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

	def load_warc(self, fname, f_offset=None):
		if not f_offset:
			f = open(fname, "rb") # leave file open as long as referenced by InWarc objects
		else:
			f = f_offset[0]
			f.seek(f_offset[1])
			del f_offset
		r = read_warc(f, responses=self.warc_responses)
		end = f.tell()
		for (wreq, req), (wres, res, item) in r:
			cookies = None
			for line in req[1:]:
				m = header_re.match(line)
				name = m.group(1)
				value = m.group(2)
				if name == b"Cookie":
					cookies = [
						{"name": morsel.key, "value": morsel.value}
						for morsel in TwitterCookie(value.decode("utf-8")).values()
					]
			context = {
				"url": wreq["warc-target-uri"],
				"timeStamp": fromisoformat(wres["warc-date"]).timestamp() * 1000,
				"cookies": cookies
			}
			if b"transfer-encoding: chunked\r\n" in res or \
			   b"Transfer-Encoding: chunked\r\n" in res:
				continue
			if res[0] in (b"HTTP/1.1 404 Not Found\r\n", b"HTTP/1.1 304 Not Modified\r\n"):
				continue
			if "//localhost" in context["url"]:
				continue
			self.load_api(fname, item, context)

		return (f, end)

	def new_thread_view(self, twid):
		seq = []

		up = twid
		while up:
			tw = self.tweets.get(up, None)
			seq.insert(0, (None, None, up))
			up = tw and tw.get("in_reply_to_status_id_str", None)
			up = up and int(up)
		del up

		dn = twid
		while dn:
			ndn = None
			for r in self.replies.get(dn, []):
				tw = self.tweets.get(r, None)
				seq.append((None, None, r))
				if tw:
					ndn = r
			dn = ndn
		del dn

		return seq


header_re = re.compile(rb"(.*): (.*)\r\n")

# gather inputs

def gather_paths(argv):
	paths = []

	def add_file(path, explicit):
		ext = os.path.splitext(path)[1]
		if ext in (".zip", ".har", ".warc", ".open"):
			paths.append(path)
		if ext == ".py" and explicit:
			paths.append(path)
		if ext == ".txt" and explicit:
			add_list(path)

	def add_path(path):
		if os.path.isdir(path):
			is_archive = os.path.exists(os.path.join(path, "data")) or os.path.exists(os.path.join(path, "tweet.js"))
			if is_archive:
				paths.append(path)
			else:
				for fname in sorted(os.listdir(path)): # sort to keep timestamped inputs in order
					add_file(os.path.join(path, fname) if path != "." else fname, explicit=False)
		else:
			add_file(path, explicit=True)

	def add_list(path):
		try:
			with open(path) as f:
				lines = f.readlines()
		except:
			return

		for l in lines:
			l = l.strip()
			if l and not l.startswith("#"):
				add_path(l)

	if argv:
		for arg in argv:
			add_path(arg)

	else:
		add_list("exports.txt")
		add_path(".")

	# archive data is broken for RTs so apply HAR later to overwrite that
	paths.sort(key=lambda path: 1 if path.endswith(".har") else 0)

	return paths

# load inputs

db = DB()

if os.path.exists("ignore.txt"):
	with open("ignore.txt") as f:
		ignore_urls = [line.strip() for line in f.readlines()]
	db.ignore_urls = set(filter(None, ignore_urls))

warc_open = {}
modules = {}

def load_single(path):
	print(path)
	if path.endswith(".har"):
		db.har.add(path, skip_if_exists=True)
		db.load_har(path)
	elif path.endswith(".warc"):
		db.load_warc(path, warc_open.pop(path+".open", None))
	elif path.endswith(".warc.open"):
		warc_open[path] = db.load_warc(path, warc_open.get(path, None))
	elif path.endswith(".zip"):
		db.load(zipfile.ZipFile(path))
	elif path.endswith(".py"):
		module = modules.get(path, None)
		if module:
			spec = module.__spec__
		else:
			spec = importlib.util.spec_from_file_location("__data_source__", path)
			module = importlib.util.module_from_spec(spec)
			module.db = db
			modules[path] = module
		spec.loader.exec_module(module)
	else:
		db.load(path)

paths = []
def db_reload():
	global paths
	new_paths = gather_paths(sys.argv[1:])
	for path in new_paths:
		if path not in paths or path.endswith(".warc.open") or path.endswith(".py"):
			load_single(path)
	paths = new_paths

	# post-processing

	db.sort_profiles()

	# print how many tweets by who are in the archive
	z = [(len(v), db.profiles[k]["screen_name"] if k in db.profiles else str(k), k) for k, v in db.by_user.items()]
	z.sort()
	for count, name, uid in z:
		print("{:4d} {}".format(count, name))

db.reload = db_reload

db.reload()

