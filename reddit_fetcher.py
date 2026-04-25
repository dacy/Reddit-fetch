import math
import time
from typing import List, Callable, Optional

import praw
from praw.exceptions import PRAWException

from config import Config
from models import RedditComment, RedditPost, RedditData


# Subreddits that are broadly useful for business/consumer research
ALWAYS_SEARCH = [
    "entrepreneur",
    "startups",
    "smallbusiness",
    "business",
    "AskReddit",
]


def _engagement_score(score: int, upvote_ratio: float, num_comments: int) -> float:
    """Higher score = more people engaged AND more discussion."""
    return max(score, 1) * upvote_ratio * math.log1p(num_comments)


class RedditFetcher:
    def __init__(self, config: Config):
        self.reddit = praw.Reddit(
            client_id=config.reddit_client_id,
            client_secret=config.reddit_client_secret,
            username=config.reddit_username,
            password=config.reddit_password,
            user_agent=config.user_agent,
        )

    # ──────────────────────────────────────────────────────────────────────────
    # Subreddit discovery
    # ──────────────────────────────────────────────────────────────────────────

    def find_relevant_subreddits(
        self,
        keywords: List[str],
        max_results: int = 12,
        min_subscribers: int = 5_000,
    ) -> List[str]:
        found: set[str] = set(ALWAYS_SEARCH)
        for kw in keywords[:4]:
            try:
                for sub in self.reddit.subreddits.search(kw, limit=6):
                    if (
                        sub.subscribers >= min_subscribers
                        and not sub.over18
                        and sub.display_name not in found
                    ):
                        found.add(sub.display_name)
                time.sleep(0.5)
            except PRAWException:
                pass
        return list(found)[:max_results]

    # ──────────────────────────────────────────────────────────────────────────
    # Post fetching helpers
    # ──────────────────────────────────────────────────────────────────────────

    def _fetch_comments(self, post, max_comments: int = 6) -> List[RedditComment]:
        try:
            post.comments.replace_more(limit=0)
            top = sorted(
                [c for c in post.comments.list() if hasattr(c, "body") and len(c.body) > 30],
                key=lambda c: getattr(c, "score", 0),
                reverse=True,
            )[:max_comments]
            return [RedditComment(body=c.body[:400], score=c.score) for c in top]
        except Exception:
            return []

    def _praw_post_to_model(self, post) -> RedditPost:
        eng = _engagement_score(post.score, post.upvote_ratio, post.num_comments)
        comments = self._fetch_comments(post)
        return RedditPost(
            id=post.id,
            title=post.title,
            text=(post.selftext or "")[:500],
            score=post.score,
            upvote_ratio=post.upvote_ratio,
            num_comments=post.num_comments,
            subreddit=str(post.subreddit),
            url=f"https://reddit.com{post.permalink}",
            comments=comments,
            engagement_score=eng,
        )

    def _is_relevant(self, post, keywords: List[str]) -> bool:
        haystack = (post.title + " " + (post.selftext or "")).lower()
        return any(kw.lower() in haystack for kw in keywords)

    # ──────────────────────────────────────────────────────────────────────────
    # Search strategies
    # ──────────────────────────────────────────────────────────────────────────

    def search_global(
        self,
        keywords: List[str],
        limit: int = 60,
    ) -> List[RedditPost]:
        """Search r/all with multiple query variations to maximise coverage."""
        seen: set[str] = set()
        posts: List[RedditPost] = []

        queries = self._build_queries(keywords)
        for query in queries:
            try:
                results = self.reddit.subreddit("all").search(
                    query, sort="relevance", time_filter="year", limit=limit // len(queries)
                )
                for p in results:
                    if p.id not in seen:
                        seen.add(p.id)
                        posts.append(self._praw_post_to_model(p))
                time.sleep(0.6)
            except PRAWException:
                pass

        return posts

    def fetch_from_subreddit(
        self,
        subreddit_name: str,
        keywords: List[str],
        limit: int = 30,
    ) -> List[RedditPost]:
        seen: set[str] = set()
        posts: List[RedditPost] = []
        try:
            sub = self.reddit.subreddit(subreddit_name)
            sources = [
                sub.hot(limit=limit),
                sub.top(time_filter="month", limit=limit),
            ]
            for source in sources:
                for p in source:
                    if p.id not in seen and self._is_relevant(p, keywords):
                        seen.add(p.id)
                        posts.append(self._praw_post_to_model(p))
                time.sleep(0.4)
        except PRAWException:
            pass
        return posts

    # ──────────────────────────────────────────────────────────────────────────
    # Main entry point
    # ──────────────────────────────────────────────────────────────────────────

    def collect(
        self,
        keywords: List[str],
        target_subreddits: List[str],
        on_progress: Optional[Callable[[str], None]] = None,
    ) -> RedditData:
        def log(msg: str):
            if on_progress:
                on_progress(msg)

        all_posts: dict[str, RedditPost] = {}

        # 1. Global search
        log("Searching across all of Reddit...")
        for p in self.search_global(keywords, limit=80):
            all_posts[p.id] = p

        log(f"  {len(all_posts)} posts from global search")

        # 2. Targeted subreddit fetch
        discovered = self.find_relevant_subreddits(keywords)
        subs_to_search = list(dict.fromkeys(target_subreddits + discovered))  # preserve order, dedupe

        for sub in subs_to_search:
            log(f"  Fetching r/{sub}...")
            before = len(all_posts)
            for p in self.fetch_from_subreddit(sub, keywords, limit=25):
                all_posts[p.id] = p
            new = len(all_posts) - before
            if new:
                log(f"    +{new} new posts from r/{sub}")

        # 3. Pain-point targeted search
        log("Running pain-point searches...")
        pain_queries = [f"{kw} problem" for kw in keywords[:3]] + [
            f"{kw} alternative" for kw in keywords[:2]
        ]
        for query in pain_queries:
            try:
                for p in self.reddit.subreddit("all").search(
                    query, sort="top", time_filter="year", limit=20
                ):
                    if p.id not in all_posts:
                        all_posts[p.id] = self._praw_post_to_model(p)
                time.sleep(0.5)
            except PRAWException:
                pass

        total_scanned = len(all_posts)

        # 4. Rank and keep top N by engagement
        ranked = sorted(all_posts.values(), key=lambda p: p.engagement_score, reverse=True)
        top_posts = ranked[:50]

        log(f"Total posts scanned: {total_scanned} → keeping top {len(top_posts)} by engagement")

        return RedditData(
            posts=top_posts,
            subreddits_searched=subs_to_search,
            total_posts_scanned=total_scanned,
            keywords_used=keywords,
        )

    # ──────────────────────────────────────────────────────────────────────────
    # Helpers
    # ──────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _build_queries(keywords: List[str]) -> List[str]:
        """Generate a few query strings to improve recall."""
        if not keywords:
            return [""]
        queries = [" ".join(keywords[:3])]
        if len(keywords) >= 2:
            queries.append(f"{keywords[0]} {keywords[1]}")
        if len(keywords) >= 1:
            queries.append(keywords[0])
        return queries
