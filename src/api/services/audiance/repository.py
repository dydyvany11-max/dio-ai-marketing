from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import Text, create_engine, inspect, select, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from src.api.config import PROJECT_ROOT
from src.api.services.audiance.snapshot import build_audience_analysis_snapshot, restore_audience_report
from src.api.services.dto import AudienceAnalysisSnapshot
from src.api.services.interfaces import AudienceAnalysisRepositoryPort


class Base(DeclarativeBase):
    pass


class ChannelAnalysisORM(Base):
    __tablename__ = "channels"

    source: Mapped[str] = mapped_column(Text, primary_key=True)
    title: Mapped[str] = mapped_column(Text, nullable=False, default="")
    username: Mapped[str] = mapped_column(Text, nullable=False, default="", index=True)
    audience_persona: Mapped[str] = mapped_column(Text, nullable=False, default="")
    dominant_theme: Mapped[str] = mapped_column(Text, nullable=False, default="")
    secondary_themes_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    report_payload_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    analyzed_at: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[str] = mapped_column(Text, nullable=False)


class SqlAlchemyAudienceAnalysisRepository(AudienceAnalysisRepositoryPort):
    def __init__(self, db_path: Path | None = None) -> None:
        self._db_path = db_path or (PROJECT_ROOT / "db" / "channels.db")
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._engine = create_engine(f"sqlite:///{self._db_path}", future=True)
        self._session_factory = sessionmaker(bind=self._engine, expire_on_commit=False, future=True)
        self._ensure_schema()

    def save_analysis(self, snapshot: AudienceAnalysisSnapshot) -> None:
        report_payload = snapshot.report_payload
        themes_payload = report_payload.get("channel_themes", [])
        persona_payload = report_payload.get("audience_persona", {})
        dominant_theme = report_payload.get("dominant_theme", {}).get("label") or snapshot.dominant_theme_label
        secondary_themes = [
            theme.get("label")
            for theme in themes_payload
            if theme.get("label") and theme.get("label") != dominant_theme
        ][:3]
        audience_persona = (
            persona_payload.get("persona_summary")
            or persona_payload.get("description")
            or persona_payload.get("title")
            or ""
        )
        source_title = snapshot.source_title or report_payload.get("source", {}).get("title") or snapshot.source_key
        summary = snapshot.summary or report_payload.get("summary", "")
        payload_json = json.dumps(report_payload, ensure_ascii=False)

        with self._session_factory() as session:
            record = session.get(ChannelAnalysisORM, snapshot.source_key)
            if record is None:
                record = ChannelAnalysisORM(
                    source=snapshot.source_key,
                    analyzed_at=snapshot.analyzed_at,
                    updated_at=snapshot.analyzed_at,
                )
                session.add(record)

            record.title = source_title
            record.username = snapshot.source_username or ""
            record.audience_persona = audience_persona
            record.dominant_theme = dominant_theme or ""
            record.secondary_themes_json = json.dumps(secondary_themes, ensure_ascii=False)
            record.summary = summary
            record.report_payload_json = payload_json
            record.updated_at = snapshot.analyzed_at
            session.commit()

    def get_latest_analysis(self, source_key: str) -> AudienceAnalysisSnapshot | None:
        normalized = self._normalize_source_key(source_key)
        with self._session_factory() as session:
            statement = select(ChannelAnalysisORM).where(
                (ChannelAnalysisORM.source == normalized) | (ChannelAnalysisORM.username == normalized)
            )
            record = session.execute(statement).scalar_one_or_none()
            if record is None:
                return None
            return self._to_snapshot(record)

    def _ensure_schema(self) -> None:
        Base.metadata.create_all(self._engine)
        self._migrate_channels_table()
        self._drop_legacy_tables()
        self._sanitize_existing_payloads()

    def _migrate_channels_table(self) -> None:
        inspector = inspect(self._engine)
        if "channels" not in inspector.get_table_names():
            Base.metadata.create_all(self._engine)
            return

        existing_columns = [column["name"] for column in inspector.get_columns("channels")]
        column_meta = {column["name"]: column for column in inspector.get_columns("channels")}
        target_columns = [
            "source",
            "title",
            "username",
            "audience_persona",
            "dominant_theme",
            "secondary_themes_json",
            "summary",
            "report_payload_json",
            "analyzed_at",
            "updated_at",
        ]
        username_nullable = bool(column_meta.get("username", {}).get("nullable", True))
        if existing_columns == target_columns and not username_nullable:
            return

        select_expressions = {
            "source": "source",
            "title": "COALESCE(NULLIF(title, ''), source)",
            "username": "COALESCE(NULLIF(username, ''), '')",
            "audience_persona": "COALESCE(audience_persona, '')",
            "dominant_theme": "COALESCE(dominant_theme, '')",
            "secondary_themes_json": "COALESCE(secondary_themes_json, '[]')",
            "summary": "COALESCE(summary, '')",
            "report_payload_json": "COALESCE(report_payload_json, '{}')",
            "analyzed_at": "COALESCE(analyzed_at, updated_at, CURRENT_TIMESTAMP)",
            "updated_at": "COALESCE(updated_at, analyzed_at, CURRENT_TIMESTAMP)",
        }
        insert_columns = ", ".join(target_columns)
        select_clause = ", ".join(select_expressions[column] for column in target_columns)

        with self._engine.begin() as connection:
            connection.execute(text("DROP TABLE IF EXISTS channels__new"))
            connection.execute(
                text(
                    """
                    CREATE TABLE channels__new (
                        source TEXT NOT NULL PRIMARY KEY,
                        title TEXT NOT NULL DEFAULT '',
                        username TEXT NOT NULL DEFAULT '',
                        audience_persona TEXT NOT NULL DEFAULT '',
                        dominant_theme TEXT NOT NULL DEFAULT '',
                        secondary_themes_json TEXT NOT NULL DEFAULT '[]',
                        summary TEXT NOT NULL DEFAULT '',
                        report_payload_json TEXT NOT NULL DEFAULT '{}',
                        analyzed_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    )
                    """
                )
            )
            connection.execute(
                text(
                    f"""
                    INSERT INTO channels__new ({insert_columns})
                    SELECT {select_clause}
                    FROM channels
                    """
                )
            )
            connection.execute(text("DROP TABLE channels"))
            connection.execute(text("ALTER TABLE channels__new RENAME TO channels"))
            connection.execute(
                text("CREATE INDEX IF NOT EXISTS ix_channels_username ON channels(username)")
            )

    def _drop_legacy_tables(self) -> None:
        inspector = inspect(self._engine)
        if "knowledge_base_entries" not in inspector.get_table_names():
            return

        with self._engine.begin() as connection:
            row_count = connection.execute(
                text("SELECT COUNT(*) FROM knowledge_base_entries")
            ).scalar_one()
            if row_count == 0:
                connection.execute(text("DROP TABLE knowledge_base_entries"))

    def _sanitize_existing_payloads(self) -> None:
        with self._session_factory() as session:
            records = session.execute(select(ChannelAnalysisORM)).scalars().all()
            changed = False

            for record in records:
                snapshot = self._to_snapshot(record)
                if snapshot is None:
                    continue

                normalized_snapshot = build_audience_analysis_snapshot(
                    restore_audience_report(snapshot)
                )
                normalized_title = (
                    normalized_snapshot.source_title
                    or normalized_snapshot.report_payload.get("source", {}).get("title")
                    or normalized_snapshot.source_key
                )
                normalized_username = normalized_snapshot.source_username or ""
                normalized_payload_json = json.dumps(
                    normalized_snapshot.report_payload,
                    ensure_ascii=False,
                )
                normalized_secondary_themes_json = json.dumps(
                    [
                        theme.get("label")
                        for theme in normalized_snapshot.report_payload.get("channel_themes", [])
                        if theme.get("label")
                        and theme.get("label") != normalized_snapshot.dominant_theme_label
                    ][:3],
                    ensure_ascii=False,
                )

                if (
                    record.title != normalized_title
                    or record.username != normalized_username
                    or record.audience_persona
                    != (
                        normalized_snapshot.report_payload.get("audience_persona", {}).get("persona_summary")
                        or normalized_snapshot.report_payload.get("audience_persona", {}).get("description")
                        or normalized_snapshot.report_payload.get("audience_persona", {}).get("title")
                        or ""
                    )
                    or record.dominant_theme != (normalized_snapshot.dominant_theme_label or "")
                    or record.secondary_themes_json != normalized_secondary_themes_json
                    or record.summary != (normalized_snapshot.summary or "")
                    or record.report_payload_json != normalized_payload_json
                ):
                    record.title = normalized_title
                    record.username = normalized_username
                    record.audience_persona = (
                        normalized_snapshot.report_payload.get("audience_persona", {}).get("persona_summary")
                        or normalized_snapshot.report_payload.get("audience_persona", {}).get("description")
                        or normalized_snapshot.report_payload.get("audience_persona", {}).get("title")
                        or ""
                    )
                    record.dominant_theme = normalized_snapshot.dominant_theme_label or ""
                    record.secondary_themes_json = normalized_secondary_themes_json
                    record.summary = normalized_snapshot.summary or ""
                    record.report_payload_json = normalized_payload_json
                    changed = True

            if changed:
                session.commit()

    @staticmethod
    def _normalize_source_key(source: str) -> str:
        value = (source or "").strip()
        if value.startswith("@"):
            return value[1:]
        if value.startswith("https://t.me/") or value.startswith("http://t.me/"):
            tail = value.split("t.me/", 1)[1].strip("/")
            return tail.split("/", 1)[0].removeprefix("s/")
        return value

    @staticmethod
    def _to_snapshot(record: ChannelAnalysisORM) -> AudienceAnalysisSnapshot | None:
        if not record.report_payload_json:
            return None

        try:
            report_payload = json.loads(record.report_payload_json)
        except json.JSONDecodeError:
            return None
        if not isinstance(report_payload, dict):
            return None
        required_keys = {
            "source",
            "dominant_theme",
            "channel_themes",
            "audience_persona",
            "engagement_metrics",
        }
        if not required_keys.issubset(report_payload):
            return None
        dominant_theme_label = record.dominant_theme or report_payload.get("dominant_theme", {}).get("label", "")

        return AudienceAnalysisSnapshot(
            source_key=record.source,
            source_title=record.title or report_payload.get("source", {}).get("title", ""),
            source_username=record.username or None,
            entity_id=report_payload.get("source", {}).get("entity_id", 0),
            entity_type=report_payload.get("source", {}).get("entity_type", ""),
            analyzed_at=record.updated_at,
            dominant_theme_key=report_payload.get("dominant_theme", {}).get("key", ""),
            dominant_theme_label=dominant_theme_label,
            summary=record.summary or report_payload.get("summary", ""),
            report_payload=report_payload,
        )
