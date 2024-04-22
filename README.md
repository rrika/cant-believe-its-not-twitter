# About

The code here allows viewing Tweets/DMs/etc. locally based on export zips or intercepted web traffic. Latter is valuable because Twitter export zips don't among other things contain:

- any tweets you're replying to
- profile names/pictures of anyone else
- tweet ids of what you're retweeting
- bookmarks

The official exports also contain the likes in shuffled order (beyond the first ~100 items).


# For users

Run `python server.py <datasources>` and navigate to http://localhost:8080/. Data sources can be any of:

- path to a zipped twitter export archive
- path to an unzipped twitter export archive
- path to a .har file
- path to a .warc file (or .warc.open file, though it won't be read continuously)
- path to a directory containing any of the above
- path to a .txt file with one data source per line (lines with # are treated as comments)

When saving .har files using firefox remember to set devtools.netmonitor.responseBodyLimit to a high value, else images might not get saved.


# For developers

Run `npm install --dev` to get the typescript headers for preact. Run `tsc -w` in the main directory to compile the typescript.


# Contributing

I don't have the capacity to review PRs, so you're encouraged to fork.
