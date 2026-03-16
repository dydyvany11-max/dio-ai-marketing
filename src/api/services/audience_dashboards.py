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
    ax_age = fig.add_subplot(grid[0, 1], facecolor="#fffaf3")
    ax_interests = fig.add_subplot(grid[1, 0], facecolor="#fffaf3")
    ax_summary = fig.add_subplot(grid[1, 1], facecolor="#fffaf3")

    top_themes = report.channel_themes[:6]
    theme_labels = [item.label for item in reversed(top_themes)]
    theme_values = [round(item.share * 100, 1) for item in reversed(top_themes)]
    ax_themes.barh(theme_labels, theme_values, color="#b85c38")
    ax_themes.set_title("Темы канала", fontsize=15, fontweight="bold", loc="left")
    ax_themes.set_xlabel("Доля, %")

    age_labels = [item.label for item in report.age_hypothesis_clusters]
    age_values = [round(item.share * 100, 1) for item in report.age_hypothesis_clusters]
    age_colors = ["#2f6690", "#3a7ca5", "#81c3d7", "#d9dcd6", "#16425b"][: len(age_values)]
    ax_age.bar(age_labels, age_values, color=age_colors)
    ax_age.set_title("Возрастная гипотеза", fontsize=15, fontweight="bold", loc="left")
    ax_age.set_ylabel("Доля, %")

    top_interests = report.interest_clusters[:6]
    interest_labels = [item.label for item in reversed(top_interests)]
    interest_values = [round(item.share * 100, 1) for item in reversed(top_interests)]
    ax_interests.barh(interest_labels, interest_values, color="#3a7d44")
    ax_interests.set_title("Интересы аудитории", fontsize=15, fontweight="bold", loc="left")
    ax_interests.set_xlabel("Доля, %")

    ax_summary.axis("off")
    summary_lines = [
        f"{report.source.title or report.source.source}",
        f"Источник: {report.source.source}",
        f"Подписчики: {report.source.participants_estimate or 'неизвестно'}",
        f"Сообщений в выборке: {report.source.message_sample_size}",
        "",
        f"Доминирующая тема: {report.dominant_theme.label}",
        f"Топ-сегмент: {report.top_active_segment.label}",
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
    ax_components = fig.add_subplot(grid[0, 1], facecolor="#fbfdff")
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

    component_names = ["Темы", "Аудитория", "Вовлеч.", "Формат"]
    for index, item in enumerate(competitors[:4]):
        ax_components.plot(
            component_names,
            [
                item.theme_similarity * 100,
                item.audience_similarity * 100,
                item.engagement_similarity * 100,
                item.format_similarity * 100,
            ],
            marker="o",
            linewidth=2.2,
            label=(item.source.title or item.source.username or f"Кандидат {index + 1}")[:28],
        )
    ax_components.set_ylim(0, 100)
    ax_components.set_title("Из чего состоит совпадение", fontsize=15, fontweight="bold", loc="left")
    ax_components.legend(loc="lower left", fontsize=9)

    ax_reasons.axis("off")
    reason_lines: list[str] = ["Почему кандидаты попали в список", ""]
    for item in competitors[:4]:
        title = item.source.title or item.source.username or item.source.source
        reason_lines.append(f"{title} [{item.relation_type}]")
        reason_lines.append(f"Темы: {', '.join(item.matched_themes[:3]) or 'нет явных'}")
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
