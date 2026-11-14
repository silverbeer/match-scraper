"""Telegram MarkdownV2 report builders for audit commands."""

from __future__ import annotations

from telegram_notify import escape

from src.orchestrator.audit.models import ProcessResult


def build_processor_report(result: ProcessResult, env: str) -> str:
    """Build a MarkdownV2 processor report for Telegram.

    Only called when a match is in MT but no longer in the feed — the one
    finding that needs a person. Corrections made alongside are listed for context.
    """
    lines: list[str] = []
    lines.append("*Audit Processor Report*")
    lines.append(f"_{escape(env)}_")
    lines.append("")

    if result.matches_resubmitted:
        type_breakdown = " · ".join(
            f"{escape(ftype.replace('_', ' ').title())} \\({escape(str(count))}\\)"
            for ftype, count in sorted(result.corrections_by_type.items())
        )
        corrected_line = f"*Corrected:* {escape(str(result.matches_resubmitted))}"
        if type_breakdown:
            corrected_line += f" — {type_breakdown}"
        lines.append(corrected_line)

    if result.extra_in_mt_skipped:
        lines.append("")
        lines.append("⚠️ *MANUAL REVIEW REQUIRED* ⚠️")
        lines.append(
            f"*{escape(str(result.extra_in_mt_skipped))} match"
            f"{'es' if result.extra_in_mt_skipped != 1 else ''}"
            f" found in MT but NOT on mlssoccer\\.com*"
        )
        lines.append("_Do NOT cancel without verifying — may be a scraper bug\\._")
        lines.append("")
        for m in result.extra_in_mt_findings:
            home = escape(m.home_team)
            away = escape(m.away_team)
            md = escape(m.match_date)
            label = escape(f"{m.team} {m.age_group}")
            lines.append(f"  • {md} {home} vs {away} _{label}_")

    if result.errors:
        lines.append("")
        lines.append(f"*Errors:* {escape(str(result.errors))}")

    return "\n".join(lines)
