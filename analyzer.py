import json
import re
from typing import List, Tuple

import anthropic

from config import Config
from models import (
    RedditData,
    RedditPost,
    PainPoint,
    MarketSignal,
    ValidationResult,
    BusinessIdea,
    DiscoveryResult,
)

_MODEL = "claude-sonnet-4-6"


class BusinessAnalyzer:
    def __init__(self, config: Config):
        self.client = anthropic.Anthropic(api_key=config.anthropic_api_key)

    # ──────────────────────────────────────────────────────────────────────────
    # Keyword extraction
    # ──────────────────────────────────────────────────────────────────────────

    def extract_keywords(self, user_input: str) -> Tuple[List[str], List[str]]:
        """
        Returns (search_keywords, target_subreddits).
        Uses a small, fast Claude call.
        """
        prompt = f"""You are a market research expert helping find Reddit discussions.

Given this business input, extract the best Reddit search keywords and likely subreddits.

BUSINESS INPUT: "{user_input}"

Return ONLY valid JSON with this exact structure:
{{
  "keywords": ["keyword1", "keyword2", "keyword3", "keyword4", "keyword5"],
  "subreddits": ["subreddit1", "subreddit2", "subreddit3"]
}}

Rules:
- keywords: 4-7 terms that people on Reddit would actually use when discussing this topic (no jargon)
- subreddits: 3-6 specific subreddit names (without r/) where this topic is discussed
- Be specific, not generic — avoid catch-all terms like "business" or "app"
"""
        response = self.client.messages.create(
            model=_MODEL,
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text.strip()
        data = _parse_json(raw)
        keywords = data.get("keywords", [user_input])
        subreddits = data.get("subreddits", [])
        return keywords, subreddits

    # ──────────────────────────────────────────────────────────────────────────
    # Validate mode
    # ──────────────────────────────────────────────────────────────────────────

    def validate_idea(self, idea: str, reddit_data: RedditData) -> ValidationResult:
        formatted = _format_reddit_data(reddit_data)

        prompt = f"""You are a sharp business analyst validating a startup idea using real Reddit data.

IDEA TO VALIDATE: "{idea}"

REDDIT DATA (posts ranked by engagement score = upvotes × upvote_ratio × log(comments+1)):
{formatted}

TASK:
Analyze the Reddit conversations above to rigorously validate this business idea.
Look for:
- Real pain points this idea addresses (with evidence from the posts)
- Demand signals (how many people discuss this, engagement levels)
- Existing competitors mentioned or implied
- Sentiment around the problem space
- Red flags or risks hidden in the conversations
- Untapped angles the idea could exploit

Think carefully. Base every claim on the actual Reddit data. Do not hallucinate.

Return ONLY valid JSON with this EXACT structure (no markdown, no commentary):
{{
  "validation_score": <0-10 float>,
  "opportunity_score": <0-10 float>,
  "sentiment_score": <0-10 float>,
  "pain_points": [
    {{
      "description": "<concise pain point>",
      "evidence_count": <estimated number of posts/comments supporting this>,
      "example_quotes": ["<quote 1 from the data>", "<quote 2>"]
    }}
  ],
  "market_signals": [
    {{
      "signal": "<market signal description>",
      "evidence": "<specific evidence from the data>",
      "strength": "<weak|moderate|strong>"
    }}
  ],
  "competition": ["<competitor or alternative mentioned>"],
  "key_insights": ["<insight 1>", "<insight 2>", "<insight 3>", "<insight 4>"],
  "strategic_recommendations": ["<recommendation 1>", "<recommendation 2>", "<recommendation 3>"],
  "suggested_pivots": ["<pivot idea 1>", "<pivot idea 2>"],
  "monitor_subreddits": ["<sub1>", "<sub2>", "<sub3>"],
  "reasoning": "<3-5 paragraph detailed reasoning explaining the validation score and key findings>"
}}

Score guide:
- validation_score: How well does Reddit data confirm this specific idea is needed? (8-10 = strong evidence, 4-7 = mixed signals, 0-3 = little evidence)
- opportunity_score: How big/accessible is the market opportunity based on discussion volume and engagement?
- sentiment_score: How positive is the overall sentiment toward this problem space being solved?
"""
        response = self.client.messages.create(
            model=_MODEL,
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text.strip()
        data = _parse_json(raw)
        return _build_validation_result(idea, data)

    # ──────────────────────────────────────────────────────────────────────────
    # Discover mode
    # ──────────────────────────────────────────────────────────────────────────

    def discover_ideas(self, domain: str, reddit_data: RedditData) -> DiscoveryResult:
        formatted = _format_reddit_data(reddit_data)

        prompt = f"""You are a business opportunity analyst mining Reddit for startup ideas.

DOMAIN / CATEGORY: "{domain}"

REDDIT DATA (posts ranked by engagement score = upvotes × upvote_ratio × log(comments+1)):
{formatted}

TASK:
Read these Reddit conversations carefully. Identify the 5 most compelling business opportunities
hiding in what people are complaining about, requesting, wishing existed, or struggling with.

Each idea must be grounded in the actual Reddit data — cite specific evidence.

Return ONLY valid JSON with this EXACT structure (no markdown, no commentary):
{{
  "ideas": [
    {{
      "title": "<punchy business idea name>",
      "description": "<2-3 sentence description of the business>",
      "opportunity_score": <0-10 float>,
      "pain_points_addressed": ["<pain point 1>", "<pain point 2>"],
      "target_audience": "<who specifically would buy/use this>",
      "differentiation": "<what makes this different from existing solutions>",
      "risks": ["<risk 1>", "<risk 2>"]
    }}
  ],
  "overall_market_insights": "<3-4 sentences summarizing what the Reddit data reveals about this domain overall>",
  "monitor_subreddits": ["<sub1>", "<sub2>", "<sub3>", "<sub4>"],
  "reasoning": "<3-5 paragraph explanation of how you identified these opportunities from the data>"
}}

Rank ideas by opportunity_score descending. Be specific and creative.
"""
        response = self.client.messages.create(
            model=_MODEL,
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text.strip()
        data = _parse_json(raw)
        return _build_discovery_result(domain, data)


# ──────────────────────────────────────────────────────────────────────────────
# Formatting helpers
# ──────────────────────────────────────────────────────────────────────────────

def _format_reddit_data(reddit_data: RedditData) -> str:
    lines: List[str] = []
    lines.append(
        f"[Dataset: {reddit_data.total_posts_scanned} posts scanned, "
        f"{len(reddit_data.posts)} shown below by engagement rank]"
    )
    lines.append(f"[Keywords used: {', '.join(reddit_data.keywords_used)}]")
    lines.append(f"[Subreddits searched: {', '.join(reddit_data.subreddits_searched[:10])}]")
    lines.append("")

    for i, post in enumerate(reddit_data.posts, 1):
        lines.append(
            f"--- POST #{i} | r/{post.subreddit} | "
            f"↑{post.score} ({int(post.upvote_ratio*100)}% upvoted) | "
            f"{post.num_comments} comments | engagement={post.engagement_score:.0f}"
        )
        lines.append(f"TITLE: {post.title}")
        if post.text.strip():
            lines.append(f"BODY: {post.text[:350]}")
        if post.comments:
            lines.append("TOP COMMENTS:")
            for c in post.comments[:5]:
                lines.append(f"  [↑{c.score}] {c.body[:300]}")
        lines.append("")

    return "\n".join(lines)


# ──────────────────────────────────────────────────────────────────────────────
# JSON parsing
# ──────────────────────────────────────────────────────────────────────────────

def _parse_json(raw: str) -> dict:
    # Strip markdown code fences if present
    raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.MULTILINE)
    raw = re.sub(r"\s*```$", "", raw, flags=re.MULTILINE)
    raw = raw.strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # Try to extract first {...} block
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
    return {}


# ──────────────────────────────────────────────────────────────────────────────
# Model builders
# ──────────────────────────────────────────────────────────────────────────────

def _build_validation_result(idea: str, data: dict) -> ValidationResult:
    pain_points = [
        PainPoint(
            description=pp.get("description", ""),
            evidence_count=int(pp.get("evidence_count", 0)),
            example_quotes=pp.get("example_quotes", []),
        )
        for pp in data.get("pain_points", [])
    ]
    market_signals = [
        MarketSignal(
            signal=ms.get("signal", ""),
            evidence=ms.get("evidence", ""),
            strength=ms.get("strength", "moderate"),
        )
        for ms in data.get("market_signals", [])
    ]
    return ValidationResult(
        idea=idea,
        validation_score=float(data.get("validation_score", 0)),
        opportunity_score=float(data.get("opportunity_score", 0)),
        sentiment_score=float(data.get("sentiment_score", 0)),
        pain_points=pain_points,
        market_signals=market_signals,
        competition=data.get("competition", []),
        key_insights=data.get("key_insights", []),
        strategic_recommendations=data.get("strategic_recommendations", []),
        suggested_pivots=data.get("suggested_pivots", []),
        monitor_subreddits=data.get("monitor_subreddits", []),
        reasoning=data.get("reasoning", ""),
    )


def _build_discovery_result(domain: str, data: dict) -> DiscoveryResult:
    ideas = [
        BusinessIdea(
            title=idea.get("title", ""),
            description=idea.get("description", ""),
            opportunity_score=float(idea.get("opportunity_score", 0)),
            pain_points_addressed=idea.get("pain_points_addressed", []),
            target_audience=idea.get("target_audience", ""),
            differentiation=idea.get("differentiation", ""),
            risks=idea.get("risks", []),
        )
        for idea in data.get("ideas", [])
    ]
    return DiscoveryResult(
        domain=domain,
        ideas=ideas,
        overall_market_insights=data.get("overall_market_insights", ""),
        monitor_subreddits=data.get("monitor_subreddits", []),
        reasoning=data.get("reasoning", ""),
    )
