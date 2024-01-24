`cant-believe-its-not-twitter` is a Twitter archive (and [HAR](https://en.wikipedia.org/wiki/HAR_(file_format))) viewer.

Just give it your Twitter archives and/or HAR files and it’ll merge the data those files contain and display it mimicking the Twitter UI you were used to (RIP).

## Requirements

Only Python 3 is required. On most platform it should be already installed, however if for some reason your platform does not have it (e.g. on Windows), you can find a download link at https://python.org

## How to start cant-believe-its-not-twitter

1. Download or clone this repository
2. Open a console and move your current directory to be this project
3. Copy over all your HAR files as-is
4. Copy all your Twitter Archives and untar them into separate subdirectories (e.g. using `unzip -d <new dir> <archive.zip>`)
5. Then run:
```
python3 server.py
```

## What are HAR files

HAR is a format for logging of a web browser's interaction with a website.
The format is supported by multiple browsers such as Firefox, Chrome or Edge.

In practice, for Twitter, the resulting HAR file for a given browsing session will contain all requests made to twitter.com and their results, data such as all the tweets viewed, number of likes/retweets/replies, some user profile data (bio, people they follow, …), ...

Since it is meant for debugging, it does contain everything you’ve done for a given website (including session cookies), so HAR files should never be shared to others.

## Archive vs. HAR file

An archive only contains personal data (tweets, list of followers, people you follow) but a lot of information are missing or incomplete. For example:
* Your bookmarks are not included
* Who liked or retweeted your Tweets
* Replies to your Tweets or threads you were involved in, but didn’t like. Even if you liked them, their order and context are missing anyway
* ...

For this reason, HAR files can be useful to save more of your data and interactions you might otherwise have lost.

## Get a HAR file

To get a HAR file:
1. Open a compatible web browser (e.g. Firefox)
2. Open the debug console. E.g. on Firefox: Main menu --> "More tools" --> Web Developer Tools
3. Go to the Networ Monitor tab
4. Go to https://twitter.com or reload the page
5. Then browse Twitter as usual
6. At the end of your browsing session, click on the Cog icon (Network Settings) and click on "Save All As HAR"

## Get your Twitter archive

Go to "Settings" --> "Your account" --> "Download an archive of your data"
From there the steps should be guided and you should be able to download your archive a day or two later, typically.

A more up-to-date and detailed information might still be available at https://help.twitter.com/en/managing-your-account/how-to-download-your-twitter-archive

## Troubleshooting

If you encounter a possible unexpected behaviour, please open a ticket in our bugtracker: https://github.com/rrika/cant-believe-its-not-twitter/issues
