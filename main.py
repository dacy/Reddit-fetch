#!/usr/bin/env python3
"""
Reddit Business Intelligence — validate or discover business ideas using Reddit data + Claude AI.
Usage: python main.py
"""

import sys
import time
from typing import Optional

from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn
from rich.prompt import Prompt, IntPrompt
from rich.rule import Rule
from rich.table import Table
from rich.text import Text
from rich import box

from config import Config
from reddit_fetcher import RedditFetcher
from analyzer import BusinessAnalyzer
from models import ValidationResult, DiscoveryResult, BusinessIdea

console = Console()


# ──────────────────────────────────────────────────────────────────────────────
# Display helpers
# ──────────────────────────────────────────────────────────────────────────────

def _score_bar(score: float, width: int = 20) -> str:
    filled = round(score / 10 * width)
    bar = "█" * filled + "░" * (width - filled)
    color = "red" if score < 4 else "yellow" if score < 7 else "green"
    return f"[{color}]{bar}[/{color}] [bold]{score:.1f}[/bold]/10"


def _strength_color(strength: str) -> str:
    return {"weak": "red", "moderate": "yellow", "strong": "green"}.get(strength, "white")


def _bullet(items: list, color: str = "cyan") -> str:
    if not items:
        return "  [dim]None identified[/dim]"
    return "\n".join(f"  [{color}]●[/{color}] {item}" for item in items)


def _print_validation(result: ValidationResult) -> None:
    console.print()
    console.print(
        Panel(
            f"[bold white]BUSINESS VALIDATION REPORT[/bold white]\n[dim]{result.idea}[/dim]",
            style="bold blue",
            padding=(1, 4),
        )
    )

    # Score summary table
    score_table = Table(box=box.SIMPLE, show_header=False, padding=(0, 2))
    score_table.add_column("Metric", style="bold")
    score_table.add_column("Score")
    score_table.add_row("Validation Score", _score_bar(result.validation_score))
    score_table.add_row("Opportunity Score", _score_bar(result.opportunity_score))
    score_table.add_row("Sentiment Score", _score_bar(result.sentiment_score))
    console.print(score_table)

    # Pain points
    console.print(Rule("[bold]Pain Points Discovered[/bold]", style="dim"))
    if result.pain_points:
        for pp in result.pain_points:
            console.print(
                f"  [red]●[/red] [bold]{pp.description}[/bold]"
                + (f" [dim]({pp.evidence_count} mentions)[/dim]" if pp.evidence_count else "")
            )
            for q in pp.example_quotes[:2]:
                console.print(f'      [dim italic]"{q[:120]}..."[/dim italic]')
    else:
        console.print("  [dim]No clear pain points extracted[/dim]")

    # Market signals
    console.print()
    console.print(Rule("[bold]Market Signals[/bold]", style="dim"))
    if result.market_signals:
        for ms in result.market_signals:
            color = _strength_color(ms.strength)
            console.print(f"  [{color}]◆ {ms.strength.upper()}[/{color}]  {ms.signal}")
            console.print(f"    [dim]{ms.evidence[:150]}[/dim]")
    else:
        console.print("  [dim]No market signals extracted[/dim]")

    # Competition
    console.print()
    console.print(Rule("[bold]Competition Landscape[/bold]", style="dim"))
    console.print(_bullet(result.competition, "yellow"))

    # Key insights
    console.print()
    console.print(Rule("[bold]Key Insights[/bold]", style="dim"))
    for i, insight in enumerate(result.key_insights, 1):
        console.print(f"  [cyan]{i}.[/cyan] {insight}")

    # Strategic recommendations
    console.print()
    console.print(Rule("[bold]Strategic Recommendations[/bold]", style="dim"))
    console.print(_bullet(result.strategic_recommendations, "green"))

    # Suggested pivots
    if result.suggested_pivots:
        console.print()
        console.print(Rule("[bold]Suggested Pivots[/bold]", style="dim"))
        console.print(_bullet(result.suggested_pivots, "magenta"))

    # Monitor
    if result.monitor_subreddits:
        console.print()
        console.print(Rule("[bold]Subreddits to Monitor[/bold]", style="dim"))
        subs = "  " + "  ".join(f"[link=https://reddit.com/r/{s}]r/{s}[/link]" for s in result.monitor_subreddits)
        console.print(subs)

    # Reasoning
    console.print()
    console.print(
        Panel(
            result.reasoning,
            title="[bold]AI Reasoning[/bold]",
            border_style="dim",
            padding=(1, 2),
        )
    )


def _print_discovery(result: DiscoveryResult) -> None:
    console.print()
    console.print(
        Panel(
            f"[bold white]BUSINESS IDEA DISCOVERY[/bold white]\n[dim]Domain: {result.domain}[/dim]",
            style="bold magenta",
            padding=(1, 4),
        )
    )

    console.print()
    console.print(
        Panel(result.overall_market_insights, title="[bold]Market Overview[/bold]", border_style="dim", padding=(0, 2))
    )

    for i, idea in enumerate(result.ideas, 1):
        console.print()
        console.print(
            Panel(
                _format_idea(idea),
                title=f"[bold cyan]#{i} — {idea.title}[/bold cyan]  {_score_bar(idea.opportunity_score)}",
                border_style="cyan",
                padding=(0, 2),
            )
        )

    if result.monitor_subreddits:
        console.print()
        console.print(Rule("[bold]Subreddits to Monitor[/bold]", style="dim"))
        subs = "  " + "  ".join(f"r/{s}" for s in result.monitor_subreddits)
        console.print(subs)

    console.print()
    console.print(
        Panel(
            result.reasoning,
            title="[bold]AI Reasoning[/bold]",
            border_style="dim",
            padding=(1, 2),
        )
    )


def _format_idea(idea: BusinessIdea) -> str:
    lines = [f"[white]{idea.description}[/white]", ""]
    lines.append(f"[bold]Target:[/bold] {idea.target_audience}")
    lines.append(f"[bold]Why different:[/bold] {idea.differentiation}")
    if idea.pain_points_addressed:
        lines.append("[bold]Pain points addressed:[/bold]")
        for pp in idea.pain_points_addressed:
            lines.append(f"  [green]✓[/green] {pp}")
    if idea.risks:
        lines.append("[bold]Risks:[/bold]")
        for r in idea.risks:
            lines.append(f"  [red]⚠[/red]  {r}")
    return "\n".join(lines)


# ──────────────────────────────────────────────────────────────────────────────
# Main flow
# ──────────────────────────────────────────────────────────────────────────────

def run_analysis(fetcher: RedditFetcher, analyzer: BusinessAnalyzer) -> None:
    console.print()
    console.print(Rule("[bold]Mode Selection[/bold]", style="blue"))
    console.print("  [cyan]1.[/cyan] Validate a specific business idea")
    console.print("  [cyan]2.[/cyan] Discover business ideas in a domain")
    console.print()

    mode_input = Prompt.ask("Choose mode", choices=["1", "2"], default="1")
    mode = "validate" if mode_input == "1" else "discover"

    console.print()
    if mode == "validate":
        user_input = Prompt.ask(
            "[bold]Describe your business idea[/bold]\n[dim]  Be specific — the more detail, the better the analysis[/dim]\n  ❯"
        ).strip()
    else:
        user_input = Prompt.ask(
            "[bold]What domain or industry are you interested in?[/bold]\n[dim]  e.g. 'remote work tools', 'pet care', 'mental health apps'[/dim]\n  ❯"
        ).strip()

    if not user_input:
        console.print("[red]Input cannot be empty.[/red]")
        return

    # Step 1: Extract keywords
    console.print()
    with console.status("[bold blue]Extracting search keywords...[/bold blue]"):
        keywords, target_subreddits = analyzer.extract_keywords(user_input)

    console.print(f"[dim]Keywords:[/dim] {', '.join(keywords)}")
    console.print(f"[dim]Target subreddits:[/dim] {', '.join(f'r/{s}' for s in target_subreddits)}")

    # Step 2: Collect Reddit data
    console.print()
    progress_messages = []

    def on_progress(msg: str):
        progress_messages.append(msg)
        console.print(f"  [dim]{msg}[/dim]")

    console.print(Rule("[bold]Collecting Reddit Data[/bold]", style="blue"))
    t0 = time.time()

    reddit_data = fetcher.collect(
        keywords=keywords,
        target_subreddits=target_subreddits,
        on_progress=on_progress,
    )

    elapsed = time.time() - t0
    console.print(
        f"\n[green]✓[/green] Data collection complete — "
        f"[bold]{reddit_data.total_posts_scanned}[/bold] posts scanned, "
        f"[bold]{len(reddit_data.posts)}[/bold] high-engagement posts selected "
        f"[dim]({elapsed:.1f}s)[/dim]"
    )

    if not reddit_data.posts:
        console.print("[yellow]⚠ No relevant posts found. Try broader keywords.[/yellow]")
        return

    # Step 3: Analyse
    console.print()
    console.print(Rule("[bold]Running AI Analysis[/bold]", style="blue"))

    with console.status(
        "[bold blue]Analysing Reddit data with Claude... this may take 30–60 seconds[/bold blue]",
        spinner="dots",
    ):
        if mode == "validate":
            result = analyzer.validate_idea(user_input, reddit_data)
        else:
            result = analyzer.discover_ideas(user_input, reddit_data)

    # Step 4: Display results
    if mode == "validate":
        _print_validation(result)
    else:
        _print_discovery(result)


def main() -> None:
    console.print()
    console.print(
        Panel(
            "[bold white]Reddit Business Intelligence[/bold white]\n"
            "[dim]Validate or discover business ideas using real Reddit conversations + Claude AI[/dim]",
            style="bold blue",
            padding=(1, 4),
        )
    )

    # Load config
    try:
        config = Config.from_env()
    except ValueError as e:
        console.print(f"\n[red bold]Configuration error:[/red bold] {e}")
        sys.exit(1)

    # Init clients
    with console.status("[dim]Connecting to Reddit and Anthropic...[/dim]"):
        try:
            fetcher = RedditFetcher(config)
            # Test Reddit auth
            _ = fetcher.reddit.user.me()
        except Exception as e:
            console.print(f"\n[red bold]Reddit connection failed:[/red bold] {e}")
            console.print("[dim]Check your REDDIT_* credentials in .env[/dim]")
            sys.exit(1)

        try:
            analyzer = BusinessAnalyzer(config)
        except Exception as e:
            console.print(f"\n[red bold]Anthropic connection failed:[/red bold] {e}")
            sys.exit(1)

    console.print(f"[green]✓[/green] Logged in as [bold]u/{config.reddit_username}[/bold]")

    # Main loop
    while True:
        try:
            run_analysis(fetcher, analyzer)
        except KeyboardInterrupt:
            console.print("\n[dim]Interrupted[/dim]")
            break
        except Exception as e:
            console.print(f"\n[red]Error during analysis:[/red] {e}")

        console.print()
        again = Prompt.ask("\nRun another analysis?", choices=["y", "n"], default="y")
        if again == "n":
            break

    console.print("\n[dim]Goodbye.[/dim]\n")


if __name__ == "__main__":
    main()
