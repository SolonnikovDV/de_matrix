# -*- coding: utf-8 -*-
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (
    Integer,
    String,
    Text,
    DateTime,
    ForeignKey,
    UniqueConstraint,
    Boolean,
    JSON,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow():
    return datetime.now(timezone.utc)


MATRIX_STRUCT_SCHEMA = "matrix_struct"


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    role: Mapped[str] = mapped_column(String(32), default="user", nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    email: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)
    presence_sessions: Mapped[list["UserPresenceSession"]] = relationship("UserPresenceSession", back_populates="user")


class MatrixNode(Base):
    """
    Дерево матрицы произвольной глубины. Лист — узел без дочерних строк; leaf_view задаётся в JSON узла.
    Подписи уровней и схема колонок — в ui_config (matrix_levels / matrix_column_schema), не в DDL.
    """

    __tablename__ = "matrix_nodes"
    __table_args__ = {"schema": MATRIX_STRUCT_SCHEMA}
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    parent_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey(f"{MATRIX_STRUCT_SCHEMA}.matrix_nodes.id", ondelete="CASCADE"), nullable=True
    )
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    depth: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    title: Mapped[str] = mapped_column(Text, default="", nullable=False)
    code: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    responsible: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    level_sticker: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    template_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    level_tag: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    level_tags: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    leaf_view: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    review_questions: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    skill_payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    excel_path_key: Mapped[str] = mapped_column(Text, default="", nullable=False)


class MatrixLevelRegistry(Base):
    """Реестр таблиц уровней: display_name из импорта, sql_table — латинский идентификатор."""

    __tablename__ = "matrix_level_registry"
    __table_args__ = {"schema": MATRIX_STRUCT_SCHEMA}
    depth: Mapped[int] = mapped_column(Integer, primary_key=True)
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    sql_table: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)


class ActionTemplate(Base):
    __tablename__ = "action_templates"
    __table_args__ = {"schema": MATRIX_STRUCT_SCHEMA}
    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    is_parent: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    minimal_requirements: Mapped[list["ActionTemplateMinimalRequirement"]] = relationship(
        "ActionTemplateMinimalRequirement", cascade="all, delete-orphan", back_populates="template"
    )
    antipatterns: Mapped[list["ActionTemplateAntipattern"]] = relationship(
        "ActionTemplateAntipattern", cascade="all, delete-orphan", back_populates="template"
    )
    stack_refs: Mapped[list["ActionTemplateStackRef"]] = relationship(
        "ActionTemplateStackRef", cascade="all, delete-orphan", back_populates="template"
    )
    example_refs: Mapped[list["ActionTemplateExampleRef"]] = relationship(
        "ActionTemplateExampleRef", cascade="all, delete-orphan", back_populates="template"
    )
    literature_refs: Mapped[list["ActionTemplateLiteratureRef"]] = relationship(
        "ActionTemplateLiteratureRef", cascade="all, delete-orphan", back_populates="template"
    )


class ActionTemplateMinimalRequirement(Base):
    __tablename__ = "action_template_min_requirements"
    __table_args__ = (
        UniqueConstraint("template_id", "sort_order", name="uq_template_min_req_pos"),
        {"schema": MATRIX_STRUCT_SCHEMA},
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    template_id: Mapped[str] = mapped_column(ForeignKey(f"{MATRIX_STRUCT_SCHEMA}.action_templates.id", ondelete="CASCADE"), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)

    template: Mapped["ActionTemplate"] = relationship("ActionTemplate", back_populates="minimal_requirements")


class ActionTemplateAntipattern(Base):
    __tablename__ = "action_template_antipatterns"
    __table_args__ = (
        UniqueConstraint("template_id", "sort_order", name="uq_template_antipattern_pos"),
        {"schema": MATRIX_STRUCT_SCHEMA},
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    template_id: Mapped[str] = mapped_column(ForeignKey(f"{MATRIX_STRUCT_SCHEMA}.action_templates.id", ondelete="CASCADE"), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)

    template: Mapped["ActionTemplate"] = relationship("ActionTemplate", back_populates="antipatterns")


class ActionTemplateStackRef(Base):
    __tablename__ = "action_template_stack_refs"
    __table_args__ = (
        UniqueConstraint("template_id", "sort_order", name="uq_template_stack_ref_pos"),
        {"schema": MATRIX_STRUCT_SCHEMA},
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    template_id: Mapped[str] = mapped_column(ForeignKey(f"{MATRIX_STRUCT_SCHEMA}.action_templates.id", ondelete="CASCADE"), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    stack_key: Mapped[str] = mapped_column(String(128), nullable=False)

    template: Mapped["ActionTemplate"] = relationship("ActionTemplate", back_populates="stack_refs")


class ActionTemplateExampleRef(Base):
    __tablename__ = "action_template_example_refs"
    __table_args__ = (
        UniqueConstraint("template_id", "sort_order", name="uq_template_example_ref_pos"),
        {"schema": MATRIX_STRUCT_SCHEMA},
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    template_id: Mapped[str] = mapped_column(ForeignKey(f"{MATRIX_STRUCT_SCHEMA}.action_templates.id", ondelete="CASCADE"), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    example_ref: Mapped[str] = mapped_column(String(128), nullable=False)

    template: Mapped["ActionTemplate"] = relationship("ActionTemplate", back_populates="example_refs")


class ActionTemplateLiteratureRef(Base):
    __tablename__ = "action_template_literature_refs"
    __table_args__ = (
        UniqueConstraint("template_id", "sort_order", name="uq_template_literature_ref_pos"),
        {"schema": MATRIX_STRUCT_SCHEMA},
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    template_id: Mapped[str] = mapped_column(ForeignKey(f"{MATRIX_STRUCT_SCHEMA}.action_templates.id", ondelete="CASCADE"), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    literature_id: Mapped[str] = mapped_column(String(128), nullable=False)

    template: Mapped["ActionTemplate"] = relationship("ActionTemplate", back_populates="literature_refs")


class ActionExample(Base):
    __tablename__ = "action_examples"
    __table_args__ = (UniqueConstraint("example_id", name="uq_action_examples_example_id"), {"schema": MATRIX_STRUCT_SCHEMA})
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    example_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    title: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    language: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    code: Mapped[str] = mapped_column(Text, default="", nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)


class UiConfig(Base):
    __tablename__ = "ui_config"
    __table_args__ = {"schema": MATRIX_STRUCT_SCHEMA}
    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)


class UiSectionTitle(Base):
    __tablename__ = "ui_section_titles"
    __table_args__ = {"schema": MATRIX_STRUCT_SCHEMA}
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)


class UiSetting(Base):
    __tablename__ = "ui_settings"
    __table_args__ = {"schema": MATRIX_STRUCT_SCHEMA}
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    value: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)


class StableState(Base):
    __tablename__ = "stable_state"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    stable_backup_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class ChangeRequest(Base):
    __tablename__ = "change_requests"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="draft", nullable=False)
    merge_mode: Mapped[str] = mapped_column(String(64), default="append", nullable=False)
    target_domain: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    target_skill: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_by: Mapped[str] = mapped_column(String(64), default="system", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    applied: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    revisions: Mapped[list["ChangeRevision"]] = relationship(
        "ChangeRevision", cascade="all, delete-orphan", back_populates="change_request"
    )
    decisions: Mapped[list["ApprovalDecision"]] = relationship(
        "ApprovalDecision", cascade="all, delete-orphan", back_populates="change_request"
    )
    discussion_threads: Mapped[list["ChangeDiscussionThread"]] = relationship(
        "ChangeDiscussionThread", cascade="all, delete-orphan", back_populates="change_request"
    )


class ChangeRevision(Base):
    __tablename__ = "change_revisions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    change_request_id: Mapped[int] = mapped_column(ForeignKey("change_requests.id", ondelete="CASCADE"), nullable=False)
    staging_batch_id: Mapped[Optional[int]] = mapped_column(ForeignKey("staging_batches.id", ondelete="SET NULL"), nullable=True)
    revision_no: Mapped[int] = mapped_column(Integer, nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    note: Mapped[str] = mapped_column(Text, default="", nullable=False)
    created_by: Mapped[str] = mapped_column(String(64), default="system", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    change_request: Mapped["ChangeRequest"] = relationship("ChangeRequest", back_populates="revisions")
    __table_args__ = (UniqueConstraint("change_request_id", "revision_no", name="uq_change_revision_no"),)


class ApprovalDecision(Base):
    __tablename__ = "approval_decisions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    change_request_id: Mapped[int] = mapped_column(ForeignKey("change_requests.id", ondelete="CASCADE"), nullable=False)
    decision: Mapped[str] = mapped_column(String(32), nullable=False)  # in_review/approved/rejected/applied
    comment: Mapped[str] = mapped_column(Text, default="", nullable=False)
    actor: Mapped[str] = mapped_column(String(64), default="system", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    change_request: Mapped["ChangeRequest"] = relationship("ChangeRequest", back_populates="decisions")


class ChangeDiscussionThread(Base):
    __tablename__ = "change_discussion_threads"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    change_request_id: Mapped[int] = mapped_column(ForeignKey("change_requests.id", ondelete="CASCADE"), nullable=False)
    subject: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="open", nullable=False)  # open/needs_author_response/resolved
    requires_resolution: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_by: Mapped[str] = mapped_column(String(64), default="system", nullable=False)
    created_role: Mapped[str] = mapped_column(String(32), default="user", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    resolved_by: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    change_request: Mapped["ChangeRequest"] = relationship("ChangeRequest", back_populates="discussion_threads")
    messages: Mapped[list["ChangeDiscussionMessage"]] = relationship(
        "ChangeDiscussionMessage", cascade="all, delete-orphan", back_populates="thread"
    )


class ChangeDiscussionMessage(Base):
    __tablename__ = "change_discussion_messages"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    thread_id: Mapped[int] = mapped_column(ForeignKey("change_discussion_threads.id", ondelete="CASCADE"), nullable=False)
    author: Mapped[str] = mapped_column(String(64), default="system", nullable=False)
    author_role: Mapped[str] = mapped_column(String(32), default="user", nullable=False)
    body: Mapped[str] = mapped_column(Text, default="", nullable=False)
    kind: Mapped[str] = mapped_column(String(32), default="comment", nullable=False)  # comment/status
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    thread: Mapped["ChangeDiscussionThread"] = relationship("ChangeDiscussionThread", back_populates="messages")


class NotificationLog(Base):
    __tablename__ = "notification_logs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_type: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)  # pending/sent/failed/skipped
    subject: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    body: Mapped[str] = mapped_column(Text, default="", nullable=False)
    recipients: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    context: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    error: Mapped[str] = mapped_column(Text, default="", nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_by: Mapped[str] = mapped_column(String(64), default="system", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    last_attempt_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class UserPresenceSession(Base):
    __tablename__ = "user_presence_sessions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    username: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    session_token: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    ip_address: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    user_agent: Mapped[str] = mapped_column(String(512), default="", nullable=False)
    login_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    logout_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_reason: Mapped[str] = mapped_column(String(32), default="", nullable=False)  # logout/expired/system

    user: Mapped[Optional["User"]] = relationship("User", back_populates="presence_sessions")


class StagingBatch(Base):
    __tablename__ = "staging_batches"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_filename: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    merge_mode: Mapped[str] = mapped_column(String(64), default="append", nullable=False)
    target_domain: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    target_skill: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_by: Mapped[str] = mapped_column(String(64), default="system", nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="parsed", nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

