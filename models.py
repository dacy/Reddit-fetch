from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class RedditComment:
    body: str
    score: int


@dataclass
class RedditPost:
    id: str
    title: str
    text: str
    score: int
    upvote_ratio: float
    num_comments: int
    subreddit: str
    url: str
    comments: List[RedditComment]
    engagement_score: float


@dataclass
class RedditData:
    posts: List[RedditPost]
    subreddits_searched: List[str]
    total_posts_scanned: int
    keywords_used: List[str]


@dataclass
class PainPoint:
    description: str
    evidence_count: int
    example_quotes: List[str]


@dataclass
class MarketSignal:
    signal: str
    evidence: str
    strength: str  # "weak" | "moderate" | "strong"


@dataclass
class ValidationResult:
    idea: str
    validation_score: float
    opportunity_score: float
    sentiment_score: float
    pain_points: List[PainPoint]
    market_signals: List[MarketSignal]
    competition: List[str]
    key_insights: List[str]
    strategic_recommendations: List[str]
    suggested_pivots: List[str]
    monitor_subreddits: List[str]
    reasoning: str


@dataclass
class BusinessIdea:
    title: str
    description: str
    opportunity_score: float
    pain_points_addressed: List[str]
    target_audience: str
    differentiation: str
    risks: List[str]


@dataclass
class DiscoveryResult:
    domain: str
    ideas: List[BusinessIdea]
    overall_market_insights: str
    monitor_subreddits: List[str]
    reasoning: str
