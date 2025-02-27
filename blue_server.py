import os.path, sys, datetime, re
server_path = os.path.dirname(__file__)
sys.path.append(server_path + "/vendor") # use bundled copy of bottle, if system has none
from bottle import route, run, static_file, HTTPError
import atproto

c = atproto.Client("https://public.api.bsky.app/xrpc")

display_name_cache = {}

def translate_profile_detailed(profile):
	display_name_cache.setdefault(profile.handle, profile.display_name)
	display_name_cache.setdefault(profile.did, profile.display_name)
	return {
		"description": profile.description,
		"name": profile.display_name,
		"screen_name": profile.handle,
		"profile_banner_url": profile.banner,
		"profile_image_url_https": profile.avatar,
		"followed_by": False,
		"protected": False,
		"user_id_str": profile.did,
		"friends_count": profile.follows_count,
		"followers_count": profile.followers_count
	}

def translate_profile_basic(profile):
	display_name_cache.setdefault(profile.handle, profile.display_name)
	display_name_cache.setdefault(profile.did, profile.display_name)
	return {
		#"description": profile.description,
		"name": profile.display_name,
		"screen_name": profile.handle,
		#"profile_banner_url": profile.banner,
		"profile_image_url_https": profile.avatar,
		"followed_by": False,
		"protected": False,
		"user_id_str": profile.did,
		#"friends_count": profile.follows_count,
		#"followers_count": profile.followers_count
	}

def translate_postview(postview):
	tweet = {
		"full_text": postview.record.text,
		"favorite_count": postview.like_count,
		"retweet_count": postview.repost_count,
		"reply_count": postview.reply_count,
		"id_str": postview.uri,
		"user": translate_profile_basic(postview.author),
		"user_id_str": postview.author.did,
		"created_at": datetime.datetime.fromisoformat(postview.indexed_at).strftime("%a %b %d %H:%M:%S %z %Y"),
	}
	if postview.record.reply:
		reply_to = postview.record.reply.parent
		reply_user_id_str = re.match("^at://([^/]+)/", reply_to.uri).group(1)
		tweet["in_reply_to_status_id_str"] = reply_to.uri
		tweet["in_reply_to_user_id_str"] = reply_user_id_str
		if reply_user_id_str in display_name_cache:
			tweet["in_reply_to_screen_name"] = display_name_cache[reply_user_id_str]

	if postview.embed: # not postview.record.embed
		if hasattr(postview.embed, "images"):
			tweet["extended_entities"] = {"media": [
				{
					"type": "image",
					"media_url_https": viewimage.thumb,
					"sizes": [{"w": viewimage.aspect_ratio.width, "h": viewimage.aspect_ratio.height}]
				} for viewimage in postview.embed.images
			]}
	return tweet

from atproto_client.models.app.bsky.feed.defs import ReasonRepost, ReasonPin

def translate_feedviewpost(feedviewpost):
	tweet = translate_postview(feedviewpost.post)
	if isinstance(feedviewpost.reason, ReasonRepost):
		tweet["context_icon"] = "retweet"
		tweet["context_user"] = feedviewpost.reason.by.display_name
		tweet["context_user_protected"] = False
	elif isinstance(feedviewpost.reason, ReasonPin):
		tweet["context_icon"] = "pin"
		tweet["context_user"] = feedviewpost.reason.by.display_name
		tweet["context_user_protected"] = False
	return tweet

ir = atproto.IdResolver()
pds_clients = {}
def get_pds_client(did):
	did_document = ir.did.resolve(did)
	for service in did_document.service:
		if service.id == "#atproto_pds":
			endpoint = service.service_endpoint
			if endpoint not in pds_clients:
				pds_clients[endpoint] = atproto.Client(service.service_endpoint)
			return pds_clients[endpoint]

class ClientAPI:

	# tweets

	def profile_view(self, did):
		feed = c.get_author_feed(did).feed
		return [translate_feedviewpost(tweet) for tweet in feed]

	def likes_view(self, did):
		pds = get_pds_client(did)
		like_records = pds.com.atproto.repo.list_records(params={"collection": "app.bsky.feed.like", "repo": did, "limit": 25}).records
		likes = c.app.bsky.feed.get_posts(params={"uris":[like_record.value.subject.uri for like_record in like_records]}).posts
		return [translate_postview(post) for post in likes]

	# users

	def get_profile(self, did):
		return translate_profile_detailed(c.get_profile(did))

ca = ClientAPI()

def paginated_tweets(x):
	if "likes" in x:
		x["tweets"] = x.pop("likes")
	return x

@route('/api/profile/<did>')
@route('/api/profile2/<did>')
def profile(did):
	return paginated_tweets({
		"topProfile": ca.get_profile(did),
		"tweets": ca.profile_view(did)
	})

@route('/api/likes/<did>')
def likes(did):
	return paginated_tweets({
		"topProfile": ca.get_profile(did),
		"likes": ca.likes_view(did)
	})

@route('/api/everyone')
def everyone():
	return {"profiles": [
		ca.get_profile("dril.bsky.social")
	]}

@route('/fonts/<path:path>')
def resources_20230628(path):
	return static_file(path, root=server_path+'/static/20230628/fonts')

@route('/responsive-web/<path:path>')
def resources_20230628(path):
	return static_file(path, root=server_path+'/static/20230628/responsive-web')

@route('/<name>.js')
def client_js(name):
	return static_file(name+'.js', root=server_path+'/static')

@route('/p/<path:path>')
def preact_js(path):
	r = static_file(path, root=server_path+'/node_modules/preact/')
	if isinstance(r, HTTPError) and path == "dist/preact.mjs":
		# fall back to bundled preact copy
		r = static_file('preact.mjs', root=server_path+'/static')
	return r

@route('/')
@route('/<who>')
@route('/dm')
@route('/dm/<conversation>')
@route('/everyone')
@route('/thread/<twid:int>')
@route('/home/<who>')
@route('/search')
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

run(port=8081)
