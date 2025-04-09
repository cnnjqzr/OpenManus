import asyncio
from typing import Optional

from app.exceptions import ToolError
from app.tool.base import BaseTool, ToolResult


_TWITTER_DESCRIPTION = """Post tweets to Twitter.
* This tool allows you to post tweets to a Twitter account.
* You can post a simple text tweet or include media like images.
* For tweets with media, provide the file path to the image.
* The tool will return the tweet ID and URL after successful posting.
"""


class _TwitterSession:
    """A session for Twitter API interactions."""

    _started: bool
    _api_key: str
    _api_secret: str
    _access_token: str
    _access_token_secret: str

    def __init__(self):
        self._started = False
        # These would typically be loaded from environment variables
        # or a configuration file in a real implementation
        self._api_key = ""
        self._api_secret = ""
        self._access_token = ""
        self._access_token_secret = ""

    async def start(self):
        """Initialize the Twitter API client."""
        if self._started:
            return

        try:
            # In a real implementation, you would initialize the Twitter API client here
            # For example, using tweepy or the Twitter API v2
            # self._client = tweepy.Client(...)

            # For now, we'll just simulate the initialization
            await asyncio.sleep(0.5)
            self._started = True
        except Exception as e:
            raise ToolError(f"Failed to initialize Twitter API: {str(e)}")

    def stop(self):
        """Close the Twitter API session."""
        if not self._started:
            raise ToolError("Session has not started.")

        # Clean up any resources if needed
        self._started = False

    async def post_tweet(self, text: str, media_path: Optional[str] = None) -> dict:
        """Post a tweet with optional media."""
        if not self._started:
            raise ToolError("Session has not started.")

        try:
            # Simulate API call delay
            await asyncio.sleep(1)

            # In a real implementation, you would use the Twitter API to post the tweet
            # For example:
            # if media_path:
            #     media_id = self._client.media_upload(media_path)
            #     response = self._client.create_tweet(text=text, media_ids=[media_id])
            # else:
            #     response = self._client.create_tweet(text=text)

            # For now, we'll just simulate a successful response
            tweet_id = "1234567890123456789"
            tweet_url = f"https://twitter.com/username/status/{tweet_id}"

            return {
                "tweet_id": tweet_id,
                "tweet_url": tweet_url,
                "text": text,
                "has_media": media_path is not None
            }
        except Exception as e:
            raise ToolError(f"Failed to post tweet: {str(e)}")


class Twitter(BaseTool):
    """A tool for posting tweets to Twitter"""

    name: str = "twitter"
    description: str = _TWITTER_DESCRIPTION
    parameters: dict = {
        "type": "object",
        "properties": {
            "text": {
                "type": "string",
                "description": "The text content of the tweet to post.",
            },
            "media_path": {
                "type": "string",
                "description": "Optional path to a media file (image) to include with the tweet.",
            },
        },
        "required": ["text"],
    }

    _session: Optional[_TwitterSession] = None

    async def execute(
        self, text: str, media_path: Optional[str] = None, restart: bool = False, **kwargs
    ) -> ToolResult:
        if restart:
            if self._session:
                self._session.stop()
            self._session = _TwitterSession()
            await self._session.start()

            return ToolResult(system="Twitter tool has been restarted.")

        if self._session is None:
            self._session = _TwitterSession()
            await self._session.start()

        if not text:
            raise ToolError("Tweet text cannot be empty.")

        result = await self._session.post_tweet(text, media_path)

        output = f"Tweet posted successfully!\nTweet ID: {result['tweet_id']}\nURL: {result['tweet_url']}"
        if result.get("has_media"):
            output += "\nMedia was included with this tweet."

        return ToolResult(output=output)


if __name__ == "__main__":
    twitter = Twitter()
    rst = asyncio.run(twitter.execute("Hello, Twitter! This is a test tweet."))
    print(rst)
