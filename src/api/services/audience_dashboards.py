from __future__ import annotations

import io

import matplotlib.pyplot as plt

from src.api.services.dto import CompetitorDiscoveryReport, TelegramAudienceReport


def dashboards_available() -> bool:
    return plt is not None


def build_audience_dashboard(report: TelegramAudienceReport) -> bytes:
    _ensure_backend()
    plt.style.use("seaborn-v0_8-whitegrid")
    plt.rcParams["font.family"] = "DejaVu Sans"

    fig = plt.figure(figsize=(16, 10), facecolor="#f5efe5")
    grid = fig.add_gridspec(2, 2, hspace=0.28, wspace=0.18)

    ax_themes = fig.add_subplot(grid[0, 0], facecolor="#fffaf3")
    ax_metrics = fig.add_subplot(grid[0, 1], facecolor="#fffaf3")
    ax_interests = fig.add_subplot(grid[1, 0], facecolor="#fffaf3")
    ax_summary = fig.add_subplot(grid[1, 1], facecolor="#fffaf3")

    top_themes = report.channel_themes[:6]
    theme_labels = [item.label for item in reversed(top_themes)]
    theme_values = [round(item.share * 100, 1) for item in reversed(top_themes)]
    ax_themes.barh(theme_labels, theme_values, color="#b85c38")
    ax_themes.set_title("Темы канала", fontsize=15, fontweight="bold", loc="left")
    ax_themes.set_xlabel("Доля, %")

    metric_labels = ["View Rate", "Deep ER", "Posts/Day"]
    metric_values = [
        round(report.engagement_metrics.view_rate * 100, 1),
        round(report.engagement_metrics.deep_engagement_rate * 100, 1),
        round(report.engagement_metrics.posts_per_day, 1),
    ]
    ax_metrics.bar(metric_labels, metric_values, color=["#2f6690", "#3a7ca5", "#81c3d7"])
    ax_metrics.set_title("Метрики постов", fontsize=15, fontweight="bold", loc="left")
    ax_metrics.set_ylabel("Значение")

    top_interests = report.interest_clusters[:6]
    interest_labels = [item.label for item in reversed(top_interests)]
    interest_values = [round(item.share * 100, 1) for item in reversed(top_interests)]
    ax_interests.barh(interest_labels, interest_values, color="#3a7d44")
    ax_interests.set_title("Интересы по контенту", fontsize=15, fontweight="bold", loc="left")
    ax_interests.set_xlabel("Доля, %")

    ax_summary.axis("off")
    summary_lines = [
        f"{report.source.title or report.source.source}",
        f"Источник: {report.source.source}",
        f"Подписчики: {report.source.participants_estimate or 'неизвестно'}",
        f"Сообщений в выборке: {report.source.message_sample_size}",
        "",
        f"Доминирующая тема: {report.dominant_theme.label}",
        f"Просмотры/post: {report.engagement_metrics.average_views}",
        f"ERR: {report.engagement_metrics.deep_engagement_rate:.2%}",
        f"Постов в день: {report.engagement_metrics.posts_per_day:.1f}",
        "",
        "Персона:",
        report.audience_persona.title,
        report.audience_persona.description,
        "",
        "Что цепляет:",
        f"- {report.content_insights.strongest_content_hook}",
        "",
        "Сводка:",
        report.summary,
    ]
    ax_summary.text(
        0.03,
        0.97,
        "\n".join(summary_lines),
        va="top",
        ha="left",
        fontsize=11,
        color="#222222",
        wrap=True,
    )

    fig.suptitle("Dashboard: Анализ аудитории Telegram", fontsize=20, fontweight="bold", x=0.05, ha="left")
    return _figure_to_png(fig)


def build_competitors_dashboard(report: CompetitorDiscoveryReport) -> bytes:
    _ensure_backend()
    plt.style.use("seaborn-v0_8-whitegrid")
    plt.rcParams["font.family"] = "DejaVu Sans"

    fig = plt.figure(figsize=(16, 10), facecolor="#f3f4f6")
    grid = fig.add_gridspec(2, 2, hspace=0.28, wspace=0.18)

    ax_scores = fig.add_subplot(grid[0, 0], facecolor="#fbfdff")
    ax_types = fig.add_subplot(grid[0, 1], facecolor="#fbfdff")
    ax_reasons = fig.add_subplot(grid[1, 0], facecolor="#fbfdff")
    ax_meta = fig.add_subplot(grid[1, 1], facecolor="#fbfdff")

    competitors = report.competitors[:6]
    labels = [item.source.title or item.source.username or item.source.source for item in competitors]
    score_values = [round(item.similarity_score * 100, 1) for item in competitors]
    colors = [
        "#c44536" if item.relation_type == "прямой конкурент"
        else "#dd8a2f" if item.relation_type == "смежный конкурент"
        else "#6c7a89"
        for item in competitors
    ]
    ax_scores.barh(list(reversed(labels)), list(reversed(score_values)), color=list(reversed(colors)))
    ax_scores.set_title("Итоговая похожесть", fontsize=15, fontweight="bold", loc="left")
    ax_scores.set_xlabel("Score, %")

    ax_types.axis("off")
    type_lines: list[str] = ["Тип конкурента", ""]
    for item in competitors[:5]:
        title = item.source.title or item.source.username or item.source.source
        type_lines.append(f"{title}: {item.relation_type}")
    ax_types.text(0.03, 0.97, "\n".join(type_lines), va="top", ha="left", fontsize=11, color="#222222", wrap=True)

    ax_reasons.axis("off")
    reason_lines: list[str] = ["Почему кандидаты попали в список", ""]
    for item in competitors[:4]:
        title = item.source.title or item.source.username or item.source.source
        reason_lines.append(f"{title} [{item.relation_type}]")
        reason_lines.append(f"Темы: {', '.join(item.matched_themes[:3]) or 'нет явных'}")
        if item.matched_keywords:
            reason_lines.append(f"Сигналы контента: {', '.join(item.matched_keywords[:3])}")
        if item.disqualifiers:
            reason_lines.append(f"Ограничения: {', '.join(item.disqualifiers[:2])}")
        reason_lines.append("")
    ax_reasons.text(0.03, 0.97, "\n".join(reason_lines), va="top", ha="left", fontsize=11, color="#222222", wrap=True)

    ax_meta.axis("off")
    failed = ", ".join(item.source for item in report.failed_candidates[:4]) or "нет"
    meta_lines = [
        f"Базовый канал: {report.source.title or report.source.source}",
        f"Источник: {report.source.source}",
        f"Найдено конкурентов: {len(report.competitors)}",
        f"Ошибки по кандидатам: {len(report.failed_candidates)}",
        "",
        f"Не обработались: {failed}",
        "",
        "Легенда:",
        "- красный: прямой конкурент",
        "- оранжевый: смежный конкурент",
        "- серый: широкий рыночный сосед",
    ]
    ax_meta.text(0.03, 0.97, "\n".join(meta_lines), va="top", ha="left", fontsize=11, color="#222222", wrap=True)

    fig.suptitle("Dashboard: Конкуренты Telegram-канала", fontsize=20, fontweight="bold", x=0.05, ha="left")
    return _figure_to_png(fig)


def _ensure_backend() -> None:
    if plt is None:
        raise RuntimeError("matplotlib is not installed")


def _figure_to_png(fig) -> bytes:
    buffer = io.BytesIO()
    fig.savefig(buffer, format="png", dpi=160, bbox_inches="tight")
    plt.close(fig)
    buffer.seek(0)
    return buffer.getvalue()
