import { h, createRef, render, Component, ComponentChildren, Fragment, JSX, VNode } from 'preact';

type Entities = {
	hashtags: any[],
	symbols: any[],
	user_mentions: UserMention[],
	urls: UrlEntity[],
	media?: MediaEntity[]
};

type LegacyProfile = {
	description?: string,
	entities: {description: Entities},
	name: string,
	screen_name: string,
	profile_banner_url?: string,
	profile_image_url_https: string,
	followed_by?: boolean,
	protected: boolean,
	user_id_str?: string,
	friends_count: number, // following
	followers_count: number, // followers

	observer?: boolean
};

type SizeInfo = {
	w: number,
	h: number,
	resize: "fit"|"crop"
}

type Sizes2019 = SizeInfo[];
type Sizes2020 = {
	large: SizeInfo,
	medium: SizeInfo,
	small: SizeInfo,
	thumb: SizeInfo
};

type VideoInfo = {
	variants: {content_type: string, url: string}[]
};

type MediaEntity = {
	ext_alt_text?: string,
	type: string,
	video_info: VideoInfo,
	indices: [string, string],
	original_info?: { // doesn't exist in archives for example
		width: number,
		height: number
	},
	sizes?: Sizes2019 | Sizes2020;
	media_url_https: string
};

type UserMention = {
	name: string,
	screen_name: string,
	indices: [string, string],
	id_str: string,
	id: string
}

type UrlEntity = {
	url: string,
	expanded_url: string,
	display_url: string,
	indices: [string, string]
};

type HashtagEntity = {
	text: string,
	indices: [string, string]
};

type TweetInfo = {
	full_text: string,
	favorite_count: string,
	retweet_count: string,
	reply_count: string,
	id_str: string,
	entities?: Entities,
	extended_entities?: Entities,
	user: LegacyProfile,
	user_id_str: string,
	created_at: string,
	display_text_range?: [number, number],
	in_reply_to_screen_name?: string,
	in_reply_to_status_id_str?: string,
	in_reply_to_user_id_str?: string,
	limited_actions? : string,

	bookmarkers?: string[],
	favoriters?: string[],
	retweeters?: string[],

	card?: any,
	line?: boolean,
	quoted_status?: TweetInfo,
	context_icon?: string,
	context_user?: string,
	context_user_protected?: boolean | null,
	circle?: {
		screen_name: string,
		name: string
	}
};

type HistogramData = {
	name: string,
	max_tweets: number,
	histogram: [number, number[]][]
};

type Message = any;
type ConversationInfo = [string, LegacyProfile, LegacyProfile, Message];
type Conversation = [{
	conversationId: string,
	messages: Message[]
}, LegacyProfile, LegacyProfile];

type AppProps = {
	topProfile?: LegacyProfile,
	profiles?: LegacyProfile[],
	focusTweetId?: string,
	tweets?: TweetInfo[],
	tab: number,
	histograms?: HistogramData[],
	conversations?: ConversationInfo[],
	conversation?: Conversation,
	final_link?: {href: string, content: string}
};

class Logic {
	updateFn: (AppProps) => void;
	history: string[];

	constructor(updateFn: (AppProps) => void) {
		this.updateFn = updateFn;
	}

	back() {
		window.history.back();
	}

	navigate(i: string, q?: string) {
		if (q === undefined)
			q = "";
		window.history.pushState(i+q, "", "/"+i+q);
		this.navigateReal(i, q);
	}

	navigateReal(i: string, q: string) {
		let api_call: string;
		let tab = 0;
		let focusTweetId = undefined;
		let m: string[];
		if (i == "") {
			api_call = "everyone";
		}
		else if ((m = i.match(/dm$/)) !== null) {
			api_call = "dm";
		}
		else if ((m = i.match(/dm\/([^/]+)$/)) !== null) {
			api_call = `dm/${m[1]}`;
		}
		else if ((m = i.match(/home\/([^/]+)$/)) !== null) {
			api_call = `home/${m[1]}`;
		}
		else if ((m = i.match(/thread\/(\d+)$/)) !== null) {
			api_call = i; // easy
			focusTweetId = m[1];
		}
		else if ((m = i.match(/search$/)) !== null) {
			api_call = "search";
		}
		else if ((m = i.match(/profile\/(\d+)$/)) !== null) {
			api_call = `profile/${m[1]}`;
			tab = 0;
		}
		else if ((m = i.match(/profile\/(\d+)\/with_replies$/)) !== null) {
			api_call = `replies/${m[1]}`;
			tab = 1;
		}
		else if ((m = i.match(/profile\/(\d+)\/media$/)) !== null) {
			api_call = `media/${m[1]}`;
			tab = 2;
		}
		else if ((m = i.match(/profile\/(\d+)\/likes$/)) !== null) {
			api_call = `likes/${m[1]}`;
			tab = 3;
		}
		else if ((m = i.match(/profile\/(\d+)\/bookmarks$/)) !== null) {
			api_call = `bookmarks/${m[1]}`;
			tab = 4;
		}
		else if ((m = i.match(/profile\/(\d+)\/interactions$/)) !== null) {
			api_call = `interactions/${m[1]}`;
			tab = 4;
		}
		else if ((m = i.match(/profile\/(\d+)\/following$/)) !== null) {
			api_call = `following/${m[1]}`;
			tab = 101;
		}
		else if ((m = i.match(/profile\/(\d+)\/followers$/)) !== null) {
			api_call = `followers/${m[1]}`;
			tab = 100;
		}
		else if ((m = i.match(/([^/]+)$/)) !== null) {
			api_call = `profile2/${m[1]}`;
			tab = 0;
		}
		else {
			api_call = i; // fall-back
		}

		let self = this;
		fetch('/api/'+api_call+q).then((response) =>
			response.json().then((data) => {
				data["tab"] = tab;
				data["focusTweetId"] = focusTweetId;				
				if (data.conversation !== undefined)
					data.conversation[0].messages.reverse(); // workaround
				self.updateFn(data)
			})
		);
	}
}

type TweetProps = {
	t: TweetInfo,
	u: LegacyProfile,
	hideContext?: boolean,
	showReplyingTo: boolean,
	focus?: boolean,
	showMediaViewer: (urls: string[]) => void
}

type ProfileProps = {
	p: LegacyProfile
}

let TweetActions = (props: {t: TweetInfo}) =>
	<div class="t20230403-actions">
		<div class="t20230403-action-item-outer t20230403-action-reply"><div tabIndex={0} class="t20230403-action-item-inner">
			<svg class="t20230403-action-icon" viewBox="0 0 24 24"><g><path d="M1.751 10c0-4.42 3.584-8 8.005-8h4.366c4.49 0 8.129 3.64 8.129 8.13 0 2.96-1.607 5.68-4.196 7.11l-8.054 4.46v-3.69h-.067c-4.49.1-8.183-3.51-8.183-8.01zm8.005-6c-3.317 0-6.005 2.69-6.005 6 0 3.37 2.77 6.08 6.138 6.01l.351-.01h1.761v2.3l5.087-2.81c1.951-1.08 3.163-3.13 3.163-5.36 0-3.39-2.744-6.13-6.129-6.13H9.756z"></path></g></svg>
			<span class="t20230403-action-text"><span>{props.t.reply_count == "0" ? "" : props.t.reply_count}</span></span>
		</div></div>
		<div class="t20230403-action-item-outer t20230403-action-rt"><div tabIndex={0} class="t20230403-action-item-inner">
			<svg class="t20230403-action-icon" viewBox="0 0 24 24"><g><path d="M4.75 3.79l4.603 4.3-1.706 1.82L6 8.38v7.37c0 .97.784 1.75 1.75 1.75H13V20H7.75c-2.347 0-4.25-1.9-4.25-4.25V8.38L1.853 9.91.147 8.09l4.603-4.3zm11.5 2.71H11V4h5.25c2.347 0 4.25 1.9 4.25 4.25v7.37l1.647-1.53 1.706 1.82-4.603 4.3-4.603-4.3 1.706-1.82L18 15.62V8.25c0-.97-.784-1.75-1.75-1.75z"></path></g></svg>
			<span class="t20230403-action-text"><span>{props.t.retweet_count == "0" ? "" : props.t.retweet_count}</span></span>
		</div></div>
		<div class={"t20230403-action-item-outer t20230403-action-like" + ((props.t.favoriters || []).length > 0 ? " activated" : "")}><div tabIndex={0} class="t20230403-action-item-inner">
			<svg class="t20230403-action-icon inactive-icon" viewBox="0 0 24 24"><g><path d="M16.697 5.5c-1.222-.06-2.679.51-3.89 2.16l-.805 1.09-.806-1.09C9.984 6.01 8.526 5.44 7.304 5.5c-1.243.07-2.349.78-2.91 1.91-.552 1.12-.633 2.78.479 4.82 1.074 1.97 3.257 4.27 7.129 6.61 3.87-2.34 6.052-4.64 7.126-6.61 1.111-2.04 1.03-3.7.477-4.82-.561-1.13-1.666-1.84-2.908-1.91zm4.187 7.69c-1.351 2.48-4.001 5.12-8.379 7.67l-.503.3-.504-.3c-4.379-2.55-7.029-5.19-8.382-7.67-1.36-2.5-1.41-4.86-.514-6.67.887-1.79 2.647-2.91 4.601-3.01 1.651-.09 3.368.56 4.798 2.01 1.429-1.45 3.146-2.1 4.796-2.01 1.954.1 3.714 1.22 4.601 3.01.896 1.81.846 4.17-.514 6.67z"></path></g></svg>
			<svg class="t20230403-action-icon active-icon" viewBox="0 0 24 24"><g><path d="M20.884 13.19c-1.351 2.48-4.001 5.12-8.379 7.67l-.503.3-.504-.3c-4.379-2.55-7.029-5.19-8.382-7.67-1.36-2.5-1.41-4.86-.514-6.67.887-1.79 2.647-2.91 4.601-3.01 1.651-.09 3.368.56 4.798 2.01 1.429-1.45 3.146-2.1 4.796-2.01 1.954.1 3.714 1.22 4.601 3.01.896 1.81.846 4.17-.514 6.67z"></path></g></svg>
			<span class="t20230403-action-text"><span>{props.t.favorite_count == "0" ? "" : props.t.favorite_count}</span></span>
		</div></div>
		{false ? <div class="t20230403-action-item-outer t20230403-action-views"><div tabIndex={0} class="t20230403-action-item-inner">
			<svg class="t20230403-action-icon" viewBox="0 0 24 24"><g><path d="M8.75 21V3h2v18h-2zM18 21V8.5h2V21h-2zM4 21l.004-10h2L6 21H4zm9.248 0v-7h2v7h-2z"></path></g></svg>
			<span class="t20230403-action-text"><span>10</span></span>
		</div></div> : []}
		<div class="t20230403-action-item-outer t20230403-action-share"><div tabIndex={0} class="t20230403-action-item-inner">
			<svg class="t20230403-action-icon" viewBox="0 0 24 24"><g><path d="M12 2.59l5.7 5.7-1.41 1.42L13 6.41V16h-2V6.41l-3.3 3.3-1.41-1.42L12 2.59zM21 15l-.02 3.51c0 1.38-1.12 2.49-2.5 2.49H5.5C4.11 21 3 19.88 3 18.5V15h2v3.5c0 .28.22.5.5.5h12.98c.28 0 .5-.22.5-.5L19 15h2z"></path></g></svg>
		</div></div>
	</div>;

let MediaGrid = (props: {items: VNode<any>[]}) => {
	let items = props.items;
	return <div class="t20230624-embed-rounded-corners">
		<div class="t20230624-media-relative">
			<div class="t20230624-media-aspect-keeper"></div>
			{
				items.length == 0 ? [] :
				items.length == 1 ? items[0] :
				items.length == 2 ?
					<div class="t20230701-media-hdiv">{items}</div> :
				items.length == 3 ?
					<div class="t20230701-media-hdiv">
						{items[0]}
						<div class="t20230701-media-vdiv">{[items[1], items[2]]}</div>
					</div>
				:
					<div class="t20230701-media-hdiv">
						<div class="t20230701-media-vdiv">{[items[0], items[1]]}</div>
						<div class="t20230701-media-vdiv">{[items[2], items[3]]}</div>
					</div>

			}
		</div>
	</div>
};

let SmallVideoEmbed = (props: {card: any}) => {
	let bv = props.card.binding_values;
	let image_url = "";
	if (props.card.name == "player")
		image_url = bv.player_image.image_value.url
	else if (props.card.name == "summary" && bv.thumbnail_image !== undefined)
		image_url = bv.thumbnail_image.image_value.url;
	return <div class="t20230624-embed-rounded-corners t20230705-video">
		<div class="t20230705-video-left">
			<div class="t20230624-image-div" style={image_url ? `background-image: url('${image_url}');` : ""}>
			</div>
			{props.card.name == "player" ?
			<div class="t20230705-overlay">
				<div class="t20230705-play-button">
					<svg viewBox="0 0 24 24" aria-hidden="true"><g><path d="M21 12L4 2v20l17-10z"></path></g></svg>
				</div>
			</div> : []}
		</div>
		<div class="t20230705-video-right">
			{bv.domain !== undefined ?
				<div class="t20230705-card-origin">{bv.domain.string_value}</div> : []}
			{bv.title !== undefined ?
				<div class="t20230705-card-title">{bv.title.string_value}</div> : [props.card.name]}
			{bv.description !== undefined ?
				<div class="t20230705-card-desc">{bv.description.string_value}</div> : []}
		</div>
	</div>;
};

let SummaryLargeImage = (props: {card: any}) => {
	let bv = props.card.binding_values;
	let image_url = "";
	if (bv.summary_photo_image)
		image_url = bv.summary_photo_image.image_value.url;
	return <div class="t20230624-embed-rounded-corners t20230810-summary-large">
		<div class="t20230810-summary-large-top">
			<div style="padding-bottom: 52.35602094240838%;"/>
			<div class="t20230624-image-div" style={image_url ? `background-image: url('${image_url}');` : ""}>
			</div>
		</div>
		<div class="t20230810-summary-large-bottom">
			{bv.domain !== undefined ?
				<div class="t20230705-card-origin">{bv.domain.string_value}</div> : []}
			{bv.title !== undefined ?
				<div class="t20230705-card-title">{bv.title.string_value}</div> : [props.card.name]}
			{bv.description !== undefined ?
				<div class="t20230705-card-desc">{bv.description.string_value}</div> : []}
		</div>
	</div>;
};

let Poll = (props: {card: any}) => {
	let card = props.card;
	let labels = [];
	let counts = [];
	labels.push(card.binding_values.choice1_label.string_value);
	labels.push(card.binding_values.choice2_label.string_value);
	counts.push(parseInt(card.binding_values.choice1_count.string_value));
	counts.push(parseInt(card.binding_values.choice2_count.string_value));
	if (card.name != "poll2choice_text_only") {
		labels.push(card.binding_values.choice3_label.string_value);
		counts.push(parseInt(card.binding_values.choice3_count.string_value));
		if (card.name != "poll3choice_text_only") {
			labels.push(card.binding_values.choice4_label.string_value);
			counts.push(parseInt(card.binding_values.choice4_count.string_value));
		}
	}
	let sum = 0, max = 0;
	for (let count of counts) {
		sum += count;
		max = count > max ? count : max;
	}
	let percentages = counts.map((v) => (100*v/sum).toFixed(1)+"%");
	return <div class="t20230920-poll">
		<div class="t20230920-poll-options">
			{labels.map((label, i) =>
				<div class={"t20230920-poll-option t20230920-poll-" + (counts[i] == max ? "active" : "inactive")}>
					<div class="t20230920-poll-bar" style={`width: ${percentages[i]};`}></div>
					<span class="t20230920-poll-desc">{label}</span>
					<span class="t20230920-poll-perc">{percentages[i]}</span>
				</div>
			)}
		</div>
		<div class="t20230920-poll-summary"><span><span>{sum} votes</span></span><span class="t20230920-poll-punctuation">·</span><span>Final results</span></div>
	</div>
};

let TweetImage = (props: {
	src: string,
	onClick?: JSX.MouseEventHandler<HTMLElement>,
	title?: string
}) => <div
	class="t20230624-image-div" 
	style={{"background-image": `url('${props.src}')`}}  /*todo: proper escape*/
	onClick={props.onClick} title={props.title}></div>;

let TweetVideo = (props: {entity: MediaEntity}) => {
	for (let variant of props.entity.video_info.variants) {
		if (variant.url != null)
			return <video
				src={variant.url}
				poster={props.entity.media_url_https}
				controls={true}
				preload="none"
				loop={props.entity.type == "animated_gif"}
			/>;
	}
	return <div>No video variant found</div>;
};

let months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

let dateFormat = (datestr: string | number) => {
	let now = new Date();
	let date = new Date(datestr);
	let deltaSec = (now.getTime() - date.getTime()) / 1000;


	if (deltaSec < 60)
		return "now";
	if (deltaSec < 60 * 60)
		return `${Math.floor(deltaSec/60)}m`
	if (deltaSec < 24 * 60 * 60)
		return `${Math.floor(deltaSec/60/24)}h`

	if (now.getFullYear() != date.getFullYear())
		return `${months[date.getMonth()]} ${date.getDate()}, ${date.getFullYear()}`;
	return `${months[date.getMonth()]} ${date.getDate()}`;
};

let dateFormat2 = (datestr: string | number) => {
	let date = new Date(datestr);
	let minutes = date.getMinutes().toString().padStart(2, '0');
	return `${date.getHours()}:${minutes} · ${months[date.getMonth()]} ${date.getDate()}, ${date.getFullYear()}`;
};

let dateFormat3 = (datestr: string | number) => {
	let date = new Date(datestr);
	let minutes = date.getMinutes().toString().padStart(2, '0');
	return `${months[date.getMonth()]} ${date.getDate()}, ${date.getFullYear()}, ${date.getHours()}:${minutes}`;
};

let SimpleTweetText = (props: {tweet: TweetInfo}) => {
	let tweet = props.tweet;
	let text = tweet.full_text;
	if (tweet.display_text_range !== undefined) {
		text = text.slice(tweet.display_text_range[0], tweet.display_text_range[1]);
	}
	if (text.indexOf("<") >= 0) {
		console.log("tweet has unescaped html", tweet);
		return <>{text}</>;
	}

	return <span dangerouslySetInnerHTML={{__html: text}}/>;
};

let surrogatesRegex = /[\uD800-\uDBFF][\uDC00-\uDFFF]/gm; 
let strlenUtf16 = (e) => e.replace(surrogatesRegex, ' ').length;
let translateRange = (text, begin, end) => {
	if (text.length - strlenUtf16(text) > 0) {
		const asArray = Array.from(text);
		let prefix = 0 === begin ? '' : asArray.slice(0, begin).join('');
		let slice = asArray.slice(begin, end).join('');
		return [prefix.length, prefix.length + slice.length];
	}
	return [begin, end];
};
let prepareEntities = (entities, kind, text) => {
	if (!entities)
		return [];
	return entities.map((e) => ({
		...e,
		kind: kind,
		indices: translateRange(text, +e.indices[0], +e.indices[1])
	}));
};
let partsForTweetEntities = (text: string, entities: Entities) => {
	let parts = [];
	if (entities === undefined)
		return [];
	parts.push(...prepareEntities(entities.media, "media", text));
	parts.push(...prepareEntities(entities.urls, "url", text));
	parts.push(...prepareEntities(entities.hashtags, "hashtag", text));
	parts.push(...prepareEntities(entities.symbols, "cashtag", text));
	parts.push(...prepareEntities(entities.user_mentions, "mention", text));
	return parts;
};
let TweetText = (props: {tweet: TweetInfo}) => {
	let tweet = props.tweet;
	return TextWithEntities({
		full_text: tweet.full_text,
		entities: tweet.entities,
		display_text_range: tweet.display_text_range,
		card_url: tweet.card && tweet.card.url,
		quoted_status_id_str: tweet.quoted_status && tweet.quoted_status.id_str
	});
};

type TextWithEntitiesProps = {
	full_text: string,
	entities: Entities,
	display_text_range: [number, number],

	card_url?: string,
	quoted_status_id_str?: string
};

let TextWithEntities = (props: TextWithEntitiesProps) => {
	let full_text = props.full_text;
	let entities = partsForTweetEntities(full_text, props.entities);
	entities.sort((a, b) => a.indices[0] - b.indices[0]);

	let [displayStart, displayEnd] =
		props.display_text_range !== undefined
		? translateRange(
			props.full_text,
			props.display_text_range[0],
			props.display_text_range[1])
		: [0, props.full_text.length];

	let parts = [];
	{
		// in here assume the text goes all the way to the end
		// this affects anyMedia as it now catches entities past the display end
		let displayEnd = props.full_text.length;

		let offset = displayStart;
		for (let entity of entities) {
			let [begin, end] = entity.indices;
			// text between entities
			let textEnd = displayEnd;
			if (textEnd > begin)
				textEnd = begin;
			if (offset < begin)
				parts.push({
					indices: [offset, textEnd],
					kind: "text",
					text: full_text.slice(offset, textEnd)
				});
			if (begin >= displayStart && end <= displayEnd) {
				parts.push(entity);
				if (offset < end)
					offset = end;
			}
		}
		if (offset < displayEnd)
			parts.push({
				indices: [offset, displayEnd],
				kind: "text",
				text: full_text.slice(offset, displayEnd)
			});
	}

	let twitterRegex = /^https?:\/\/(?:(?:(?:m(?:obile)?)|(?:www)|)\.)?twitter\.com\/@?([_\w\d]+)\/status(?:es)?\/([\d]+)\/?/;
	let anyMedia = parts.some((part) => part.kind == "media");
	let cardUrl = props.card_url;
	parts = parts.filter((part, n) => {
		let last = n == parts.length-1;
		let qrt = false;
		if (part.kind == "media")
			return false;
		if (part.kind == "url" && props.quoted_status_id_str !== undefined) {
			let m = part.expanded_url.match(twitterRegex);
			if (m) {
				let [, screen_name, tweet_id] = m;
				qrt = tweet_id == props.quoted_status_id_str;
			}
		}
		if (qrt && anyMedia && part.indices[1] == displayEnd)
			return false;
		if (last && qrt && !anyMedia)
			return false;
		if (last && props.quoted_status_id_str === undefined && cardUrl && (cardUrl == part.url || cardUrl == part.expanded_url))
			return false;
		return true;
	});

	let vdom = [];
	parts.forEach((part, index) => {
		if (part.kind == "text") {
			let isFirst = index == 0;
			let isLast = index == parts.length-1;
			if (!part.text.trim() && (isFirst || isLast))
				return;
			let text = part.text;
			if (isLast)
				text = text.replace(/(\s+$)/g, '');
			if (text.indexOf("<") >= 0)
				vdom.push(text);
			else
				vdom.push(<span dangerouslySetInnerHTML={{__html: text}}/>);
		} else if (part.kind == "url") {
			let urle = part as UrlEntity;
			vdom.push(<a href={urle.expanded_url}>{urle.display_url}</a>);
		} else if (part.kind == "hashtag") {
			let hashtage = part as HashtagEntity;
			vdom.push(<a href={"#todo-hashtag-"+hashtage.text}>#{hashtage.text}</a>);
		} else if (part.kind == "mention") {
			let usere = part as UserMention;
			vdom.push(<a href={"/profile/"+usere.id_str}>@{usere.screen_name}</a>);
		} else {
			vdom.push(`[unhandled ${part.kind} entity]`)
		}
	});

	return <>{vdom}</>;
};

let tweetIdToEpoch = (id_str: string) => parseInt((BigInt(id_str) >> BigInt(22)).toString()) + 1288834974657;
let likeIdToEpoch = (id_str: string) => parseInt((BigInt(id_str) >> BigInt(20)).toString());

let AnonymousTweet = (props: {t: TweetInfo}) => {
	return <div class="t20230403-tweet t20230403-tweet-unfocused" tabIndex={0}>
		<div class="t20230403-tweet-split">
			<div class="t20230403-avatar-column">
			</div>
			<div class="t20230403-main-column">
				<div class="t20230403-user-line">
					<span class="t20230403-user-line-displayname">Unknown</span>
					<span class="t20230403-user-line-handle" tabIndex={-1}>@unknown</span>
					<span class="t20230403-user-line-punctuation">·</span>
					<a class="t20230403-user-line-time" href={`https://twitter.com/i/web/status/${props.t.id_str}`}>{dateFormat(tweetIdToEpoch(props.t.id_str))}</a>
					<span class="t20230403-user-line-menu"></span>
				</div>
				<div class="t20230403-contents"><TweetText tweet={props.t}/></div>
			</div>
		</div>
	</div>;
};

let WithheldItem = (props: {message: string, action?: string, handler?: (e: JSX.TargetedMouseEvent<HTMLAnchorElement>) => void}) =>
	<div class="t20230707-item">
		<div class="t20230707-withheld">
			<div class="t20230707-withheld-text">{props.message}</div>
			{props.action ? <a class="t20230707-withheld-button" onClick={props.handler}><span>{props.action}</span></a> : []}
		</div>
	</div>

let VisibilityNote = (props: {whoseCircle: string, box: boolean, learnMore: boolean}) =>
	<div class="t20230818-visibility">
		<div class={(props.box ? "t20230818-visibility-circle-box " : "") + "t20230818-visibility-circle"}>
			<div><svg viewBox="0 0 24 24" aria-hidden="true" class="r-jwli3a r-4qtqp9 r-yyyyoo r-tbmifm r-dnmrzs r-bnwqim r-1plcrui r-lrvibr r-16eto9q"><g><path d="M14 6c0 2.21-1.791 4-4 4S6 8.21 6 6s1.791-4 4-4 4 1.79 4 4zm-4 5c-2.352 0-4.373.85-5.863 2.44-1.477 1.58-2.366 3.8-2.632 6.46l-.11 1.1h17.21l-.11-1.1c-.266-2.66-1.155-4.88-2.632-6.46C14.373 11.85 12.352 11 10 11zm13.759-3.83c-.355-.69-1.059-1.13-1.84-1.17-.66-.03-1.347.22-1.918.79-.573-.57-1.259-.82-1.92-.79-.781.04-1.485.48-1.84 1.17-.358.71-.339 1.62.206 2.59.541.97 1.601 1.99 3.352 2.98l.202.12.201-.12c1.751-.99 2.811-2.01 3.352-2.98.544-.97.563-1.88.205-2.59z"></path></g></svg></div>
			<div>
				<span>Only people in @{props.whoseCircle}’s Twitter Circle can see this Tweet</span>
				{props.learnMore ? <a href="/">Learn more</a> : []}
			</div>
		</div>
	</div>;

let Tweet = (props: TweetProps) => {
	let t = props.t;
	let p = props.u;
	let id_str = props.t.id_str;
	let user_id_str = props.t.user_id_str;
	if (!p)
		return <AnonymousTweet t={t}/>;

	let selectTweet = (e: JSX.TargetedMouseEvent<HTMLElement>) => {
		e.preventDefault();
		logic.navigate("thread/"+id_str);
	};
	let selectUser = (e: JSX.TargetedMouseEvent<HTMLAnchorElement>) => {
		e.preventDefault();
		e.stopPropagation();
		logic.navigate("profile/"+user_id_str);
	};
	let dumpTweet = (e: JSX.TargetedMouseEvent<HTMLAnchorElement>) => {
		e.preventDefault();
		console.log(t);
	};
	// let userPath = "/"+props.u.screen_name;
	let userPath = "/profile/"+user_id_str;

	let embeds = [];
	// videos appear as type="photo" in entities, and type="video" in extended_entities
	let entities = props.t.extended_entities || props.t.entities;
	if (entities !== undefined && entities.media !== undefined) {
		let media = entities.media;
		let items = media.map((media: MediaEntity) =>
			(media.type == "video" || media.type == "animated_gif")
			? <TweetVideo entity={media}/>
			: <TweetImage src={media.media_url_https + "?name=small"} title={media.ext_alt_text} onClick={
				(e: JSX.TargetedMouseEvent<HTMLElement>) => {
					e.preventDefault();
					props.showMediaViewer([media.media_url_https]);
				}
			}/>);
		if (items.length != 1) {
			embeds.push(<MediaGrid items={items}/>);
		} else {
			// can this be done with CSS?
			let width, height, m0 = media[0];
			if (m0.original_info !== undefined) {
				width = m0.original_info.width;
				height = m0.original_info.height;
			} else if (m0.sizes === undefined) {
				// arbitrary values to get a specific aspect ratio
				width = 100;
				height = 75.0977;
			} else if (Array.isArray(m0.sizes)) {
				let last = m0.sizes[m0.sizes.length-1];
				width = last.w;
				height = last.h;
			} else {
				width = m0.sizes.large.w;
				height = m0.sizes.large.h;
			}
			let columnWidth = props.focus ? 566 : 506;
			let maxHeight = props.focus ? 900 /* <- guessed */ : 510;
			let aspect = width / height;
			if (aspect < 0.75) aspect = 0.75;
			if (aspect > 5) aspect = 5;
			let fitHeight = columnWidth / aspect;
			let fitWidth = maxHeight * aspect;
			if (fitHeight > maxHeight) {
				width = fitWidth;
				height = maxHeight;
			} else {
				width = columnWidth;
				height = fitHeight;
			}
			embeds.push(<div><div class="t20230624-embed-rounded-corners" style={`display: flex; width: ${width}px; height: ${height}px;`}>{items[0]}</div></div>);
		}
	}
	if (t.quoted_status)
		embeds.push(<QuotedTweet t={t.quoted_status} u={t.quoted_status.user} showMediaViewer={props.showMediaViewer} showReplyingTo={props.showReplyingTo}/>);
	if (t.card) {
		let n = t.card.name;
		if (n == "player")
			embeds.push(<SmallVideoEmbed card={t.card}/>);
		else if (n == "summary")
			embeds.push(<SmallVideoEmbed card={t.card}/>);
		else if (n == "summary_large_image")
			embeds.push(<SummaryLargeImage card={t.card}/>);
		else if (
			n == "poll2choice_text_only" ||
			n == "poll3choice_text_only" ||
			n == "poll4choice_text_only")
			embeds.push(<Poll card={t.card}/>);
		else
			embeds.push(<div class="t20230624-embed-rounded-corners t20230403-contents">Unsupported card type {n}</div>);
	}

	let focusClass = props.focus
		? "t20230403-tweet-focused"
		: "t20230403-tweet-unfocused";

	let timestamp = props.t.created_at ? props.t.created_at : tweetIdToEpoch(props.t.id_str);

	return <div class={"t20230403-tweet "+focusClass} tabIndex={0} onClick={selectTweet}>
		{t.context_icon ?
		<div class="t20230403-tweet-split t20230705-tweet-context">
			<div class="t20230403-avatar-column">
				{
				t.context_icon == "retweet" ? <svg class="t20230706-context-icon" viewBox="0 0 24 24" aria-hidden="true"><g><path d="M4.75 3.79l4.603 4.3-1.706 1.82L6 8.38v7.37c0 .97.784 1.75 1.75 1.75H13V20H7.75c-2.347 0-4.25-1.9-4.25-4.25V8.38L1.853 9.91.147 8.09l4.603-4.3zm11.5 2.71H11V4h5.25c2.347 0 4.25 1.9 4.25 4.25v7.37l1.647-1.53 1.706 1.82-4.603 4.3-4.603-4.3 1.706-1.82L18 15.62V8.25c0-.97-.784-1.75-1.75-1.75z"></path></g></svg> :
				t.context_icon == "pin" ? <svg class="t20230706-context-icon" viewBox="0 0 24 24" aria-hidden="true"><g><path d="M7 4.5C7 3.12 8.12 2 9.5 2h5C15.88 2 17 3.12 17 4.5v5.26L20.12 16H13v5l-1 2-1-2v-5H3.88L7 9.76V4.5z"></path></g></svg> :
				<span>{t.context_icon}</span>
				}
			</div>
			<div class="t20230403-main-column">{
				t.context_icon == "retweet" ? (props.hideContext ? "[redacted]" : t.context_user) + " Retweeted" :
				t.context_icon == "pin" ? "Pinned Tweet" :
				"Missing context description: " + t.context_icon
			}
			</div>
		</div>
		: []}
		<div class="t20230403-tweet-split">
			<div class="t20230403-avatar-column">
				<a href={userPath} onClick={selectUser}>
					<div class="t20230403-avatar-box">
						<img alt="" draggable={true} src={props.u.profile_image_url_https} class="t20230403-avatar"/>
					</div>
				</a>
				{t.line && !props.focus ? <div class="t20230624-thread-line-below"></div> : []}
			</div>
			<div class="t20230403-main-column">
				{props.focus
				?
				<div class="t20230627-profile-li-header">
					<a href={userPath} onClick={selectUser} class="t20230627-profile-li-header-1">
						<div class="t20230403-user-line-displayname">
							{p.name}
						</div>
						{p.protected
							? <svg class="t20230627-padlock" viewBox="0 0 24 24" aria-label="Protected account" role="img" data-testid="icon-lock"><g><path d="M17.5 7H17v-.25c0-2.76-2.24-5-5-5s-5 2.24-5 5V7h-.5C5.12 7 4 8.12 4 9.5v9C4 19.88 5.12 21 6.5 21h11c1.39 0 2.5-1.12 2.5-2.5v-9C20 8.12 18.89 7 17.5 7zM13 14.73V17h-2v-2.27c-.59-.34-1-.99-1-1.73 0-1.1.9-2 2-2 1.11 0 2 .9 2 2 0 .74-.4 1.39-1 1.73zM15 7H9v-.25c0-1.66 1.35-3 3-3 1.66 0 3 1.34 3 3V7z"></path></g></svg>
							: []}
					</a>
					<div class="t20230627-profile-li-header-2">
						<span class="t20230403-user-line-handle">@{p.screen_name}</span>
						{/*p.followed_by ? <span class="t20230627-profile-badge">Follows you</span> : []*/}
					</div>
				</div>
				:
				<>
				<div class="t20230403-user-line">
					<a class="t20230403-user-line-displayname" href={userPath} onClick={selectUser}>{props.u.name}</a>
					<a class="t20230403-user-line-handle" href={userPath} onClick={selectUser} tabIndex={-1}>@{props.u.screen_name}</a>
					<span class="t20230403-user-line-punctuation">·</span>
					<a class="t20230403-user-line-time" href={`https://twitter.com/${props.u.screen_name}/status/${props.t.id_str}`} onClick={dumpTweet}>{
						dateFormat(timestamp)}</a>
					<span class="t20230403-user-line-menu"></span>
				</div>
				{(props.showReplyingTo && t.in_reply_to_status_id_str ) ?
					<div class="t20230805-replying-to">Replying to <a href={"/profile/"+t.in_reply_to_user_id_str}>@{t.in_reply_to_screen_name}</a></div> : []}
				<div class="t20230403-contents"><TweetText tweet={props.t}/></div>
				{embeds.length ? <div class="t20230624-embeds">{embeds}</div> : []}
				{props.t.limited_actions === "limit_trusted_friends_tweet" ? <VisibilityNote whoseCircle={props.t.circle ? props.t.circle.screen_name : "unknown"} box={true} learnMore={false}/> : []}
				<TweetActions t={props.t}/>
				</>}
			</div>
		</div>
		{props.focus ? <>
			<div class="t20230403-contents"><TweetText tweet={props.t}/></div>
			{embeds.length ? <div class="t20230624-embeds">{embeds}</div> : []}
			<div class="t20230921-timestamp-below">
				<a href={`https://twitter.com/${props.u.screen_name}/status/${props.t.id_str}`} onClick={dumpTweet}><time dateTime={new Date(timestamp).toISOString()}>{dateFormat2(timestamp)}</time></a>
			</div>
			<TweetActions t={props.t}/>
			{props.t.limited_actions === "limit_trusted_friends_tweet" ? <VisibilityNote whoseCircle={props.t.circle ? props.t.circle.screen_name : "unknown"} box={true} learnMore={true}/> : []}
		</> : []}
	</div>;
};

class ShyTweet extends Component<TweetProps & {hideProtectedAccounts: boolean}, {revealed: boolean}> {
	constructor() {
		super();
		this.state = {revealed: false};
	}
	render() {
		let hidden = this.props.hideProtectedAccounts && this.props.u.protected && !this.state.revealed;
		let hideContext = this.props.hideProtectedAccounts && this.props.t.context_user_protected === true && !this.state.revealed;
		let show = (ev) => {
			ev.preventDefault();
			this.setState({revealed: true});
		};
		if (hidden)
			return <WithheldItem message={"This Tweet is from protected account @"+this.props.u.screen_name} action="View" handler={show}/>;
		else
			return <Tweet hideContext={hideContext} {...this.props}/>;
	}
}

let QuotedTweet = (props: TweetProps) => {
	if (!props.t.id_str)
		return <>Error, no tweet id on this one</>;
	let u = props.u || {name: "Unknown", screen_name: "unknown"}
	let userPath = "/"+u.screen_name;
	return <div class="t20230624-embed-rounded-corners">
		<div class="t20230630-qrt-top">
			<div class="t20230403-user-line">
				<a class="t20230403-user-line-displayname" href={userPath}>{u.name}</a>
				<a class="t20230403-user-line-handle" href={userPath} tabIndex={-1}>@{u.screen_name}</a>
				<span class="t20230403-user-line-punctuation">·</span>
				<a class="t20230403-user-line-time" href={`https://twitter.com/${u.screen_name}/status/${props.t.id_str}`}>{
					props.t.created_at ? dateFormat(props.t.created_at) : dateFormat(tweetIdToEpoch(props.t.id_str))}</a>
			</div>
		</div>
		<div class="t20230630-qrt-bottom t20230403-contents">
			{props.t.full_text !== undefined ? <TweetText tweet={props.t}/> : "[missing]"}
		</div>
	</div>;
}

let DMText = (props: {msgc: any}) => {
	let text = props.msgc.text;
	if (text.indexOf("<") >= 0) {
		console.log("dm message has unescaped html", props.msgc);
		return <>{text}</>;
	}
	else if (text.indexOf("&") >= 0)
		return <span dangerouslySetInnerHTML={{__html: text}}></span>;
	else
		return <>{text}</>;
};

let DMConversationItem = (props: {info: ConversationInfo}) => {
	let [cid, p0, p1, last_message] = props.info;
	if (!p1) return <div>{cid}</div>;
	let p = p1;
	let last_message_date = dateFormat(last_message.messageCreate.createdAt);
	let virtualClick = (e: JSX.TargetedMouseEvent<HTMLAnchorElement>) => {
		e.preventDefault();
		logic.navigate(new URL(e.currentTarget.href).pathname.slice(1));
	};
	return <a class="t20230912-dmselector-entry" href={"/dm/"+cid} onClick={virtualClick}>
		<div class="t20230912-dmselector-entry-avatar">
			<img width="40" height="40" src={p.profile_image_url_https}/>
		</div>
		<div>
			<div class="t20230912-dmselector-entry-user-line"><span class="t20230912-dmselector-entry-names"><span class="t20230912-dmselector-entry-displayname">{p.name}</span><span class="t20230912-dmselector-entry-handle">@{p.screen_name}</span></span><span class="t20230912-dmselector-entry-punctuation">·</span><span class="t20230912-dmselector-entry-time">{last_message_date}</span></div>
			<div class="t20230912-dmselector-entry-message"><DMText msgc={last_message.messageCreate}/></div>
		</div>
		<div class="t20230912-dmselector-entry-menubutton"></div>
	</a>;
};

let DMMessage = (props: {conv: Conversation, msg: any, index: number}) => {
	let msgc = props.msg.messageCreate;
	let our_user_id = props.conv[1].user_id_str;
	let ours = msgc.senderId == our_user_id;
	let text = msgc.text;
	let withDate = true;
	let messages = props.conv[0].messages;
	if (props.index+1 < messages.length) {
		let next_msgc = messages[props.index+1].messageCreate;
		let next_ours = next_msgc.senderId == our_user_id;
		withDate = ours != next_ours; // show date whenever speaker switches
	}
	return <div class={ours ? "t20230912-dm-right" : "t20230912-dm-left"}>
		<div class="t20230912-dm-bubble-container">
			<div>
				<div class="t20230912-dm-bubble"><DMText msgc={msgc}/></div>
				<div class="t20230912-dm-actions"></div>
			</div>
		</div>
		{withDate
		? <div class="t20230912-dm-timestamp">{dateFormat3(msgc.createdAt)}</div>
		: ""}
	</div>;
};

let ProfileItem = (props: ProfileProps) => {
	let p = props.p;
	let user_id_str = p.user_id_str;
	let selectUser = (e: JSX.TargetedMouseEvent<HTMLElement>) => {
		let selObj = window.getSelection();
		if (selObj && !selObj.isCollapsed)
			return; // user is probably trying to select the bio text, let them
		e.preventDefault();
		logic.navigate("profile/"+user_id_str);
	};
	let userPath = "/"+p.screen_name;
	return <div class="t20230627-profile-li" onClick={selectUser}>
		<div class="t20230403-avatar-column">
			<a href={userPath}>
				<div class="t20230403-avatar-box">
					<img alt="" draggable={true} src={p.profile_image_url_https} class="t20230403-avatar"/>
				</div>
			</a>
		</div>
		<div class="t20230403-main-column">
			<div class="t20230627-profile-li-header">
				<a href={userPath} class="t20230627-profile-li-header-1">
					<div class="t20230403-user-line-displayname">
						{p.name}
					</div>
					{p.protected
						? <svg class="t20230627-padlock" viewBox="0 0 24 24" aria-label="Protected account" role="img" data-testid="icon-lock"><g><path d="M17.5 7H17v-.25c0-2.76-2.24-5-5-5s-5 2.24-5 5V7h-.5C5.12 7 4 8.12 4 9.5v9C4 19.88 5.12 21 6.5 21h11c1.39 0 2.5-1.12 2.5-2.5v-9C20 8.12 18.89 7 17.5 7zM13 14.73V17h-2v-2.27c-.59-.34-1-.99-1-1.73 0-1.1.9-2 2-2 1.11 0 2 .9 2 2 0 .74-.4 1.39-1 1.73zM15 7H9v-.25c0-1.66 1.35-3 3-3 1.66 0 3 1.34 3 3V7z"></path></g></svg>
						: []}
				</a>
				<div class="t20230627-profile-li-header-2">
					<span class="t20230403-user-line-handle">@{p.screen_name}</span>
					{p.followed_by ? <span class="t20230627-profile-badge">Follows you</span> : []}
				</div>
			</div>
			<div class="t20230627-profile-li-bio t20230403-contents">
				{p.description
				? <TextWithEntities full_text={p.description} entities={p.entities && p.entities.description} display_text_range={[0, p.description.length]}/>
				: "[missing]"}
			</div>
		</div>
	</div>;
};

let pluralize = (n: number, counter: string) => n == 1 ? counter : counter + "s";

let Profile2 = (p: LegacyProfile) =>
	<div class="t20230627-profile">
		<a class="t20230627-profile-banner">
			{p.profile_banner_url ? <img src={p.profile_banner_url} draggable={true}/> : []}
		</a>
		<div class="t20230627-profile-info">
			<div class="t20230627-profile-picture-and-actions">
				<div class="t20230627-profile-picture">
						<div class="t20230627-profile-picture-square-aspect"></div>
						<div class="t20230627-profile-picture-outer-rim"></div>
						<img alt="Opens profile photo" draggable={true} src={p.profile_image_url_https ? p.profile_image_url_https.replace("normal", "200x200") : ""}/>
				</div>
			</div>
			<div class="t20230627-profile-title">
				<div class="t20230627-profile-li-header">
					<a href="#" class="t20230627-profile-li-header-1">
						<div class="t20230403-user-line-displayname">
							{p.name}
						</div>
						{p.protected
							? <svg class="t20230627-padlock" viewBox="0 0 24 24" aria-label="Protected account" role="img" data-testid="icon-lock"><g><path d="M17.5 7H17v-.25c0-2.76-2.24-5-5-5s-5 2.24-5 5V7h-.5C5.12 7 4 8.12 4 9.5v9C4 19.88 5.12 21 6.5 21h11c1.39 0 2.5-1.12 2.5-2.5v-9C20 8.12 18.89 7 17.5 7zM13 14.73V17h-2v-2.27c-.59-.34-1-.99-1-1.73 0-1.1.9-2 2-2 1.11 0 2 .9 2 2 0 .74-.4 1.39-1 1.73zM15 7H9v-.25c0-1.66 1.35-3 3-3 1.66 0 3 1.34 3 3V7z"></path></g></svg>
							: []}
					</a>
					<div class="t20230627-profile-li-header-2">
						<span class="t20230403-user-line-handle">@{p.screen_name}</span>
						{p.followed_by ? <span class="t20230627-profile-badge">Follows you</span> : []}
					</div>
				</div>
			</div>
			<div class="t20230627-profile-description">
				{p.description
				? <TextWithEntities full_text={p.description} entities={p.entities && p.entities.description} display_text_range={[0, p.description.length]}/>
				: "[missing]"}
			</div>
			<div class="t20230627-profile-attributes">
			</div>
			<div class="t20230627-profile-numbers">{[
				<a href={`/profile/${p.user_id_str}/following`}><span>{p.friends_count}</span> <span>Following</span></a>,
				<a href={`/profile/${p.user_id_str}/followers`}><span>{p.followers_count}</span> <span>{pluralize(p.followers_count, "Follower")}</span></a>
			]}</div>
			<div class="t20230627-profile-context">
			</div>
		</div>
	</div>

let Profile = (props: ProfileProps) => Profile2(props.p);

let Header = (props: {}) =>
	<div class="t20230628-timeline-header">
		<div class="t20230628-timeline-header-profile">
			<div class="t20230628-timeline-header-return-button">
				<div class="t20230628-timeline-header-button" onClick={logic.back.bind(logic)}>
					<svg viewBox="0 0 24 24" aria-hidden="true"><g><path d="M7.414 13l5.043 5.04-1.414 1.42L3.586 12l7.457-7.46 1.414 1.42L7.414 11H21v2H7.414z"></path></g></svg>
				</div>
			</div>
		</div>
	</div>;

type HistogramProps = {
	year?: number | undefined,
	month?: number | undefined,
	max_tweets: number,
	histogram: [number, number[]][],
	selectMonth: (year: number, month: number) => void, // 1=jan
	toggleMode?: () => void,
}

let monthNames = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

let Histogram = (props: HistogramProps) => <>
	{props.histogram.map((row)=>
		<div class={"t20160910-histogram" + (row[0]==props.year || props.year===undefined ? " t20160910-active" : "")}>
			<h3>{row[0]}</h3><ol class="t20160910-months t20160910-unstyled">{row[1].map((count, month)=> count
				? <li><a href="#" class={"t20160910-with-tweets" + (row[0]==props.year && month+1==props.month && props.year !== undefined ? " t20160910-active" : "")}
					onClick={(ev)=>{ev.preventDefault();props.selectMonth(row[0], month+1)}}
					title={`${monthNames[month]} ${row[0]}: ${count} Tweets`}>
						<span class="t20160910-bar" style={`height: ${100*count/props.max_tweets}%;`}></span></a></li>
				: <li class="t20160910-without-tweets" title=""></li>
			)}</ol>
		</div>
	)}
	{props.toggleMode !== undefined ? <a class="histogram-mode-button" href="#" onClick={(ev) => { ev.preventDefault(); props.toggleMode() }}>Mode</a> : []}
	{props.year !== undefined ? <a href="#">Reset selection</a> : []}
</>;

let Sidebar = (props: {children: ComponentChildren}) =>
	<div class="sidebar-container"><div class="t20160910-sidebar-nav">
		{props.children}
	</div></div>;

type Tab = {
	label: string,
	navigate_to: string
}

type NavBarProps = {
	items: Tab[],
	selected: number
}

let NavBar = (props: NavBarProps) =>
	<div class="t20230630-navbar">
		{props.items.map((tab, index) =>
			<div class={"t20230630-navbutton" + (index == props.selected ? " navbar-selected" : "")}
				onClick={(e) => logic.navigate(tab.navigate_to)}
			>
				<div class="t20230630-navbutton-text">{tab.label}</div>
			</div>
		)}
	</div>;

type MediaViewerProps = {
	urls: string[]
}

type AppState = {
	mediaViewer?: MediaViewerProps,
	theme: string,
	histogramMode: number,
	hideProtectedAccounts: boolean
};

class Modal extends Component<{children: ComponentChildren, onEscape: ()=>void}> {
	ref = createRef();
	componentDidMount() {
		this.ref.current.focus();
		window.addEventListener("keydown", this);
	}
	componentWillUnmount() {
		window.removeEventListener("keydown", this);
	}
	handleEvent(ev) { // magic function name that will be looked up on the event listener
		if(ev.key === "Escape")
			this.props.onEscape();
	}
	render() {
		return <div class="modal-overlay" tabIndex={0} ref={this.ref}>{this.props.children}</div>;
	}
}

class App extends Component<AppProps, AppState> {
	constructor() {
		super();
		this.state = {theme: "dim", histogramMode: 0, hideProtectedAccounts: false};
	}
	render() {
		let top = this.props.topProfile;
		let parts = [];
		if (this.props.tab >= 100) {
			let uid = this.props.topProfile.user_id_str;
			let tabs: Tab[] = [
				{label:"Followers", navigate_to: `profile/${uid}/followers`},
				{label:"Following", navigate_to: `profile/${uid}/following`}
			];
			parts.push(<Header/>);
			parts.push(<NavBar items={tabs} selected={this.props.tab-100}/>);
		} else if (top) {
			let uid = this.props.topProfile.user_id_str;
			let tabs: Tab[] = [
				{label: "Tweets",  navigate_to: `profile/${uid}`},
				{label: "Replies", navigate_to: `profile/${uid}/with_replies`},
				{label: "Media",   navigate_to: `profile/${uid}/media`},
				{label: "Likes",   navigate_to: `profile/${uid}/likes`}
			];
			if (top.observer)
				tabs.push({label: "Bookmarks", navigate_to: `profile/${uid}/bookmarks`});
			else
				tabs.push({label: "Interactions", navigate_to: `profile/${uid}/interactions`});
			parts.push(<Header/>);
			parts.push(<Profile p={top}/>);
			parts.push(<NavBar items={tabs} selected={this.props.tab}/>);
		} else {
			parts.push(<Header/>);
		}
		let showMediaViewer = (urls: string[]) => {
			this.setState({mediaViewer: {urls: urls}});
		};
		let hideMediaViewer = () => {
			this.setState({mediaViewer: undefined});
		};
		if (this.props.conversations) {
			document.body.parentElement.style.height = "100%";
			document.body.style.height = "100%";
			document.body.style.alignItems = "stretch";
			return <div class={`common-frame-990 theme-${this.state.theme}`}>
				<div class="t20230912-dmselector">
					<div class="t20230912-dmselector-header">Messages</div>
					<div class="t20230912-dmselector-scrollable">
						{this.props.conversations.map((x)=> <DMConversationItem info={x}/>)}
					</div>
				</div>
				<div class="t20230912-dm-conversation-column">
					<div class="t20230912-dm-header">
						<img width="32" height="32" src={this.props.conversation
							? this.props.conversation[2].profile_image_url_https
							: ""}/>
						<span>
							{this.props.conversation
							? this.props.conversation[2].name
							: ""}
						</span>
					</div>
					<div class="t20230912-dm-conversation">
						{this.props.conversation
						 ? this.props.conversation[0].messages.map((x, i)=> <DMMessage conv={this.props.conversation} msg={x} index={i}/>)
						 : "Select a message"}
					 </div>
					<div class="t20230912-dm-editor">
						<div></div>
						<div>What would you have said?</div>
					</div>
				</div>
			</div>;
		} else {
			delete document.body.parentElement.style.height;
			delete document.body.style.height;
			delete document.body.style.alignItems;
			parts.push(...(this.props.profiles || []).map(profile => <ProfileItem key={profile.user_id_str} p={profile}/>));
			parts.push(...(this.props.tweets || []).map(tweet => tweet && tweet.full_text ?
				<ShyTweet key={tweet.id_str} hideProtectedAccounts={this.state.hideProtectedAccounts} t={tweet} u={tweet.user} focus={tweet.id_str == this.props.focusTweetId} showMediaViewer={showMediaViewer} showReplyingTo={!!top}/> : []));
			if (this.props.final_link)
				parts.push(<div class="timeline-system-message">
					<a class="deemphasized-link" href={this.props.final_link.href}>{this.props.final_link.content}</a>
				</div>);
			let timeline = <div class={`common-frame-600 theme-${this.state.theme}`}>
				<div class="t20230403-timeline" tabIndex={0}>
					{parts}
				</div>
			</div>;
			let setTheme = (theme: string) => (ev) => {
				ev.preventDefault();
				this.setState({theme});
			};
			let themeLinks = [];
			for (let theme of ["light", "dim"])
				if (this.state.theme != theme) {
					if (themeLinks.length > 0)
						themeLinks.push(" ");
					themeLinks.push(<a href="#" onClick={setTheme(theme)}>{theme}</a>);
				}
			let toggleHideProtectedAccounts = (ev) => {
				ev.preventDefault();
				this.setState({hideProtectedAccounts: !this.state.hideProtectedAccounts});
			};
			let availableHistograms =
				this.props.histograms ? this.props.histograms.filter((h)=>!!h) : [];
			let toggleHistogramMode = () => {
				let h = this.state.histogramMode + 1;
				this.setState({histogramMode: h < availableHistograms.length ? h : 0});
			};
			let selectMonth = (year, month) => {
				let from = new Date(year, month-1);
				let until = new Date(year, month);
				let name = availableHistograms[this.state.histogramMode].name;
				let q;
				if (false) {
					q = `?from=${from.getTime()}&until=${until.getTime()}`;
					if (name == 'ot') // this omission works out with the current implicit filtering modes
						q += "&by=" + name;
				} else {
					let usp = new URLSearchParams(window.location.search);
					usp.delete("by");
					usp.set("from", ""+from.getTime());
					usp.set("until", ""+until.getTime());
					if (name == 'ot') // this omission works out with the current implicit filtering modes
						usp.set("by", name);
					q = "?"+usp.toString();
				}
				logic.navigate(window.location.pathname.slice(1), q);
			};
			let submitSearch = (ev) => {
				ev.preventDefault();
				let usp = new URLSearchParams();
				usp.set("q", ev.target.q.value);
				logic.navigate("search", "?"+usp.toString());
			};
			let sidebar = <Sidebar>
				<h3>Search</h3>
				<form action="/search" method="get" onSubmit={submitSearch}>
				<input name="q" style={{width: "100%", boxSizing: "border-box"}} autocomplete="off"/>
				</form>
				<h3>Settings</h3>
				<span>Set theme: </span>{themeLinks}<br/>
				<a href="#" onClick={toggleHideProtectedAccounts}>{
					this.state.hideProtectedAccounts ? "Show" : "Hide"} Tweets by locked accounts</a><br/>
				<a href="/dm">Go to Direct Messages</a>
				<Histogram
					// year={2021}
					// month={10}
					max_tweets={availableHistograms.length ? availableHistograms[this.state.histogramMode].max_tweets : 0}
					histogram={availableHistograms.length ? availableHistograms[this.state.histogramMode].histogram : []}
					selectMonth={selectMonth}
					toggleMode={availableHistograms.length > 1 ? toggleHistogramMode : undefined}/>
			</Sidebar>;
			if (this.state.mediaViewer) {
				let escapeByClick = (ev) => {
					if (ev.target == ev.currentTarget)
						hideMediaViewer();
				};
				let mediaViewer =
					<Modal onEscape={hideMediaViewer}>
						<div class="media-viewer" onClick={escapeByClick}>
							<img src={this.state.mediaViewer.urls[0]}/></div></Modal>;
				return [timeline, sidebar, mediaViewer];
			} else
				return [timeline, sidebar];
		}
	}
}

let div = null;
let logic = new Logic((props) => render(h(App, props), div));
window.addEventListener("popstate", (event) => logic.navigateReal(
	window.location.pathname.slice(1),
	window.location.search));
window.addEventListener("load", () => {
	div = document.getElementById("root");
	render(<App tweets={[]} tab={0}/>, div);
	logic.navigateReal(
		window.location.pathname.slice(1),
		window.location.search);
}, {once: true});
