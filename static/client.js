import { h, render, Component, Fragment } from 'preact';
class Logic {
    constructor(updateFn) {
        this.updateFn = updateFn;
    }
    back() {
        window.history.back();
    }
    navigate(i) {
        window.history.pushState(i, "", "/" + i);
        this.navigateReal(i);
    }
    navigateReal(i) {
        let api_call;
        let tab = 0;
        let m;
        if (i == "") {
            api_call = "everyone";
        }
        else if ((m = i.match(/thread\/(\d+)$/)) !== null) {
            api_call = i; // easy
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
        else {
            api_call = i; // fall-back
        }
        let self = this;
        fetch('/api/' + api_call).then((response) => response.json().then((data) => {
            data["tab"] = tab;
            self.updateFn(data);
        }));
    }
}
let TweetActions = (props) => h("div", { class: "t20230403-actions" },
    h("div", { class: "t20230403-action-item-outer t20230403-action-reply" },
        h("div", { tabIndex: 0, class: "t20230403-action-item-inner" },
            h("svg", { class: "t20230403-action-icon", viewBox: "0 0 24 24" },
                h("g", null,
                    h("path", { d: "M1.751 10c0-4.42 3.584-8 8.005-8h4.366c4.49 0 8.129 3.64 8.129 8.13 0 2.96-1.607 5.68-4.196 7.11l-8.054 4.46v-3.69h-.067c-4.49.1-8.183-3.51-8.183-8.01zm8.005-6c-3.317 0-6.005 2.69-6.005 6 0 3.37 2.77 6.08 6.138 6.01l.351-.01h1.761v2.3l5.087-2.81c1.951-1.08 3.163-3.13 3.163-5.36 0-3.39-2.744-6.13-6.129-6.13H9.756z" }))),
            h("span", { class: "t20230403-action-text" },
                h("span", null, props.t.reply_count == "0" ? "" : props.t.reply_count)))),
    h("div", { class: "t20230403-action-item-outer t20230403-action-rt" },
        h("div", { tabIndex: 0, class: "t20230403-action-item-inner" },
            h("svg", { class: "t20230403-action-icon", viewBox: "0 0 24 24" },
                h("g", null,
                    h("path", { d: "M4.75 3.79l4.603 4.3-1.706 1.82L6 8.38v7.37c0 .97.784 1.75 1.75 1.75H13V20H7.75c-2.347 0-4.25-1.9-4.25-4.25V8.38L1.853 9.91.147 8.09l4.603-4.3zm11.5 2.71H11V4h5.25c2.347 0 4.25 1.9 4.25 4.25v7.37l1.647-1.53 1.706 1.82-4.603 4.3-4.603-4.3 1.706-1.82L18 15.62V8.25c0-.97-.784-1.75-1.75-1.75z" }))),
            h("span", { class: "t20230403-action-text" },
                h("span", null, props.t.retweet_count == "0" ? "" : props.t.retweet_count)))),
    h("div", { class: "t20230403-action-item-outer t20230403-action-like" + ((props.t.favoriters || []).length > 0 ? " activated" : "") },
        h("div", { tabIndex: 0, class: "t20230403-action-item-inner" },
            h("svg", { class: "t20230403-action-icon inactive-icon", viewBox: "0 0 24 24" },
                h("g", null,
                    h("path", { d: "M16.697 5.5c-1.222-.06-2.679.51-3.89 2.16l-.805 1.09-.806-1.09C9.984 6.01 8.526 5.44 7.304 5.5c-1.243.07-2.349.78-2.91 1.91-.552 1.12-.633 2.78.479 4.82 1.074 1.97 3.257 4.27 7.129 6.61 3.87-2.34 6.052-4.64 7.126-6.61 1.111-2.04 1.03-3.7.477-4.82-.561-1.13-1.666-1.84-2.908-1.91zm4.187 7.69c-1.351 2.48-4.001 5.12-8.379 7.67l-.503.3-.504-.3c-4.379-2.55-7.029-5.19-8.382-7.67-1.36-2.5-1.41-4.86-.514-6.67.887-1.79 2.647-2.91 4.601-3.01 1.651-.09 3.368.56 4.798 2.01 1.429-1.45 3.146-2.1 4.796-2.01 1.954.1 3.714 1.22 4.601 3.01.896 1.81.846 4.17-.514 6.67z" }))),
            h("svg", { class: "t20230403-action-icon active-icon", viewBox: "0 0 24 24" },
                h("g", null,
                    h("path", { d: "M20.884 13.19c-1.351 2.48-4.001 5.12-8.379 7.67l-.503.3-.504-.3c-4.379-2.55-7.029-5.19-8.382-7.67-1.36-2.5-1.41-4.86-.514-6.67.887-1.79 2.647-2.91 4.601-3.01 1.651-.09 3.368.56 4.798 2.01 1.429-1.45 3.146-2.1 4.796-2.01 1.954.1 3.714 1.22 4.601 3.01.896 1.81.846 4.17-.514 6.67z" }))),
            h("span", { class: "t20230403-action-text" },
                h("span", null, props.t.favorite_count == "0" ? "" : props.t.favorite_count)))),
    false ? h("div", { class: "t20230403-action-item-outer t20230403-action-views" },
        h("div", { tabIndex: 0, class: "t20230403-action-item-inner" },
            h("svg", { class: "t20230403-action-icon", viewBox: "0 0 24 24" },
                h("g", null,
                    h("path", { d: "M8.75 21V3h2v18h-2zM18 21V8.5h2V21h-2zM4 21l.004-10h2L6 21H4zm9.248 0v-7h2v7h-2z" }))),
            h("span", { class: "t20230403-action-text" },
                h("span", null, "10")))) : [],
    h("div", { class: "t20230403-action-item-outer t20230403-action-share" },
        h("div", { tabIndex: 0, class: "t20230403-action-item-inner" },
            h("svg", { class: "t20230403-action-icon", viewBox: "0 0 24 24" },
                h("g", null,
                    h("path", { d: "M12 2.59l5.7 5.7-1.41 1.42L13 6.41V16h-2V6.41l-3.3 3.3-1.41-1.42L12 2.59zM21 15l-.02 3.51c0 1.38-1.12 2.49-2.5 2.49H5.5C4.11 21 3 19.88 3 18.5V15h2v3.5c0 .28.22.5.5.5h12.98c.28 0 .5-.22.5-.5L19 15h2z" }))))));
let MediaGrid = (props) => {
    let items = props.items;
    return h("div", { class: "t20230624-embed-rounded-corners" },
        h("div", { class: "t20230624-media-relative" },
            h("div", { class: "t20230624-media-aspect-keeper" }),
            items.length == 0 ? [] :
                items.length == 1 ? items[0] :
                    items.length == 2 ?
                        h("div", { class: "t20230701-media-hdiv" }, items) :
                        items.length == 3 ?
                            h("div", { class: "t20230701-media-hdiv" },
                                items[0],
                                h("div", { class: "t20230701-media-vdiv" }, [items[1], items[2]]))
                            :
                                h("div", { class: "t20230701-media-hdiv" },
                                    h("div", { class: "t20230701-media-vdiv" }, [items[0], items[1]]),
                                    h("div", { class: "t20230701-media-vdiv" }, [items[2], items[3]]))));
};
let TweetImage = (props) => h("div", { class: "t20230624-image-div", style: { "background-image": `url('${props.src}')` } }); /*todo: proper escape*/
let dateFormat = (datestr) => {
    let now = new Date();
    let date = new Date(datestr);
    let deltaSec = (now.getTime() - date.getTime()) / 1000;
    let months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
    if (deltaSec < 60)
        return "now";
    if (deltaSec < 60 * 60)
        return `${Math.floor(deltaSec / 60)}m`;
    if (deltaSec < 24 * 60 * 60)
        return `${Math.floor(deltaSec / 60 / 24)}h`;
    if (now.getFullYear() != date.getFullYear())
        return `${months[date.getMonth()]} ${date.getDate()}, ${date.getFullYear()}`;
    return `${months[date.getMonth()]} ${date.getDate()}`;
};
let SimpleTweetText = (props) => {
    let tweet = props.tweet;
    let text = tweet.full_text;
    if (tweet.display_text_range !== undefined) {
        text = text.slice(tweet.display_text_range[0], tweet.display_text_range[1]);
    }
    if (text.indexOf("<") >= 0) {
        console.log("tweet has unescaped html", tweet);
        return h(Fragment, null, "text");
    }
    return h("span", { dangerouslySetInnerHTML: { __html: text } });
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
        indices: translateRange(text, e.indices[0], e.indices[1])
    }));
};
let partsForTweetEntities = (text, entities) => {
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
let TweetText = (props) => {
    let tweet = props.tweet;
    return TextWithEntities({
        full_text: tweet.full_text,
        entities: tweet.entities,
        display_text_range: tweet.display_text_range,
        card_url: tweet.card && tweet.card.url,
        quoted_status_id_str: tweet.quoted_status && tweet.quoted_status.id_str
    });
};
let TextWithEntities = (props) => {
    let full_text = props.full_text;
    let entities = partsForTweetEntities(full_text, props.entities);
    entities.sort((a, b) => a.indices[0] - b.indices[0]);
    let [displayStart, displayEnd] = props.display_text_range !== undefined
        ? translateRange(props.full_text, props.display_text_range[0], props.display_text_range[1])
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
        let last = n == parts.length - 1;
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
            let isLast = index == parts.length - 1;
            if (!part.text.trim() && (isFirst || isLast))
                return;
            let text = part.text;
            if (isLast)
                text = text.replace(/(\s+$)/g, '');
            if (text.indexOf("<") >= 0)
                vdom.push(text);
            else
                vdom.push(h("span", { dangerouslySetInnerHTML: { __html: text } }));
        }
        else if (part.kind == "url") {
            let urle = part;
            vdom.push(h("a", { href: urle.expanded_url }, urle.display_url));
        }
        else if (part.kind == "mention") {
            let usere = part;
            vdom.push(h("a", { href: "/profile/" + usere.id_str },
                "@",
                usere.screen_name));
        }
        else {
            vdom.push(`[unhandled ${part.kind} entity]`);
        }
    });
    return h(Fragment, null, vdom);
};
let AnonymousTweet = (props) => {
    return h("div", { class: "t20230403-tweet t20230403-tweet-unfocused", tabIndex: 0 },
        h("div", { class: "t20230403-tweet-split" },
            h("div", { class: "t20230403-avatar-column" }),
            h("div", { class: "t20230403-main-column" },
                h("div", { class: "t20230403-user-line" },
                    h("span", { class: "t20230403-user-line-displayname" }, "Unknown"),
                    h("span", { class: "t20230403-user-line-handle", tabIndex: -1 }, "@unknown"),
                    h("span", { class: "t20230403-user-line-punctuation" }, "\u00B7"),
                    h("a", { class: "t20230403-user-line-time", href: `https://twitter.com/i/web/status/${props.t.id_str}` }, dateFormat(parseInt((BigInt(props.t.id_str) >> BigInt(22)).toString()) + 1288834974657)),
                    h("span", { class: "t20230403-user-line-menu" })),
                h("div", { class: "t20230403-contents" },
                    h(TweetText, { tweet: props.t })))));
};
let Tweet = (props) => {
    let t = props.t;
    let id_str = props.t.id_str;
    let user_id_str = props.t.user_id_str;
    if (!user_id_str)
        return h(AnonymousTweet, { t: t });
    let selectTweet = (e) => {
        e.preventDefault();
        logic.navigate("thread/" + id_str);
    };
    let selectUser = (e) => {
        e.preventDefault();
        e.stopPropagation();
        logic.navigate("profile/" + user_id_str);
    };
    let dumpTweet = (e) => {
        e.preventDefault();
        console.log(t);
    };
    // let userPath = "/"+props.u.screen_name;
    let userPath = "/profile/" + user_id_str;
    let embeds = [];
    if (props.t.entities !== undefined && props.t.entities.media !== undefined) {
        let items = props.t.entities.media.map((media) => h(TweetImage, { src: media.media_url_https }));
        embeds.push(h(MediaGrid, { items: items }));
    }
    if (t.quoted_status)
        embeds.push(h(QuotedTweet, { t: t.quoted_status, u: t.quoted_status.user }));
    return h("div", { class: "t20230403-tweet t20230403-tweet-unfocused", tabIndex: 0, onClick: selectTweet },
        t.context_icon ?
            h("div", { class: "t20230403-tweet-split t20230705-tweet-context" },
                h("div", { class: "t20230403-avatar-column" }, t.context_icon == "retweet"
                    ? h("svg", { class: "t20230706-context-icon", viewBox: "0 0 24 24", "aria-hidden": "true" },
                        h("g", null,
                            h("path", { d: "M4.75 3.79l4.603 4.3-1.706 1.82L6 8.38v7.37c0 .97.784 1.75 1.75 1.75H13V20H7.75c-2.347 0-4.25-1.9-4.25-4.25V8.38L1.853 9.91.147 8.09l4.603-4.3zm11.5 2.71H11V4h5.25c2.347 0 4.25 1.9 4.25 4.25v7.37l1.647-1.53 1.706 1.82-4.603 4.3-4.603-4.3 1.706-1.82L18 15.62V8.25c0-.97-.784-1.75-1.75-1.75z" })))
                    : h("span", null, t.context_icon)),
                h("div", { class: "t20230403-main-column" },
                    t.context_user,
                    " Retweeted"))
            : [],
        h("div", { class: "t20230403-tweet-split" },
            h("div", { class: "t20230403-avatar-column" },
                h("a", { href: userPath, onClick: selectUser },
                    h("div", { class: "t20230403-avatar-box" },
                        h("img", { alt: "", draggable: true, src: props.u.profile_image_url_https, class: "t20230403-avatar" }))),
                t.line ? h("div", { class: "t20230624-thread-line-below" }) : []),
            h("div", { class: "t20230403-main-column" },
                h("div", { class: "t20230403-user-line" },
                    h("a", { class: "t20230403-user-line-displayname", href: userPath, onClick: selectUser }, props.u.name),
                    h("a", { class: "t20230403-user-line-handle", href: userPath, onClick: selectUser, tabIndex: -1 },
                        "@",
                        props.u.screen_name),
                    h("span", { class: "t20230403-user-line-punctuation" }, "\u00B7"),
                    h("a", { class: "t20230403-user-line-time", href: `https://twitter.com/${props.u.screen_name}/status/${props.t.id_str}`, onClick: dumpTweet }, dateFormat(props.t.created_at)),
                    h("span", { class: "t20230403-user-line-menu" })),
                h("div", { class: "t20230403-contents" },
                    h(TweetText, { tweet: props.t })),
                embeds.length ? h("div", { class: "t20230624-embeds" }, embeds) : [],
                h(TweetActions, { t: props.t }))));
};
let QuotedTweet = (props) => {
    let userPath = "/" + props.u.screen_name;
    return h("div", { class: "t20230624-embed-rounded-corners" },
        h("div", { class: "t20230630-qrt-top" },
            h("div", { class: "t20230403-user-line" },
                h("a", { class: "t20230403-user-line-displayname", href: userPath }, props.u.name),
                h("a", { class: "t20230403-user-line-handle", href: userPath, tabIndex: -1 },
                    "@",
                    props.u.screen_name),
                h("span", { class: "t20230403-user-line-punctuation" }, "\u00B7"),
                h("a", { class: "t20230403-user-line-time", href: `https://twitter.com/${props.u.screen_name}/status/${props.t.id_str}` }, dateFormat(props.t.created_at)))),
        h("div", { class: "t20230630-qrt-bottom t20230403-contents" },
            h(TweetText, { tweet: props.t })));
};
let ProfileItem = (props) => {
    let p = props.p;
    let user_id_str = p.user_id_str;
    let selectUser = (e) => {
        e.preventDefault();
        logic.navigate("profile/" + user_id_str);
    };
    let userPath = "/" + p.screen_name;
    return h("div", { class: "t20230627-profile-li" },
        h("div", { class: "t20230403-avatar-column" },
            h("a", { href: userPath, onClick: selectUser },
                h("div", { class: "t20230403-avatar-box" },
                    h("img", { alt: "", draggable: true, src: p.profile_image_url_https, class: "t20230403-avatar" })))),
        h("div", { class: "t20230403-main-column" },
            h("div", { class: "t20230627-profile-li-header" },
                h("a", { href: userPath, onClick: selectUser, class: "t20230627-profile-li-header-1" },
                    h("div", { class: "t20230403-user-line-displayname" }, p.name),
                    p.protected
                        ? h("svg", { class: "t20230627-padlock", viewBox: "0 0 24 24", "aria-label": "Protected account", role: "img", "data-testid": "icon-lock" },
                            h("g", null,
                                h("path", { d: "M17.5 7H17v-.25c0-2.76-2.24-5-5-5s-5 2.24-5 5V7h-.5C5.12 7 4 8.12 4 9.5v9C4 19.88 5.12 21 6.5 21h11c1.39 0 2.5-1.12 2.5-2.5v-9C20 8.12 18.89 7 17.5 7zM13 14.73V17h-2v-2.27c-.59-.34-1-.99-1-1.73 0-1.1.9-2 2-2 1.11 0 2 .9 2 2 0 .74-.4 1.39-1 1.73zM15 7H9v-.25c0-1.66 1.35-3 3-3 1.66 0 3 1.34 3 3V7z" })))
                        : []),
                h("div", { class: "t20230627-profile-li-header-2" },
                    h("span", { class: "t20230403-user-line-handle" },
                        "@",
                        p.screen_name),
                    p.followed_by ? h("span", { class: "t20230627-profile-badge" }, "Follows you") : [])),
            h("div", { class: "t20230627-profile-li-bio t20230403-contents" },
                h(TextWithEntities, { full_text: p.description, entities: p.entities && p.entities.description, display_text_range: [0, p.description.length] }))));
};
let pluralize = (n, counter) => n == 1 ? counter : counter + "s";
let Profile2 = (p) => h("div", { class: "t20230627-profile" },
    h("a", { class: "t20230627-profile-banner" },
        h("img", { src: p.profile_banner_url, draggable: true })),
    h("div", { class: "t20230627-profile-info" },
        h("div", { class: "t20230627-profile-picture-and-actions" },
            h("div", { class: "t20230627-profile-picture" },
                h("div", { class: "t20230627-profile-picture-square-aspect" }),
                h("div", { class: "t20230627-profile-picture-outer-rim" }),
                h("img", { alt: "Opens profile photo", draggable: true, src: p.profile_image_url_https ? p.profile_image_url_https.replace("normal", "200x200") : "" }))),
        h("div", { class: "t20230627-profile-title" },
            h("div", { class: "t20230627-profile-li-header" },
                h("a", { href: "#", class: "t20230627-profile-li-header-1" },
                    h("div", { class: "t20230403-user-line-displayname" }, p.name),
                    p.protected
                        ? h("svg", { class: "t20230627-padlock", viewBox: "0 0 24 24", "aria-label": "Protected account", role: "img", "data-testid": "icon-lock" },
                            h("g", null,
                                h("path", { d: "M17.5 7H17v-.25c0-2.76-2.24-5-5-5s-5 2.24-5 5V7h-.5C5.12 7 4 8.12 4 9.5v9C4 19.88 5.12 21 6.5 21h11c1.39 0 2.5-1.12 2.5-2.5v-9C20 8.12 18.89 7 17.5 7zM13 14.73V17h-2v-2.27c-.59-.34-1-.99-1-1.73 0-1.1.9-2 2-2 1.11 0 2 .9 2 2 0 .74-.4 1.39-1 1.73zM15 7H9v-.25c0-1.66 1.35-3 3-3 1.66 0 3 1.34 3 3V7z" })))
                        : []),
                h("div", { class: "t20230627-profile-li-header-2" },
                    h("span", { class: "t20230403-user-line-handle" },
                        "@",
                        p.screen_name),
                    p.followed_by ? h("span", { class: "t20230627-profile-badge" }, "Follows you") : []))),
        h("div", { class: "t20230627-profile-description" },
            h(TextWithEntities, { full_text: p.description, entities: p.entities && p.entities.description, display_text_range: [0, p.description.length] })),
        h("div", { class: "t20230627-profile-attributes" }),
        h("div", { class: "t20230627-profile-numbers" }, [
            h("a", { href: `/profile/${p.user_id_str}/following` },
                h("span", null, p.friends_count),
                " ",
                h("span", null, "Following")),
            h("a", { href: `/profile/${p.user_id_str}/followers` },
                h("span", null, p.followers_count),
                " ",
                h("span", null, pluralize(p.followers_count, "Follower")))
        ]),
        h("div", { class: "t20230627-profile-context" })));
let Profile = (props) => Profile2(props.p);
let Header = (props) => h("div", { class: "t20230628-timeline-header" },
    h("div", { class: "t20230628-timeline-header-profile" },
        h("div", { class: "t20230628-timeline-header-return-button" },
            h("div", { class: "t20230628-timeline-header-button", onClick: logic.back.bind(logic) },
                h("svg", { viewBox: "0 0 24 24", "aria-hidden": "true", style: "color: rgb(239, 243, 244);" },
                    h("g", null,
                        h("path", { d: "M7.414 13l5.043 5.04-1.414 1.42L3.586 12l7.457-7.46 1.414 1.42L7.414 11H21v2H7.414z" })))))));
let monthNames = ["Jan", "Feb", "Mar", "Apr", "May", "Jul", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
let Histogram = (props) => h(Fragment, null,
    props.histogram.map((row) => h("div", { class: "t20160910-histogram" + (row[0] == props.year || props.year === undefined ? " t20160910-active" : "") },
        h("h3", null, row[0]),
        h("ol", { class: "t20160910-months t20160910-unstyled" }, row[1].map((count, month) => count
            ? h("li", null,
                h("a", { href: "#", class: "t20160910-with-tweets" + (row[0] == props.year && month + 1 == props.month && props.year !== undefined ? " t20160910-active" : ""), onClick: (ev) => props.selectMonth(row[0], month + 1), title: `${monthNames[month]} ${row[0]}: ${count} Tweets` },
                    h("span", { class: "t20160910-bar", style: `height: ${100 * count / props.max_tweets}%;` })))
            : h("li", { class: "t20160910-without-tweets", title: "" }))))),
    props.year !== undefined ? h("a", { href: "#" }, "Reset selection") : []);
let Sidebar = (props) => h("div", { class: "sidebar-container" },
    h("div", { class: "t20160910-sidebar-nav" }, props.children));
let NavBar = (props) => h("div", { class: "t20230630-navbar" }, props.items.map((tab, index) => h("div", { class: "t20230630-navbutton" + (index == props.selected ? " navbar-selected" : ""), onClick: (e) => logic.navigate(tab.navigate_to) },
    h("div", { class: "t20230630-navbutton-text" }, tab.label))));
class App extends Component {
    render() {
        let top = this.props.topProfile;
        let parts = [];
        if (this.props.tab >= 100) {
            let uid = this.props.topProfile.user_id_str;
            let tabs = [
                { label: "Followers", navigate_to: `profile/${uid}/followers` },
                { label: "Following", navigate_to: `profile/${uid}/following` }
            ];
            parts.push(h(Header, null));
            parts.push(h(NavBar, { items: tabs, selected: this.props.tab - 100 }));
        }
        else if (top) {
            let uid = this.props.topProfile.user_id_str;
            let tabs = [
                { label: "Tweets", navigate_to: `profile/${uid}` },
                { label: "Replies", navigate_to: `profile/${uid}/with_replies` },
                { label: "Media", navigate_to: `profile/${uid}/media` },
                { label: "Likes", navigate_to: `profile/${uid}/likes` }
            ];
            if (top.observer)
                tabs.push({ label: "Bookmarks", navigate_to: `profile/${uid}/bookmarks` });
            else
                tabs.push({ label: "Interactions", navigate_to: `profile/${uid}/interactions` });
            parts.push(h(Header, null));
            parts.push(h(Profile, { p: top }));
            parts.push(h(NavBar, { items: tabs, selected: this.props.tab }));
        }
        else {
            parts.push(h(Header, null));
        }
        parts.push(...(this.props.profiles || []).map(profile => h(ProfileItem, { key: profile.user_id_str, p: profile })));
        parts.push(...(this.props.tweets || []).map(tweet => tweet ? h(Tweet, { key: tweet.id_str, t: tweet, u: tweet.user }) : []));
        let timeline = h("div", { class: "common-frame-600 theme-dim" },
            h("div", { class: "t20230403-timeline", tabIndex: 0 }, parts));
        let sidebar = h(Sidebar, null,
            h(Histogram
            // year={2021}
            // month={10}
            , { 
                // year={2021}
                // month={10}
                max_tweets: this.props.histogram !== undefined ? this.props.histogram.max_tweets : 0, histogram: this.props.histogram !== undefined ? this.props.histogram.histogram : [], selectMonth: console.log }));
        return [timeline, sidebar];
    }
}
let div = null;
let logic = new Logic((props) => render(h(App, props), div));
window.addEventListener("popstate", (event) => logic.navigateReal(window.location.pathname.slice(1)));
window.addEventListener("load", () => {
    div = document.getElementById("root");
    render(h(App, { tweets: [], tab: 0 }), div);
    logic.navigateReal(window.location.pathname.slice(1));
});
