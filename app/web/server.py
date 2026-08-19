from __future__ import annotations

import hashlib
import json
import os
import socket
import subprocess
import sys
import threading
import time
import traceback
import uuid
import webbrowser
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qs, unquote, urlparse

from app.core.contracts import normalize_work_plan
from app.database.repository import Repository
from app.exporters.export_docx import export_chapter_docx, export_docx, export_range_docx
from app.exporters.export_txt import export_chapter_txt, export_range_txt, export_txt
from app.exporters.naming import book_export_path, chapter_export_path, chapter_range_export_path
from app.services.ai_client import AIClient, AIClientError
from app.services.base_agent import JsonValidationError
from app.utils.config import DATA_DIR, RESOURCE_DIR, ROOT_DIR, load_config, save_config
from app.utils.formatters import (
    format_context_readable,
    format_memory_readable,
    format_outline_readable,
    format_project_readable,
    format_review_readable,
)
from app.utils.context_filter import context_for_memory, context_for_reviewer, context_for_reviser
from app.utils.json_parser import json_dumps, parse_json_object
from app.utils.outline_utils import normalize_chapter_outline
from app.utils.text_cleaner import strip_chapter_heading
from app.utils.text_check import manuscript_quality_report, quality_summary, style_guard_warnings, style_regression_warnings
from app.utils.word_target import chapter_word_target_from_style
from app.web.config_api import balance_query_config, model_discovery_config, public_config, sanitize_config_update
from app.web.state import STATE
from app.workflow import NovelWorkflow


STATIC_DIR = RESOURCE_DIR / "web"
BRAND_LOGO_PATH = ROOT_DIR / "Hi Story.png"
TASK_CANCELLED_PREFIX = "任务已停止"


class ApiTokenError(ValueError):
    pass


class HiStoryWebHandler(BaseHTTPRequestHandler):
    server_version = "HiStoryWeb/1.0"

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path.startswith("/api/"):
            self._handle_api("GET", parsed.path, parsed.query)
            return
        self._serve_static(parsed.path)

    def do_POST(self) -> None:  # noqa: N802
        self._handle_api("POST", urlparse(self.path).path)

    def do_PUT(self) -> None:  # noqa: N802
        self._handle_api("PUT", urlparse(self.path).path)

    def do_DELETE(self) -> None:  # noqa: N802
        self._handle_api("DELETE", urlparse(self.path).path)

    def log_message(self, fmt: str, *args: Any) -> None:
        return

    def _handle_api(self, method: str, path: str, query_string: str = "") -> None:
        try:
            self._check_api_token(method, self._parts(path))
            query = {key: values[-1] for key, values in parse_qs(query_string).items() if values}
            result = self._route_api(method, self._parts(path), self._read_json(), query)
            self._send_json({"ok": True, "data": result})
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            return
        except ApiTokenError as exc:
            self._send_json({"ok": False, "error": str(exc)}, status=403)
        except ValueError as exc:
            self._send_json({"ok": False, "error": str(exc)}, status=400)
        except Exception as exc:  # noqa: BLE001
            if _is_expected_cancellation(exc):
                self._send_json({"ok": False, "error": str(exc)}, status=409)
                return
            _log_server_error(method, path, exc)
            self._send_json({"ok": False, "error": str(exc)}, status=500)

    def _check_api_token(self, method: str, parts: list[str]) -> None:
        if not _requires_api_token(method, parts):
            return
        token = self.headers.get("X-HiStory-Token", "")
        if not token or token != STATE.api_token:
            raise ApiTokenError("本地页面令牌无效，请刷新页面或重启服务。")

    def _route_api(
        self,
        method: str,
        parts: list[str],
        body: dict[str, Any],
        query: dict[str, str] | None = None,
    ) -> Any:
        query = query or {}
        if parts == ["api", "health"]:
            config = load_config()
            return {
                "service": "hi-story",
                "pid": os.getpid(),
                "root": str(ROOT_DIR),
                "status": "running",
                "mock_mode": bool(config.get("mock_mode", True)),
                "model": config.get("default_model", ""),
            }
        if parts == ["api", "config"]:
            if method == "GET":
                return public_config(load_config())
            if method == "PUT":
                config = sanitize_config_update(load_config(), body)
                save_config(config)
                STATE.reload_config()
                return public_config(config)
        if parts == ["api", "config", "test"] and method == "POST":
            return _test_ai_connection(body)
        if parts == ["api", "config", "models"] and method == "POST":
            task_id = _task_id(body)
            STATE.start_task(task_id, kind="configModels", title="获取可用模型")
            client: AIClient | None = None
            try:
                config = model_discovery_config(load_config(), _without_task_control(body))
                client = AIClient(config)
                STATE.register_task_cleanup(task_id, client.close)
                models = client.list_models()
            except AIClientError as exc:
                _finish_config_task_error(task_id, exc)
                raise ValueError(str(exc)) from exc
            except Exception as exc:
                _finish_config_task_error(task_id, exc)
                raise
            finally:
                if client is not None:
                    client.close()
                if not STATE.task_status(task_id).get("finished_at"):
                    STATE.finish_task(task_id)
            return {"models": models, "count": len(models)}
        if parts == ["api", "config", "balance"] and method == "POST":
            task_id = _task_id(body)
            STATE.start_task(task_id, kind="configBalance", title="查询账户余额")
            client: AIClient | None = None
            try:
                config = balance_query_config(load_config(), _without_task_control(body))
                client = AIClient(config)
                STATE.register_task_cleanup(task_id, client.close)
                return client.get_balance()
            except AIClientError as exc:
                _finish_config_task_error(task_id, exc)
                raise ValueError(str(exc)) from exc
            except Exception as exc:
                _finish_config_task_error(task_id, exc)
                raise
            finally:
                if client is not None:
                    client.close()
                if not STATE.task_status(task_id).get("finished_at"):
                    STATE.finish_task(task_id)
        if parts == ["api", "shutdown"] and method == "POST":
            threading.Thread(target=self.server.shutdown, daemon=True).start()
            return {"message": "服务正在关闭"}
        if len(parts) == 4 and parts[:2] == ["api", "tasks"] and parts[3] == "cancel" and method == "POST":
            if not STATE.cancel_task(parts[2]):
                raise ValueError("任务不存在或已经结束，请刷新页面后重试。")
            return STATE.task_status(parts[2]) or {"cancelled": True}
        if parts == ["api", "tasks", "active"] and method == "GET":
            return _active_task_state()
        if len(parts) == 3 and parts[:2] == ["api", "tasks"] and method == "GET":
            return STATE.task_status(parts[2])
        if parts == ["api", "works"] and method == "GET":
            return {"works": STATE.repo.list_works()}
        if parts == ["api", "works"] and method == "POST":
            STATE.assert_no_active_task("新建作品")
            work_id = STATE.repo.create_empty_work(_clean_inputs(body))
            return _work_state(work_id)

        if len(parts) >= 3 and parts[:2] == ["api", "works"]:
            work_id = _to_int(parts[2], "作品 ID")
            if _work_mutation_requires_idle_task(method, parts):
                STATE.assert_work_mutable(work_id)
            if len(parts) == 3:
                if method == "GET":
                    return _work_state(work_id)
                if method == "PUT":
                    STATE.repo.update_work_basic(work_id, _clean_inputs(body))
                    return _work_state(work_id)
                if method == "DELETE":
                    result = STATE.repo.delete_work(work_id)
                    return {**result, "works": STATE.repo.list_works()}

            if len(parts) == 4 and parts[3] == "summary" and method == "GET":
                return _work_summary_state(work_id)

            if len(parts) == 4 and parts[3] == "outline-state" and method == "GET":
                return _outline_state(work_id)

            if len(parts) == 4 and parts[3] == "settings-lock" and method in {"POST", "PUT"}:
                STATE.repo.set_work_settings_locked(work_id, bool(body.get("locked", False)))
                return _work_state(work_id)

            if len(parts) == 4 and parts[3] == "settings" and method == "PUT":
                settings = body.get("settings") if isinstance(body.get("settings"), dict) else {}
                contract = body.get("book_contract") if isinstance(body.get("book_contract"), dict) else {}
                STATE.repo.update_work_settings(
                    work_id,
                    settings,
                    contract,
                    expected_updated_at=str(body.get("expected_updated_at") or ""),
                )
                return _work_summary_state(work_id)

            if len(parts) == 4 and parts[3] == "book-contract" and method in {"POST", "PUT"}:
                STATE.repo.save_book_contract(work_id, body)
                return _work_state(work_id)

            if len(parts) == 4 and parts[3] == "plan-draft" and method == "POST":
                task_id = _task_id(body)
                _start_task(task_id, work_id, kind="plan", title="生成设定草稿", stage="project", input_data=body)
                try:
                    inputs = _clean_inputs(body or _inputs_from_work(STATE.repo.get_work(work_id)))
                    workflow = _task_workflow_for(task_id)
                    plan = normalize_work_plan(workflow.planner.generate_work_plan(inputs))
                    _raise_if_stopped(task_id, "任务已停止：设定草稿已返回，但未写入界面。")
                    return {"plan": plan, "readable": format_project_readable(plan)}
                except Exception as exc:
                    _finish_task_error(task_id, exc, work_id=work_id)
                    raise
                finally:
                    if not STATE.task_status(task_id).get("finished_at"):
                        _finish_task(task_id, work_id)

            if len(parts) == 4 and parts[3] == "apply-plan" and method == "POST":
                plan = normalize_work_plan(body.get("plan") or {})
                if not plan:
                    raise ValueError("没有可采用的设定草稿。")
                inputs = _clean_inputs(body.get("inputs") or _inputs_from_work(STATE.repo.get_work(work_id)))
                STATE.repo.apply_plan_to_work(work_id, inputs, plan)
                STATE.repo.log_agent_run(
                    work_id=work_id,
                    chapter_id=None,
                    agent_name="planner",
                    model=_task_workflow().client.model_for("planner"),
                    prompt_name="planner_prompt.md",
                    input_preview=json_dumps(inputs),
                    output=json_dumps(plan),
                )
                return _work_state(work_id)

            if len(parts) == 4 and parts[3] == "outline":
                if method == "POST":
                    task_id = _task_id(body)
                    _start_task(task_id, work_id, kind="outline", title="生成全书大纲", stage="outline", input_data=body)
                    try:
                        workflow = _task_workflow_for(task_id)
                        workflow.generate_outline(work_id, should_stop=lambda: STATE.task_cancelled(task_id))
                        return _outline_state(work_id)
                    except Exception as exc:
                        _finish_task_error(task_id, exc, work_id=work_id)
                        raise
                    finally:
                        if not STATE.task_status(task_id).get("finished_at"):
                            _finish_task(task_id, work_id)
                if method == "PUT":
                    return _save_outline(work_id, body)

            if len(parts) == 4 and parts[3] == "chapter-outlines" and method == "POST":
                task_id = _task_id(body)
                output_preview = ""
                _start_task(task_id, work_id, kind="chapterOutlines", title="生成章节细纲", stage="chapter_outline", input_data=body)
                try:
                    start = max(1, int(body.get("start_chapter") or 1))
                    count = min(30, max(1, int(body.get("count") or 3)))
                    volume_number = int(body["volume_number"]) if body.get("volume_number") not in (None, "") else None
                    workflow = _task_workflow_for(task_id)
                    outline_result = workflow.generate_chapter_outlines(
                        work_id,
                        start_chapter=start,
                        count=count,
                        volume_number=volume_number,
                        should_stop=lambda: STATE.task_cancelled(task_id),
                    )
                    chapters = outline_result.get("chapters", [])
                    volume_transition = outline_result.get("volume_transition", {})
                    if chapters:
                        first = chapters[0].get("chapter_number")
                        last = chapters[-1].get("chapter_number")
                        output_preview = f"生成 {len(chapters)} 章细纲：第 {first} 章至第 {last} 章。"
                    if volume_transition.get("changed"):
                        output_preview = (output_preview + "\n" if output_preview else "") + _volume_transition_preview(volume_transition)
                    partial_warning = ""
                    if len(chapters) < count:
                        partial_warning = f"AI 本次只返回了 {len(chapters)}/{count} 章细纲，已先保存可用章节。"
                    return {
                        "generated_chapters": chapters,
                        "partial_warning": partial_warning,
                        "volume_transition": volume_transition,
                        "volume_decision": outline_result.get("volume_decision", {}),
                        **_outline_state(work_id),
                    }
                except Exception as exc:
                    _finish_task_error(task_id, exc, work_id=work_id)
                    raise
                finally:
                    if not STATE.task_status(task_id).get("finished_at"):
                        _finish_task(task_id, work_id, output_preview=output_preview)

            if len(parts) == 4 and parts[3] == "export" and method == "POST":
                return _export_work(work_id, body)

            if len(parts) == 4 and parts[3] == "export-dir" and method == "GET":
                return _export_dir_state(work_id)

            if len(parts) == 5 and parts[3] == "export-dir" and method == "POST":
                action = parts[4]
                if action == "choose":
                    return _choose_export_dir(work_id)
                if action == "open":
                    return _open_export_dir(work_id)
                if action == "reset":
                    STATE.custom_export_dirs.pop(work_id, None)
                    return _export_dir_state(work_id)

            if len(parts) == 4 and parts[3] == "library" and method == "GET":
                return _library_state(work_id)

            if len(parts) == 4 and parts[3] == "records" and method == "GET":
                return {
                    "agent_runs": STATE.repo.list_agent_runs(work_id, limit=120),
                    "task_runs": STATE.repo.list_task_runs(work_id, limit=120),
                }

            if len(parts) == 4 and parts[3] == "records-page" and method == "GET":
                chapter_number = _optional_query_int(query.get("chapter_number"), "章节号")
                return STATE.repo.list_run_records(
                    work_id,
                    page=_query_int(query, "page", 1),
                    page_size=_query_int(query, "page_size", 40),
                    kind=str(query.get("kind") or "all"),
                    chapter_number=chapter_number,
                )

            if len(parts) == 6 and parts[3] == "library" and parts[5] == "items":
                kind = parts[4]
                if method == "GET":
                    if kind == "historical_profile":
                        profile = STATE.repo.get_historical_profile(work_id)
                        return {"items": [profile] if profile else [], "page": 1, "page_size": 1, "total": 1 if profile else 0}
                    return STATE.repo.list_library_page(
                        work_id,
                        kind,
                        page=_query_int(query, "page", 1),
                        page_size=_query_int(query, "page_size", 50),
                        search=str(query.get("q") or ""),
                        scope=str(query.get("scope") or "valid"),
                    )
            if len(parts) == 6 and parts[3] == "library" and parts[5] == "item" and method in {"POST", "PUT"}:
                item_id = _save_library_item_id(work_id, parts[4], body)
                item = body if parts[4] == "historical_profile" else STATE.repo.get_library_item(work_id, parts[4], item_id)
                return {"id": item_id, "item": item, "counts": STATE.repo.library_counts(work_id)}
            if len(parts) == 7 and parts[3] == "library" and parts[5] == "items":
                kind = parts[4]
                item_id = _to_int(parts[6], "资料 ID")
                if method == "GET":
                    item = STATE.repo.get_library_item(work_id, kind, item_id)
                    if item is None:
                        raise ValueError("资料不存在或已被删除。")
                    return item
                if method == "DELETE":
                    _delete_library_item_only(work_id, kind, item_id)
                    return {"deleted": True, "counts": STATE.repo.library_counts(work_id)}

            if len(parts) == 5 and parts[3] == "library" and method in {"POST", "PUT"}:
                return _save_library_item(work_id, parts[4], body)

            if len(parts) == 5 and parts[3] == "library" and parts[4] == "counts" and method == "GET":
                return STATE.repo.library_counts(work_id)

            if len(parts) == 6 and parts[3] == "library" and method == "DELETE":
                return _delete_library_item(work_id, parts[4], _to_int(parts[5], "资料 ID"))

            if len(parts) >= 5 and parts[3] == "chapters":
                chapter_number = _to_int(parts[4], "章节号")
                if len(parts) == 5:
                    if method == "GET":
                        return _chapter_state(work_id, chapter_number)
                    if method == "PUT":
                        return _save_chapter_text(work_id, chapter_number, body)
                    if method == "DELETE":
                        chapter = STATE.repo.get_chapter(work_id, chapter_number)
                        chapter_id = int(chapter["id"])
                        owner_id = f"delete-{uuid.uuid4().hex}"
                        STATE.claim_chapter(owner_id, work_id, chapter_id)
                        try:
                            chapter = STATE.repo.get_chapter(work_id, chapter_number)
                            _validate_chapter_request(
                                work_id,
                                chapter_number,
                                body,
                                chapter,
                                require_identity=True,
                            )
                            STATE.repo.delete_chapter(work_id, chapter_number, delete_related=True)
                        finally:
                            STATE.release_chapter(owner_id, work_id, chapter_id)
                        return _work_state(work_id)
                if len(parts) == 6 and parts[5] == "outline":
                    if method == "GET":
                        return {"chapter": normalize_chapter_outline(STATE.repo.get_chapter(work_id, chapter_number))}
                    if method == "PUT":
                        return _save_chapter_outline(work_id, chapter_number, body)
                if len(parts) == 6 and parts[5] == "context" and method == "GET":
                    return _chapter_context_state(work_id, chapter_number)
                if len(parts) == 6 and parts[5] == "clear-text" and method == "POST":
                    chapter = STATE.repo.get_chapter(work_id, chapter_number)
                    owner_id = f"clear-{uuid.uuid4().hex}"
                    STATE.claim_chapter(owner_id, work_id, int(chapter["id"]))
                    try:
                        chapter = STATE.repo.get_chapter(work_id, chapter_number)
                        _validate_chapter_request(work_id, chapter_number, body, chapter, require_identity=True)
                        STATE.repo.clear_chapter_text(work_id, chapter_number)
                    finally:
                        STATE.release_chapter(owner_id, work_id, int(chapter["id"]))
                    return _work_state(work_id)
                if len(parts) == 6 and parts[5] == "delete-from" and method == "DELETE":
                    chapter = STATE.repo.get_chapter(work_id, chapter_number)
                    chapter_ids = [
                        int(item["id"])
                        for item in STATE.repo.list_chapters(work_id)
                        if int(item.get("chapter_number") or 0) >= chapter_number
                    ]
                    owner_id = f"delete-from-{uuid.uuid4().hex}"
                    STATE.claim_chapters(owner_id, work_id, chapter_ids)
                    try:
                        chapter = STATE.repo.get_chapter(work_id, chapter_number)
                        _validate_chapter_request(work_id, chapter_number, body, chapter, require_identity=True)
                        deleted = STATE.repo.delete_chapters_from(work_id, chapter_number, delete_related=True)
                    finally:
                        STATE.release_chapters(owner_id, work_id, chapter_ids)
                    return {**_work_state(work_id), "deleted_count": deleted}
                if len(parts) == 6 and parts[5] == "generate" and method == "POST":
                    task_id = _task_id(body)
                    chapter_id = _chapter_id_or_none(work_id, chapter_number)
                    output_preview = ""
                    _start_task(
                        task_id,
                        work_id,
                        chapter_id=chapter_id,
                        kind="chapter",
                        title=f"生成第 {chapter_number} 章",
                        stage="writing",
                        input_data=body,
                    )
                    try:
                        mode = str(body.get("mode") or "standard")
                        formal_mode = mode != "fast"
                        workflow = _task_workflow_for(task_id)
                        result = workflow.generate_chapter(
                            work_id,
                            chapter_number,
                            do_review=formal_mode,
                            do_revise=formal_mode,
                            do_memory=bool(body.get("do_memory", False)),
                            should_stop=lambda: STATE.task_cancelled(task_id),
                            on_stage=lambda stage, detail: _update_task_stage(
                                task_id,
                                work_id,
                                chapter_id,
                                stage,
                                detail,
                            ),
                        )
                        output_preview = _chapter_task_preview(result)
                        return _chapter_result(work_id, chapter_number, result)
                    except Exception as exc:
                        _finish_task_error(task_id, exc, work_id=work_id, chapter_id=chapter_id)
                        raise
                    finally:
                        if not STATE.task_status(task_id).get("finished_at"):
                            _finish_task(task_id, work_id, chapter_id=chapter_id, output_preview=output_preview)
                if len(parts) == 6 and parts[5] == "memory" and method == "POST":
                    task_id = _task_id(body)
                    chapter_id = _chapter_id_or_none(work_id, chapter_number)
                    output_preview = ""
                    _start_task(
                        task_id,
                        work_id,
                        chapter_id=chapter_id,
                        kind="memory",
                        title=f"生成第 {chapter_number} 章记忆",
                        stage="memory",
                        input_data=body,
                    )
                    try:
                        workflow = _task_workflow_for(task_id)
                        result = _generate_memory(
                            work_id,
                            chapter_number,
                            body,
                            workflow=workflow,
                            should_stop=lambda: STATE.task_cancelled(task_id),
                        )
                        output_preview = f"第 {chapter_number} 章记忆已入库。"
                        return result
                    except Exception as exc:
                        _finish_task_error(task_id, exc, work_id=work_id, chapter_id=chapter_id)
                        raise
                    finally:
                        if not STATE.task_status(task_id).get("finished_at"):
                            _finish_task(task_id, work_id, chapter_id=chapter_id, output_preview=output_preview)
                if len(parts) == 6 and parts[5] in {"revise", "revision"} and method == "POST":
                    if not str(body.get("instruction") or "").strip():
                        raise ValueError("请先填写修改意见。")
                    if not str(body.get("current_text") or "").strip():
                        raise ValueError("当前正文为空，无法按意见修订。")
                    task_id = _task_id(body)
                    chapter_id = _chapter_id_or_none(work_id, chapter_number)
                    output_preview = ""
                    _start_task(
                        task_id,
                        work_id,
                        chapter_id=chapter_id,
                        kind="revise",
                        title=f"按意见修订第 {chapter_number} 章",
                        stage="revision",
                        input_data={"instruction": body.get("instruction", "")},
                    )
                    try:
                        workflow = _task_workflow_for(task_id)
                        result = _revise_chapter_with_instruction(
                            work_id,
                            chapter_number,
                            body,
                            workflow=workflow,
                            should_stop=lambda: STATE.task_cancelled(task_id),
                            on_stage=lambda stage, detail: _update_task_stage(
                                task_id,
                                work_id,
                                chapter_id,
                                stage,
                                detail,
                            ),
                        )
                        output_preview = str(result.get("message") or "").strip()
                        if not output_preview:
                            output_preview = (
                                f"第 {chapter_number} 章修订稿已保存为候选版本。"
                                if result.get("candidate_only")
                                else f"第 {chapter_number} 章正文修订已保存。"
                            )
                        return result
                    except Exception as exc:
                        _finish_task_error(task_id, exc, work_id=work_id, chapter_id=chapter_id)
                        raise
                    finally:
                        if not STATE.task_status(task_id).get("finished_at"):
                            _finish_task(task_id, work_id, chapter_id=chapter_id, output_preview=output_preview)
                if len(parts) == 7 and parts[5] == "versions" and method == "DELETE":
                    chapter = STATE.repo.get_chapter(work_id, chapter_number)
                    version_id = _to_int(parts[6], "版本 ID")
                    deleted = STATE.repo.delete_chapter_candidate(work_id, int(chapter["id"]), version_id)
                    return {"deleted": deleted}

        raise ValueError("未知接口。")

    def _serve_static(self, path: str) -> None:
        if path in {"", "/"}:
            file_path = STATIC_DIR / "index.html"
        elif path == "/brand-logo.png":
            file_path = BRAND_LOGO_PATH
        else:
            safe_path = unquote(path).lstrip("/")
            file_path = (STATIC_DIR / safe_path).resolve()
            try:
                file_path.relative_to(STATIC_DIR.resolve())
            except ValueError:
                self.send_error(403)
                return
        if not file_path.exists() or not file_path.is_file():
            self.send_error(404)
            return
        content_type = _content_type(file_path)
        data = file_path.read_bytes()
        if file_path == STATIC_DIR / "index.html":
            data = _inject_api_token(data)
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        raw = self.rfile.read(length).decode("utf-8")
        if not raw.strip():
            return {}
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError("请求体不是合法 JSON。") from exc
        if not isinstance(data, dict):
            raise ValueError("请求体必须是 JSON 对象。")
        return data

    def _send_json(self, payload: dict[str, Any], *, status: int = 200) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        try:
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            return

    @staticmethod
    def _parts(path: str) -> list[str]:
        return [part for part in path.strip("/").split("/") if part]


def run(host: str = "127.0.0.1", port: int = 8765, *, open_browser: bool = True) -> None:
    actual_port = _available_port(host, port)
    server = ThreadingHTTPServer((host, actual_port), HiStoryWebHandler)
    url = f"http://{host}:{actual_port}/"
    _write_server_url(url)
    if open_browser:
        threading.Timer(0.4, lambda: webbrowser.open(url)).start()
    server.serve_forever()


def _write_server_url(url: str) -> None:
    log_dir = DATA_DIR / "logs"
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        (log_dir / "server.url").write_text(f"{url}\ntoken={STATE.api_token}\n", encoding="utf-8")
    except OSError:
        return


def _inject_api_token(data: bytes) -> bytes:
    html = data.decode("utf-8")
    script = f"<script>window.__HI_STORY_TOKEN__ = {json.dumps(STATE.api_token)};</script>"
    if "</head>" in html:
        html = html.replace("</head>", script + "\n</head>", 1)
    else:
        html = script + html
    return html.encode("utf-8")


def _requires_api_token(method: str, parts: list[str]) -> bool:
    if parts == ["api", "health"]:
        return False
    return bool(parts and parts[0] == "api")


def _work_mutation_requires_idle_task(method: str, parts: list[str]) -> bool:
    if method == "GET":
        return False
    if len(parts) == 4 and parts[3] in {"plan-draft", "chapter-outlines"} and method == "POST":
        return False
    if len(parts) == 4 and parts[3] == "outline" and method == "POST":
        return False
    if len(parts) == 6 and parts[3] == "chapters" and parts[5] in {"generate", "memory", "revise", "revision"} and method == "POST":
        return False
    return True


def _task_workflow() -> NovelWorkflow:
    return NovelWorkflow(repo=Repository(), client=AIClient(load_config()))


def _task_workflow_for(task_id: str) -> NovelWorkflow:
    workflow = _task_workflow()
    STATE.register_task_cleanup(task_id, workflow.client.close)
    return workflow


def _test_ai_connection(body: dict[str, Any] | None = None) -> dict[str, Any]:
    task_id = _task_id(body or {})
    STATE.start_task(task_id, kind="configTest", title="接口连接测试")
    client: AIClient | None = None
    try:
        config = load_config()
        config["timeout"] = min(60, max(10, int(config.get("timeout", 300) or 300)))
        config["max_retries"] = 0
        config["max_output_tokens"] = 64
        config["model_reasoning_effort"] = "low"
        config["temperature"] = 0
        client = AIClient(config)
        STATE.register_task_cleanup(task_id, client.close)
        return client.test_connection()
    except AIClientError as exc:
        _finish_config_task_error(task_id, exc)
        raise ValueError(str(exc)) from exc
    except Exception as exc:
        _finish_config_task_error(task_id, exc)
        raise
    finally:
        if client is not None:
            client.close()
        if not STATE.task_status(task_id).get("finished_at"):
            STATE.finish_task(task_id)


def _finish_config_task_error(task_id: str, exc: Exception) -> None:
    message = str(exc)
    cancelled = STATE.task_cancelled(task_id) or message == "AI 请求已取消。"
    STATE.finish_task(task_id, status="cancelled" if cancelled else "failed", error=message)


def _available_port(host: str, start: int) -> int:
    for port in range(start, start + 50):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.bind((host, port))
            except OSError:
                continue
            return port
    raise RuntimeError("没有找到可用的本地端口。")


def _log_server_error(method: str, path: str, exc: Exception) -> None:
    log_dir = DATA_DIR / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    message = [
        "=" * 80,
        datetime.now().isoformat(timespec="seconds"),
        f"{method} {path}",
        "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)).rstrip(),
        "",
    ]
    try:
        with (log_dir / "server.log").open("a", encoding="utf-8") as f:
            f.write("\n".join(message))
    except OSError:
        return


def _is_expected_cancellation(exc: Exception) -> bool:
    message = str(exc)
    return message == "AI 请求已取消。" or message.startswith(TASK_CANCELLED_PREFIX)


def _task_id(body: dict[str, Any]) -> str:
    return str(body.get("task_id") or "").strip() or f"task-{uuid.uuid4().hex}"


def _without_task_control(body: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in body.items() if key != "task_id"}


def _raise_if_stopped(task_id: str, message: str) -> None:
    if STATE.task_cancelled(task_id):
        raise RuntimeError(message)


def _start_task(
    task_id: str,
    work_id: int,
    *,
    kind: str,
    title: str,
    stage: str = "",
    chapter_id: int | None = None,
    input_data: dict[str, Any] | None = None,
) -> None:
    STATE.start_task(task_id, kind=kind, title=title, work_id=work_id, chapter_id=chapter_id)
    try:
        STATE.repo.log_task_run(
            task_id=task_id,
            work_id=work_id,
            chapter_id=chapter_id,
            kind=kind,
            title=title,
            stage=stage,
            status="running",
            input_json=json_dumps(input_data or {}),
        )
    except Exception:
        STATE.finish_task(task_id, status="failed", error="任务记录初始化失败。")
        raise


def _finish_task(
    task_id: str,
    work_id: int,
    *,
    status: str = "done",
    error: str = "",
    chapter_id: int | None = None,
    output_preview: str = "",
) -> None:
    STATE.finish_task(task_id, status=status, error=error)
    task = STATE.task_status(task_id) or {}
    STATE.repo.log_task_run(
        task_id=task_id,
        work_id=work_id,
        chapter_id=chapter_id,
        status=str(task.get("status") or status),
        output_preview=output_preview,
        error=str(task.get("error") or error),
        finished_at=str(task.get("finished_at") or ""),
    )


def _update_task_stage(
    task_id: str,
    work_id: int,
    chapter_id: int | None,
    stage: str,
    detail: str,
) -> None:
    STATE.update_task_stage(task_id, stage, detail)
    STATE.repo.log_task_run(
        task_id=task_id,
        work_id=work_id,
        chapter_id=chapter_id,
        status="running",
        stage=stage,
        output_preview=detail,
    )


def _finish_task_error(task_id: str, exc: Exception, *, work_id: int | None = None, chapter_id: int | None = None) -> None:
    message = str(exc)
    status = "cancelled" if message.startswith(TASK_CANCELLED_PREFIX) or message == "AI 请求已取消。" else "failed"
    if work_id is None:
        STATE.finish_task(task_id, status=status, error=message)
    else:
        _finish_task(task_id, work_id, status=status, error=message, chapter_id=chapter_id)


def _chapter_id_or_none(work_id: int, chapter_number: int) -> int | None:
    try:
        chapter = STATE.repo.get_chapter(work_id, chapter_number)
        return int(chapter["id"])
    except Exception:  # noqa: BLE001
        return None


def _work_state(work_id: int) -> dict[str, Any]:
    work = STATE.repo.get_work(work_id)
    chapters = STATE.repo.list_chapters(work_id)
    project_bundle = {
        "work": work,
        "book_contract": STATE.repo.get_book_contract(work_id),
        "characters": [],
        "characters_deferred": True,
        "world_rules": STATE.repo.list_world_rules(work_id),
        "historical_profile": STATE.repo.get_historical_profile(work_id),
        "historical_facts": [],
        "historical_facts_deferred": True,
        "chapter_notes": [],
        "chapter_notes_deferred": True,
        "open_plot_threads": [],
        "open_plot_threads_deferred": True,
    }
    outline = _outline_data(work_id)
    return {
        "work": work,
        "works": STATE.repo.list_works(),
        "chapters": chapters,
        "book_contract": STATE.repo.get_book_contract(work_id),
        "workflow_state": STATE.repo.workflow_state(work_id),
        "project_readable": format_project_readable(project_bundle),
        "outline": outline,
        "export_dir": str(_current_export_dir(work_id)),
        "default_export_dir": str(STATE.repo.export_dir(work_id)),
        "custom_export_dir": work_id in STATE.custom_export_dirs,
    }


def _work_summary_state(work_id: int) -> dict[str, Any]:
    work = STATE.repo.get_work(work_id)
    chapters = STATE.repo.list_chapters(work_id)
    return {
        "work": work,
        "works": STATE.repo.list_works(),
        "chapters": chapters,
        "book_contract": STATE.repo.get_book_contract(work_id),
        "workflow_state": STATE.repo.workflow_state(work_id),
        "outline": {
            "full_outline": work.get("full_outline") or "",
            "volume_outline": parse_json_object(work.get("volume_outline") or "[]", default=[]),
            "chapters": chapters,
        },
        "export_dir": str(_current_export_dir(work_id)),
        "default_export_dir": str(STATE.repo.export_dir(work_id)),
        "custom_export_dir": work_id in STATE.custom_export_dirs,
    }


def _active_task_state() -> dict[str, Any]:
    tasks = STATE.active_tasks()
    for task in tasks:
        work_id = int(task.get("work_id") or 0)
        chapter_id = int(task.get("chapter_id") or 0)
        if not work_id or not chapter_id:
            continue
        chapter = next(
            (item for item in STATE.repo.list_chapters(work_id) if int(item.get("id") or 0) == chapter_id),
            None,
        )
        if chapter is not None:
            task["chapter_number"] = int(chapter.get("chapter_number") or 0)
    return {"tasks": tasks}


def _chapter_state(work_id: int, chapter_number: int) -> dict[str, Any]:
    chapter = STATE.repo.get_chapter(work_id, chapter_number)
    memory = parse_json_object(chapter.get("memory_json") or "{}", default={}) or {}
    chapter_word_target = _chapter_word_target(work_id)
    review = STATE.repo.get_review_for_current_text(work_id, int(chapter["id"]))
    return {
        "chapter": chapter,
        "review": review,
        "review_readable": format_review_readable(review),
        "candidate_versions": STATE.repo.list_chapter_candidates(work_id, int(chapter["id"]), limit=10),
        "chapter_word_target": chapter_word_target,
        "context": {"chapter_word_target": chapter_word_target},
        "context_readable": "",
        "context_error": "",
        "context_deferred": True,
        "memory_readable": format_memory_readable(memory),
        "outline_readable": format_outline_readable({"chapters": [chapter]}),
    }


def _chapter_context_state(work_id: int, chapter_number: int) -> dict[str, Any]:
    context = {}
    context_readable = ""
    context_error = ""
    try:
        context = _task_workflow().build_chapter_context(work_id, chapter_number)
        context_readable = format_context_readable(context)
    except Exception as exc:  # noqa: BLE001
        context_error = str(exc)
    return {
        "chapter_number": chapter_number,
        "context": context,
        "context_readable": context_readable,
        "context_error": context_error,
        "context_deferred": False,
        "chapter_word_target": context.get("chapter_word_target") or _chapter_word_target(work_id),
    }


def _chapter_word_target(work_id: int) -> dict[str, Any]:
    work = STATE.repo.get_work(work_id)
    return chapter_word_target_from_style(work.get("style", ""))


def _chapter_result(work_id: int, chapter_number: int, result: dict[str, Any]) -> dict[str, Any]:
    result_text = str(result.get("final_text") or result.get("draft") or "").strip()
    review = result.get("review") if result_text else None
    return {
        **_chapter_state(work_id, chapter_number),
        "draft": result.get("draft", ""),
        "final_text": result.get("final_text", ""),
        "review": review,
        "review_readable": format_review_readable(review),
        "memory": result.get("memory"),
        "memory_readable": format_memory_readable(result.get("memory")),
        "quality_gate": result.get("quality_gate", {}),
        "problem_draft": bool(result.get("problem_draft")),
        "partial_stage": str(result.get("partial_stage") or ""),
    }


def _volume_transition_preview(transition: dict[str, Any]) -> str:
    if not isinstance(transition, dict) or not transition.get("changed"):
        return ""
    from_label = f"第{transition.get('from_volume')}卷"
    to_label = f"第{transition.get('to_volume')}卷"
    if transition.get("from_title"):
        from_label += f"《{transition.get('from_title')}》"
    if transition.get("to_title"):
        to_label += f"《{transition.get('to_title')}》"
    lines = [f"已从{from_label}切换到{to_label}。"]
    if transition.get("reason"):
        lines.append(f"原因：{transition.get('reason')}")
    carry_over = transition.get("carry_over") or []
    if carry_over:
        lines.append("遗留线索：" + "、".join(str(item) for item in carry_over if str(item).strip()))
    return "\n".join(lines)


def _chapter_task_preview(result: dict[str, Any]) -> str:
    quality = result.get("quality_gate")
    if not isinstance(quality, dict):
        return ""
    summary = str(quality.get("summary") or "").strip()
    if result.get("partial_stage") and summary:
        return summary[:500]
    if quality.get("problem_draft"):
        draft = quality.get("draft") if isinstance(quality.get("draft"), dict) else {}
        blockers = quality.get("blockers") or draft.get("blockers") or []
        warnings = draft.get("warnings") or []
        chars = draft.get("visible_chars") or 0
        issues = _quality_issue_lines([*blockers, *warnings])
        detail = "\n" + "\n".join(issues) if issues else ""
        return f"问题草稿已保存：初稿约 {chars} 字符，阻断 {len(blockers)} 项，警告 {len(warnings)} 项。{detail}"
    final = quality.get("final")
    if not isinstance(final, dict):
        return summary[:300]
    blockers = final.get("blockers") or []
    warnings = final.get("warnings") or []
    chars = final.get("visible_chars") or 0
    issues = _quality_issue_lines([*blockers, *warnings])
    detail = "\n" + "\n".join(issues) if issues else ""
    return f"质量检查：终稿约 {chars} 字符，阻断 {len(blockers)} 项，警告 {len(warnings)} 项。{detail}"


def _quality_issue_lines(values: list[Any]) -> list[str]:
    lines = []
    seen = set()
    for value in values:
        text = str(value or "").strip().rstrip("。！？；;, ")
        if not text or text in seen:
            continue
        seen.add(text)
        lines.append(f"{len(lines) + 1}. {text}")
    return lines


def _save_chapter_text(work_id: int, chapter_number: int, body: dict[str, Any]) -> dict[str, Any]:
    chapter = STATE.repo.get_chapter(work_id, chapter_number)
    owner_id = f"manual-save-{uuid.uuid4().hex}"
    STATE.claim_chapter(owner_id, work_id, int(chapter["id"]))
    try:
        chapter = STATE.repo.get_chapter(work_id, chapter_number)
        return _save_chapter_text_claimed(work_id, chapter_number, body, chapter)
    finally:
        STATE.release_chapter(owner_id, work_id, int(chapter["id"]))


def _save_chapter_text_claimed(
    work_id: int,
    chapter_number: int,
    body: dict[str, Any],
    chapter: dict[str, Any],
) -> dict[str, Any]:
    _validate_chapter_request(work_id, chapter_number, body, chapter, require_identity=True)
    title = str(body.get("title") or chapter.get("title") or f"第{chapter_number}章").strip()
    text = strip_chapter_heading(str(body.get("final_text") or ""), chapter_number, title)
    try:
        context = _task_workflow().build_chapter_context(work_id, chapter_number)
    except Exception:  # noqa: BLE001
        context = {}
    quality = manuscript_quality_report(
        text,
        context,
        chapter_number=chapter_number,
        chapter_title=title,
        stage="手动保存稿",
    )
    hard_blockers = _manual_save_hard_blockers(quality)
    if hard_blockers:
        raise ValueError("正文不能保存：" + "；".join(hard_blockers))
    content_changed = text != str(chapter.get("final_text") or "")
    title_changed = title != str(chapter.get("title") or "")
    if not content_changed and not title_changed and not bool(body.get("invalidate_memory", False)):
        return {
            **_chapter_state(work_id, chapter_number),
            "quality_gate": {
                "manual": quality,
                "summary": quality_summary(quality),
                "warning_only": True,
                "saved_as_final": True,
                "already_saved": True,
            },
            "memory_invalidated": False,
        }
    if chapter.get("final_text"):
        STATE.repo.add_version(work_id, chapter["id"], "web_manual_before_save", chapter.get("final_text") or "")
    memory_invalidated = STATE.repo.save_final_after_manual_edit(
        work_id,
        chapter["id"],
        text,
        title=title,
        ending_hook="" if content_changed else chapter.get("ending_hook") or "",
        handoff="" if content_changed else chapter.get("handoff") or "",
        memory_json=chapter.get("memory_json") or "",
        invalidate_memory=bool(body.get("invalidate_memory", False)),
        expected_revision=int(chapter.get("revision") or 0),
    )
    if content_changed and [*(quality.get("blockers") or []), *(quality.get("warnings") or [])]:
        review = NovelWorkflow._local_quality_review(quality)
        review["revision_plan"] = NovelWorkflow._build_revision_plan(review, quality)
        STATE.repo.save_review(work_id, int(chapter["id"]), review)
    return {
        **_chapter_state(work_id, chapter_number),
        "quality_gate": {
            "manual": quality,
            "summary": quality_summary(quality),
            "warning_only": True,
            "saved_as_final": True,
        },
        "memory_invalidated": memory_invalidated,
    }


def _manual_save_hard_blockers(quality: dict[str, Any]) -> list[str]:
    hard_markers = ["为空"]
    blockers = []
    for item in quality.get("blockers") or []:
        text = str(item or "").strip()
        if text and any(marker in text for marker in hard_markers):
            blockers.append(text)
    return blockers


def _save_chapter_outline(work_id: int, chapter_number: int, body: dict[str, Any]) -> dict[str, Any]:
    try:
        existing = STATE.repo.get_chapter(work_id, chapter_number)
        outline_json = parse_json_object(existing.get("outline_json") or "{}", default={}) or {}
    except ValueError:
        outline_json = {}
    if not isinstance(outline_json, dict):
        outline_json = {}
    for key in [
        "story_time",
        "continuity_debt",
        "debt_type",
        "opening_mode",
        "opening_subject",
        "opening_trigger",
        "time_or_environment_function",
        "previous_anchor",
        "first_screen_conflict",
        "forbidden_opening",
        "reader_question_in",
        "reader_answer_out",
        "new_question_out",
        "chapter_goal",
        "reader_expectation",
        "conflict",
        "main_scene",
        "characters_present",
        "clues",
        "new_information",
        "chapter_payoff",
        "character_change",
        "foreshadowing",
        "emotional_turn",
        "emotional_rhythm",
        "ending_external_anchor",
        "next_opening_action",
        "next_continuity_debt",
        "forbidden",
        "handoff",
        "opening_hook",
        "volume_number",
    ]:
        if key in body:
            outline_json[key] = body.get(key)
    outline_json["chapter_number"] = chapter_number
    outline_json["volume_number"] = int(body.get("volume_number") or outline_json.get("volume_number") or 1)
    outline_json["title"] = str(body.get("title") or f"第{chapter_number}章")
    outline_json["outline"] = str(body.get("outline") or "")
    outline_json["ending_hook"] = str(body.get("ending_hook") or "")
    if "scene_cards" in body:
        outline_json["scene_cards"] = body.get("scene_cards") or []
    STATE.repo.upsert_chapter_outline(
        work_id=work_id,
        chapter_number=chapter_number,
        title=outline_json["title"],
        outline=outline_json["outline"],
        ending_hook=outline_json["ending_hook"],
        outline_json=outline_json,
        protect_written=False,
        title_source="manual",
        title_locked=True,
        title_reason="用户在大纲与细纲页面修改章节标题。",
    )
    return _chapter_state(work_id, chapter_number)


def _generate_memory(
    work_id: int,
    chapter_number: int,
    body: dict[str, Any],
    *,
    workflow: NovelWorkflow,
    should_stop: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    chapter = STATE.repo.get_chapter(work_id, chapter_number)
    _validate_chapter_request(work_id, chapter_number, body, chapter, require_identity=True)
    final_text = str(chapter.get("final_text") or "").strip()
    if not final_text and str(chapter.get("draft") or "").strip():
        # A problem draft is still a user-visible manuscript. Promote it before
        # memory generation so the memory card always points at final_text.
        final_text = str(chapter.get("draft") or "").strip()
        STATE.repo.save_final_after_manual_edit(
            work_id,
            int(chapter["id"]),
            final_text,
            title=chapter.get("title") or f"第{chapter_number}章",
            expected_revision=int(chapter.get("revision") or 0),
        )
        chapter = STATE.repo.get_chapter(work_id, chapter_number)
        final_text = str(chapter.get("final_text") or "").strip()
    if not final_text:
        raise ValueError("当前章节没有可保存的正文，无法生成记忆。")
    source_revision = int(chapter.get("revision") or 0)
    source_text_hash = hashlib.sha256(final_text.encode("utf-8")).hexdigest()
    context = workflow.build_chapter_context(work_id, chapter_number)
    memory_context = context_for_memory(context)
    try:
        memory = workflow.memory.make_memory_card(memory_context, final_text)
    except (AIClientError, JsonValidationError) as exc:
        _log_agent_call(
            work_id,
            chapter,
            workflow,
            agent_name="memory",
            prompt_name="memory_prompt.md",
            phase="章节记忆",
            input_preview={
                "chapter_number": chapter_number,
                "context_chars": len(json_dumps(memory_context)),
                "final_text_chars": len(final_text),
            },
            output="",
            status="failed",
            error=str(exc),
        )
        raise
    if should_stop and should_stop():
        raise RuntimeError("任务已停止：章节记忆已返回，但未入库。")
    memory = workflow.normalize_output_names(work_id, memory)
    memory["source_revision"] = source_revision
    memory["source_text_hash"] = source_text_hash
    memory_title_decision = workflow._memory_title_decision(
        chapter,
        memory,
        context,
        str(chapter.get("title") or f"第{chapter_number}章"),
    )
    STATE.repo.apply_memory_card(
        work_id=work_id,
        chapter_id=chapter["id"],
        chapter_number=chapter_number,
        memory=memory,
        title=memory_title_decision["title"],
        title_source=memory_title_decision.get("source"),
        title_reason=memory_title_decision.get("reason"),
        expected_revision=source_revision,
        expected_text_hash=source_text_hash,
        prune_intermediate=True,
    )
    STATE.repo.log_agent_run(
        work_id=work_id,
        chapter_id=chapter["id"],
        agent_name="memory",
        model=workflow.client.model_for("memory"),
        prompt_name="memory_prompt.md",
        input_preview=json_dumps(
            {
                "chapter_number": chapter_number,
                "source_revision": source_revision,
                "source_text_hash": source_text_hash,
            }
        ),
        output=json_dumps(memory),
        **workflow.client.last_usage("memory"),
    )
    return {
        **_chapter_state(work_id, chapter_number),
        "memory": memory,
        "memory_readable": format_memory_readable(memory),
        "pruned_intermediate_versions": True,
    }


def _revision_stage(
    on_stage: Callable[[str, str], None] | None,
    stage: str,
    detail: str,
) -> None:
    if on_stage:
        on_stage(stage, detail)


def _call_usage_for_log(workflow: NovelWorkflow, agent_name: str) -> dict[str, Any]:
    call = workflow.client.last_call(agent_name)
    return {
        key: call.get(key, 0 if key != "finish_reason" else "")
        for key in [
            "input_chars",
            "output_chars",
            "estimated_input_tokens",
            "estimated_output_tokens",
            "estimated_total_tokens",
            "elapsed_seconds",
            "finish_reason",
        ]
    }


def _log_agent_call(
    work_id: int,
    chapter: dict[str, Any],
    workflow: NovelWorkflow,
    *,
    agent_name: str,
    prompt_name: str,
    phase: str,
    input_preview: dict[str, Any],
    output: str,
    status: str = "ok",
    error: str = "",
) -> None:
    STATE.repo.log_agent_run(
        work_id=work_id,
        chapter_id=int(chapter["id"]),
        agent_name=agent_name,
        model=workflow.client.model_for(agent_name),
        prompt_name=prompt_name,
        input_preview=json_dumps({"phase": phase, **input_preview}),
        output=output,
        status=status,
        error=error,
        **_call_usage_for_log(workflow, agent_name),
    )


def _run_reviser_call(
    work_id: int,
    chapter: dict[str, Any],
    workflow: NovelWorkflow,
    *,
    phase: str,
    detail: str,
    input_preview: dict[str, Any],
    call: Callable[[], str],
    on_stage: Callable[[str, str], None] | None,
) -> str:
    _revision_stage(on_stage, "revision", detail)
    try:
        output = call()
    except Exception as exc:
        _log_agent_call(
            work_id,
            chapter,
            workflow,
            agent_name="reviser",
            prompt_name="reviser_prompt.md",
            phase=phase,
            input_preview=input_preview,
            output="",
            status="failed",
            error=str(exc),
        )
        raise
    _log_agent_call(
        work_id,
        chapter,
        workflow,
        agent_name="reviser",
        prompt_name="reviser_prompt.md",
        phase=phase,
        input_preview=input_preview,
        output=output,
    )
    return output


def _revision_quality_report(
    workflow: NovelWorkflow,
    original_text: str,
    revised_text: str,
    context: dict[str, Any],
    chapter_number: int,
    chapter_title: str,
    instruction: str,
) -> dict[str, Any]:
    quality = manuscript_quality_report(
        revised_text,
        context,
        chapter_number=chapter_number,
        chapter_title=chapter_title,
        stage="修订后",
    )
    blockers = [
        *(quality.get("blockers") or []),
        *style_regression_warnings(original_text, revised_text),
        *style_guard_warnings(revised_text),
        *workflow.revision_preservation_blockers(
            original_text,
            revised_text,
            context.get("chapter_word_target"),
            instruction,
        ),
    ]
    quality["blockers"] = list(dict.fromkeys(str(item).strip() for item in blockers if str(item).strip()))
    return quality


def _revision_correction_issues(
    workflow: NovelWorkflow,
    review: dict[str, Any],
    quality: dict[str, Any],
    expected_scenes: int,
) -> list[str]:
    issues = [
        *(quality.get("blockers") or []),
        *workflow.scene_coverage_blockers(review, expected_scenes),
    ]
    for problem in review.get("problems") or []:
        if not isinstance(problem, dict):
            continue
        # Medium findings are shown to the user but should not automatically
        # trigger another full-chapter model call. Reserve a second pass for
        # confirmed structural or continuity risks.
        if str(problem.get("severity") or "medium").lower() != "high":
            continue
        evidence = str(problem.get("evidence") or "").strip()
        reason = str(problem.get("why_it_matters") or "").strip()
        if evidence:
            issues.append(f"{evidence}；{reason}" if reason else evidence)
    return list(dict.fromkeys(str(item).strip() for item in issues if str(item).strip()))[:8]


def _apply_revision_review_blockers(
    workflow: NovelWorkflow,
    review: dict[str, Any],
    quality: dict[str, Any],
    expected_scenes: int,
) -> None:
    blockers = list(quality.get("blockers") or [])
    if not review.get("semantic_review_failed"):
        blockers.extend(workflow.scene_coverage_blockers(review, expected_scenes))
    quality["blockers"] = list(dict.fromkeys(str(item).strip() for item in blockers if str(item).strip()))
    merged = workflow._merge_quality_report_into_review(review, quality)
    review.clear()
    review.update(merged)
    review["revision_plan"] = workflow._build_revision_plan(review, quality)


def _revise_chapter_with_instruction(
    work_id: int,
    chapter_number: int,
    body: dict[str, Any],
    *,
    workflow: NovelWorkflow,
    should_stop: Callable[[], bool] | None = None,
    on_stage: Callable[[str, str], None] | None = None,
) -> dict[str, Any]:
    instruction = str(body.get("instruction") or "").strip()
    current_text = str(body.get("current_text") or "").strip()
    if not instruction:
        raise ValueError("请先填写修改意见。")
    if not current_text:
        raise ValueError("当前正文为空，无法按意见修订。")
    chapter = STATE.repo.get_chapter(work_id, chapter_number)
    _validate_chapter_request(work_id, chapter_number, body, chapter, require_identity=True)
    revision_limit = min(900, max(180, int(load_config().get("timeout", 300) or 300) * 2))
    revision_deadline = time.monotonic() + revision_limit

    def revision_expired() -> bool:
        return time.monotonic() >= revision_deadline

    def keep_candidate_if_expired(text: str, detail: str) -> dict[str, Any] | None:
        if not revision_expired():
            return None
        return _cancelled_revision_candidate(
            work_id,
            chapter_number,
            chapter,
            workflow,
            text,
            f"修订任务达到 {revision_limit} 秒总时限，{detail}",
        )

    _revision_stage(on_stage, "revision_prepare", "正在汇总修改要求")
    context = workflow.build_chapter_context(work_id, chapter_number)
    reviser_context = context_for_reviser(context)
    before_quality = manuscript_quality_report(
        current_text,
        context,
        chapter_number=chapter_number,
        chapter_title=chapter.get("title") or "",
        stage="修订前",
    )
    known_issues = list(
        dict.fromkeys(
            str(item).strip()
            for item in [
                *(before_quality.get("blockers") or []),
                *(before_quality.get("warnings") or []),
                *style_guard_warnings(current_text),
            ]
            if str(item).strip()
        )
    )[:8]
    revised = _run_reviser_call(
        work_id,
        chapter,
        workflow,
        phase="主修订",
        detail="正在进行第一轮修订",
        input_preview={"instruction": instruction, "known_issues": known_issues, "current_text": current_text[:3000]},
        call=lambda: workflow.reviser.revise_with_instruction(
            reviser_context,
            current_text,
            instruction,
            known_issues,
        ),
        on_stage=on_stage,
    )
    expired_result = keep_candidate_if_expired(revised, "已保存为候选稿")
    if expired_result is not None:
        return expired_result
    if should_stop and should_stop():
        return _cancelled_revision_candidate(
            work_id,
            chapter_number,
            chapter,
            workflow,
            revised,
            "第一轮修订稿已完整返回",
        )
    latest_chapter = STATE.repo.get_chapter(work_id, chapter_number)
    _validate_chapter_request(work_id, chapter_number, body, latest_chapter, require_identity=True)
    revised = workflow.normalize_output_names(work_id, revised)
    revised = strip_chapter_heading(revised, chapter_number, latest_chapter.get("title"))
    _revision_stage(on_stage, "revision_validate", "正在检查字数、语言和内容保留")
    after_quality = _revision_quality_report(
        workflow,
        current_text,
        revised,
        context,
        chapter_number,
        latest_chapter.get("title") or "",
        instruction,
    )
    try:
        post_review = _review_revised_text(
            work_id,
            chapter,
            revised,
            context,
            after_quality,
            workflow,
            phase="第一次语义复审",
            on_stage=on_stage,
            should_stop=should_stop,
        )
    except RuntimeError as exc:
        if not str(exc).startswith(TASK_CANCELLED_PREFIX):
            raise
        return _cancelled_revision_candidate(
            work_id,
            chapter_number,
            chapter,
            workflow,
            revised,
            "修订稿已返回，语义复审被停止",
        )
    expired_result = keep_candidate_if_expired(revised, "语义复审未继续")
    if expired_result is not None:
        return expired_result
    expected_scenes = len((reviser_context.get("story_plan") or {}).get("scene_cards") or [])
    correction_issues = _revision_correction_issues(
        workflow,
        post_review,
        after_quality,
        expected_scenes,
    )
    if correction_issues and not post_review.get("semantic_review_failed"):
        first_pass = revised
        first_pass_version_id = STATE.repo.add_version(
            work_id,
            chapter["id"],
            "web_user_instruction_first_pass",
            first_pass,
        )
        try:
            revised = _run_reviser_call(
                work_id,
                chapter,
                workflow,
                phase="定向返修",
                detail="复审发现实质问题，正在定向返修",
                input_preview={"instruction": instruction, "issues": correction_issues, "current_text": first_pass[:3000]},
                call=lambda: workflow.reviser.refine_revision(
                    reviser_context,
                    first_pass,
                    instruction,
                    post_review,
                    correction_issues,
                ),
                on_stage=on_stage,
            )
        except AIClientError as exc:
            message = f"第一轮修订已完成，但定向返修未完成：{exc} 第一轮稿已保留为候选稿，未覆盖最终稿。"
            return {
                **_chapter_state(work_id, chapter_number),
                "review": post_review,
                "review_readable": format_review_readable(post_review),
                "revised_text": first_pass,
                "saved": False,
                "candidate_only": True,
                "candidate_version_id": first_pass_version_id,
                "quality_blockers": [message, *correction_issues],
                "quality_gate": {"final": after_quality, "blockers": correction_issues},
                "message": message,
            }
        expired_result = keep_candidate_if_expired(revised, "定向返修已返回")
        if expired_result is not None:
            return expired_result
        if should_stop and should_stop():
            return _cancelled_revision_candidate(
                work_id,
                chapter_number,
                chapter,
                workflow,
                revised,
                "定向返修稿已完整返回",
            )
        revised = workflow.normalize_output_names(
            work_id,
            strip_chapter_heading(revised, chapter_number, latest_chapter.get("title")),
        )
        _revision_stage(on_stage, "revision_validate", "正在检查返修结果")
        after_quality = _revision_quality_report(
            workflow,
            current_text,
            revised,
            context,
            chapter_number,
            latest_chapter.get("title") or "",
            instruction,
        )
        try:
            post_review = _review_revised_text(
                work_id,
                chapter,
                revised,
                context,
                after_quality,
                workflow,
                phase="最终语义确认",
                on_stage=on_stage,
                should_stop=should_stop,
            )
        except RuntimeError as exc:
            if not str(exc).startswith(TASK_CANCELLED_PREFIX):
                raise
            return _cancelled_revision_candidate(
                work_id,
                chapter_number,
                chapter,
                workflow,
                revised,
                "定向返修稿已返回，最终确认被停止",
            )
        expired_result = keep_candidate_if_expired(revised, "最终语义确认未继续")
        if expired_result is not None:
            return expired_result
    _apply_revision_review_blockers(workflow, post_review, after_quality, expected_scenes)
    acceptance_blockers = workflow._automated_acceptance_blockers(after_quality)
    if post_review.get("semantic_review_failed"):
        acceptance_blockers = workflow._dedupe_texts(
            [
                "AI 语义复审未完成，当前修订稿只保留为候选稿；这是模型服务异常，不代表正文新增了质量问题。",
                *acceptance_blockers,
            ]
        )
    if acceptance_blockers:
        _revision_stage(on_stage, "revision_save", "正在保存问题候选稿")
        candidate_version_id = STATE.repo.add_version(
            work_id,
            chapter["id"],
            "web_user_instruction_candidate_style",
            revised,
        )
        return {
            **_chapter_state(work_id, chapter_number),
            "review": post_review,
            "review_readable": format_review_readable(post_review),
            "revised_text": revised,
            "saved": False,
            "candidate_only": True,
            "candidate_version_id": candidate_version_id,
            "quality_blockers": acceptance_blockers,
            "quality_gate": {"final": after_quality, "blockers": acceptance_blockers},
            "message": "修订稿未通过自动验收，已作为候选稿保留，未覆盖最终稿。",
        }
    _revision_stage(on_stage, "revision_save", "正在保存修订结果")
    content_changed = revised != str(latest_chapter.get("final_text") or "")
    memory_invalidated = content_changed and bool(str(latest_chapter.get("memory_json") or "").strip())
    revision_title_decision = workflow._final_title_decision(
        latest_chapter,
        post_review,
        context,
    )
    STATE.repo.add_version(work_id, chapter["id"], "web_user_instruction_before_revise", current_text)
    memory_invalidated = STATE.repo.save_final_after_manual_edit(
        work_id,
        chapter["id"],
        revised,
        title=revision_title_decision["title"],
        title_source=revision_title_decision.get("source"),
        title_reason=revision_title_decision.get("reason"),
        title_locked=False if revision_title_decision.get("source") else None,
        ending_hook="" if content_changed else latest_chapter.get("ending_hook") or "",
        handoff="" if content_changed else latest_chapter.get("handoff") or "",
        memory_json=latest_chapter.get("memory_json") or "",
        invalidate_memory=memory_invalidated,
        expected_revision=int(latest_chapter.get("revision") or 0),
    )
    latest_review = STATE.repo.get_latest_review(work_id, int(chapter["id"])) or {}
    revision_plan = latest_review.get("revision_plan") if isinstance(latest_review, dict) else []
    if not isinstance(revision_plan, list):
        revision_plan = []
    review_id = int(latest_review.get("id") or 0) if isinstance(latest_review, dict) else 0
    if revision_plan and review_id:
        STATE.repo.update_review_check(
            work_id,
            review_id,
            workflow.revision_check(before_quality, after_quality, revision_plan),
        )
    post_review["revision_check"] = workflow.revision_check(
        before_quality,
        after_quality,
        revision_plan,
    )
    post_review["revision_plan"] = workflow._build_revision_plan(post_review, after_quality)
    STATE.repo.save_review(work_id, int(chapter["id"]), post_review)
    return {
        **_chapter_state(work_id, chapter_number),
        "review": post_review,
        "review_readable": format_review_readable(post_review),
        "revised_text": revised,
        "saved": True,
        "memory_invalidated": memory_invalidated,
        "quality_gate": {"final": after_quality, "blockers": []},
    }


def _cancelled_revision_candidate(
    work_id: int,
    chapter_number: int,
    chapter: dict[str, Any],
    workflow: NovelWorkflow,
    revised: str,
    detail: str,
) -> dict[str, Any]:
    latest_chapter = STATE.repo.get_chapter(work_id, chapter_number)
    cleaned = workflow.normalize_output_names(
        work_id,
        strip_chapter_heading(revised, chapter_number, latest_chapter.get("title")),
    ).strip()
    if not cleaned:
        raise RuntimeError("任务已停止：模型没有返回可保留的修订正文。")
    candidate_version_id = STATE.repo.add_version(
        work_id,
        int(chapter["id"]),
        "web_user_instruction_candidate_style",
        cleaned,
    )
    message = f"任务已停止；{detail}，已保存为候选稿，未覆盖最终稿。"
    return {
        **_chapter_state(work_id, chapter_number),
        "revised_text": cleaned,
        "saved": False,
        "candidate_only": True,
        "candidate_version_id": candidate_version_id,
        "quality_blockers": [message],
        "message": message,
    }


def _review_revised_text(
    work_id: int,
    chapter: dict[str, Any],
    text: str,
    context: dict[str, Any],
    quality: dict[str, Any],
    workflow: NovelWorkflow,
    *,
    phase: str,
    on_stage: Callable[[str, str], None] | None = None,
    should_stop: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    review_context = dict(context)
    review_context["local_quality_report"] = quality
    reviewer_context = context_for_reviewer(review_context)
    review: dict[str, Any] | None = None
    last_error: Exception | None = None
    for attempt in range(2):
        detail = "正在检查场景、承接和人物因果" if attempt == 0 else "复审格式不完整，正在重新确认"
        _revision_stage(on_stage, "revision_review", detail)
        try:
            review = workflow.reviewer.review_chapter(reviewer_context, text)
        except JsonValidationError as exc:
            last_error = exc
            _log_agent_call(
                work_id,
                chapter,
                workflow,
                agent_name="reviewer",
                prompt_name="reviewer_prompt.md",
                phase=f"{phase}{'格式重试' if attempt else ''}",
                input_preview={"context": reviewer_context, "draft": text[:3000]},
                output="",
                status="invalid",
                error=str(exc),
            )
            if attempt == 0:
                continue
            break
        except AIClientError as exc:
            last_error = exc
            _log_agent_call(
                work_id,
                chapter,
                workflow,
                agent_name="reviewer",
                prompt_name="reviewer_prompt.md",
                phase=phase,
                input_preview={"context": reviewer_context, "draft": text[:3000]},
                output="",
                status="failed",
                error=str(exc),
            )
            break
        else:
            review = workflow.normalize_output_names(work_id, review)
            _log_agent_call(
                work_id,
                chapter,
                workflow,
                agent_name="reviewer",
                prompt_name="reviewer_prompt.md",
                phase=f"{phase}{'格式重试' if attempt else ''}",
                input_preview={"context": reviewer_context, "draft": text[:3000]},
                output=json_dumps(review),
            )
            break
    if should_stop and should_stop():
        raise RuntimeError("任务已停止：语义复审已返回，但未继续保存。")
    if review is None:
        review = workflow._local_quality_review(quality)
        review["stage_warning"] = f"修订稿语义复审失败：{last_error or '没有取得有效结果'}"
        review["semantic_review_failed"] = True
    review = workflow._merge_quality_report_into_review(review, quality)
    review["revision_plan"] = workflow._build_revision_plan(review, quality)
    return review


def _outline_data(work_id: int) -> dict[str, Any]:
    work = STATE.repo.get_work(work_id)
    chapters = [normalize_chapter_outline(chapter) for chapter in STATE.repo.list_chapter_outlines(work_id)]
    return {
        "full_outline": work.get("full_outline") or "",
        "volume_outline": parse_json_object(work.get("volume_outline") or "[]", default=[]),
        "chapters": chapters,
    }


def _outline_state(work_id: int) -> dict[str, Any]:
    work = STATE.repo.get_work(work_id)
    return {
        "work": work,
        "works": STATE.repo.list_works(),
        "outline": {
            "full_outline": work.get("full_outline") or "",
            "volume_outline": parse_json_object(work.get("volume_outline") or "[]", default=[]),
            "chapters": STATE.repo.list_chapter_outline_summaries(work_id),
        },
    }


def _save_outline(work_id: int, body: dict[str, Any]) -> dict[str, Any]:
    volume_outline = body.get("volume_outline")
    if isinstance(volume_outline, str):
        volume_outline = parse_json_object(volume_outline or "[]", default=[])
    if not isinstance(volume_outline, list):
        volume_outline = []
    STATE.repo.save_outline(
        work_id,
        {
            "full_outline": str(body.get("full_outline") or ""),
            "volume_outline": volume_outline,
        },
    )
    return _outline_state(work_id)


def _export_work(work_id: int, body: dict[str, Any]) -> dict[str, Any]:
    fmt = str(body.get("format") or "txt").lower()
    if fmt not in {"txt", "docx"}:
        raise ValueError("暂不支持该导出格式。请选择 TXT 或 DOCX。")
    scope = str(body.get("scope") or "book")
    include_draft = bool(body.get("include_draft", False))
    work = STATE.repo.get_work(work_id)
    output_dir = _current_export_dir(work_id)
    custom = work_id in STATE.custom_export_dirs
    if scope == "chapter":
        chapter_number = max(1, int(body.get("chapter_number") or 1))
        _validate_export_ready(work_id, scope="chapter", include_draft=include_draft, start=chapter_number, end=chapter_number)
        chapter = STATE.repo.get_chapter(work_id, chapter_number)
        output_path = chapter_export_path(work, chapter, fmt, output_dir.parent if not custom else None)
        if custom:
            output_path = output_dir / output_path.name
        path = (
            export_chapter_txt(STATE.repo, work_id, chapter_number, output_path, include_draft=include_draft)
            if fmt == "txt"
            else export_chapter_docx(STATE.repo, work_id, chapter_number, output_path, include_draft=include_draft)
        )
    elif scope == "range":
        start = max(1, int(body.get("start_chapter") or 1))
        end = max(start, int(body.get("end_chapter") or start))
        _validate_export_ready(work_id, scope="range", include_draft=include_draft, start=start, end=end)
        output_path = chapter_range_export_path(work, start, end, fmt, output_dir.parent if not custom else None)
        if custom:
            output_path = output_dir / output_path.name
        path = (
            export_range_txt(STATE.repo, work_id, start, end, output_path, include_draft=include_draft)
            if fmt == "txt"
            else export_range_docx(STATE.repo, work_id, start, end, output_path, include_draft=include_draft)
        )
    else:
        _validate_export_ready(work_id, scope="book", include_draft=include_draft)
        output_path = book_export_path(work, fmt, output_dir.parent if not custom else None)
        if custom:
            output_path = output_dir / output_path.name
        path = (
            export_txt(STATE.repo, work_id, output_path, include_draft=include_draft)
            if fmt == "txt"
            else export_docx(STATE.repo, work_id, output_path, include_draft=include_draft)
        )
    return {"path": str(path)}


def _validate_export_ready(
    work_id: int,
    *,
    scope: str,
    include_draft: bool,
    start: int | None = None,
    end: int | None = None,
) -> None:
    chapters = STATE.repo.chapters_for_export(work_id)
    if not chapters:
        raise ValueError("没有可导出的章节。请先生成正文。")
    by_number = {int(chapter.get("chapter_number") or 0): chapter for chapter in chapters}
    if scope == "book":
        numbers = sorted(number for number in by_number if number > 0)
        expected = list(range(1, numbers[-1] + 1)) if numbers else []
    else:
        if start is None or end is None:
            raise ValueError("导出范围不完整。")
        expected = list(range(int(start), int(end) + 1))
    missing = []
    empty = []
    for number in expected:
        chapter = by_number.get(number)
        if not chapter:
            missing.append(number)
            continue
        if not _exportable_chapter_text(chapter, include_draft=include_draft).strip():
            empty.append(number)
    if missing or empty:
        details = []
        if missing:
            details.append("缺少章节：" + _chapter_number_list(missing))
        if empty:
            label = "没有可导出的正式稿/草稿" if include_draft else "没有可导出的正式稿"
            details.append(f"{label}：" + _chapter_number_list(empty))
        raise ValueError("导出中止：" + "；".join(details) + "。请补齐后再导出。")


def _exportable_chapter_text(chapter: dict[str, Any], *, include_draft: bool) -> str:
    text = str(chapter.get("final_text") or "")
    if include_draft and not text.strip():
        text = str(chapter.get("draft") or "")
    return text


def _chapter_number_list(numbers: list[int]) -> str:
    return "、".join(f"第 {number} 章" for number in numbers[:20]) + (" 等" if len(numbers) > 20 else "")


def _current_export_dir(work_id: int) -> Path:
    return STATE.custom_export_dirs.get(work_id) or STATE.repo.export_dir(work_id)


def _export_dir_state(work_id: int) -> dict[str, Any]:
    return {
        "export_dir": str(_current_export_dir(work_id)),
        "default_export_dir": str(STATE.repo.export_dir(work_id)),
        "custom": work_id in STATE.custom_export_dirs,
    }


def _choose_export_dir(work_id: int) -> dict[str, Any]:
    try:
        import tkinter as tk
        from tkinter import filedialog
    except ImportError as exc:
        raise ValueError("当前 Python 环境无法打开目录选择框。") from exc

    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    initial = _current_export_dir(work_id)
    initial.mkdir(parents=True, exist_ok=True)
    selected = filedialog.askdirectory(title="选择导出位置", initialdir=str(initial))
    root.destroy()
    if selected:
        STATE.custom_export_dirs[work_id] = Path(selected)
    return _export_dir_state(work_id)


def _open_export_dir(work_id: int) -> dict[str, Any]:
    path = _current_export_dir(work_id)
    path.mkdir(parents=True, exist_ok=True)
    try:
        if os.name == "nt":
            os.startfile(str(path))  # type: ignore[attr-defined]
        else:
            opener = "open" if sys.platform == "darwin" else "xdg-open"
            subprocess.Popen([opener, str(path)])
    except OSError as exc:
        raise ValueError(f"无法打开导出目录：{exc}") from exc
    return _export_dir_state(work_id)


def _library_state(work_id: int) -> dict[str, Any]:
    return {
        "characters": STATE.repo.list_characters(work_id),
        "world_rules": STATE.repo.list_world_rules(work_id),
        "plot_threads": STATE.repo.list_plot_threads(work_id),
        "timeline": STATE.repo.list_timeline(work_id, limit=200),
        "chapter_notes": STATE.repo.list_chapter_notes(work_id),
        "sync_events": STATE.repo.list_sync_events(work_id, limit=100),
        "historical_profile": STATE.repo.get_historical_profile(work_id),
        "historical_facts": STATE.repo.list_historical_facts(work_id, limit=200),
    }


def _save_library_item(work_id: int, kind: str, body: dict[str, Any]) -> dict[str, Any]:
    item_id = _save_library_item_id(work_id, kind, body)
    return {"id": item_id, **_library_state(work_id)}


def _save_library_item_id(work_id: int, kind: str, body: dict[str, Any]) -> int:
    if kind == "characters":
        item_id = STATE.repo.upsert_character(work_id, body)
    elif kind == "world_rules":
        item_id = STATE.repo.upsert_world_rule(work_id, body)
    elif kind == "plot_threads":
        item_id = STATE.repo.upsert_plot_thread(work_id, body)
    elif kind == "timeline":
        item_id = STATE.repo.upsert_timeline_event(work_id, body)
    elif kind == "chapter_notes":
        item_id = STATE.repo.upsert_chapter_note(work_id, body)
    elif kind == "historical_profile":
        STATE.repo.upsert_historical_profile(work_id, body)
        item_id = work_id
    elif kind == "historical_facts":
        item_id = STATE.repo.upsert_historical_fact(work_id, body)
    else:
        raise ValueError("该资料类型暂不支持保存。")
    return int(item_id)


def _delete_library_item(work_id: int, kind: str, item_id: int) -> dict[str, Any]:
    _delete_library_item_only(work_id, kind, item_id)
    return _library_state(work_id)


def _delete_library_item_only(work_id: int, kind: str, item_id: int) -> None:
    if kind == "characters":
        STATE.repo.delete_character(work_id, item_id)
    elif kind == "world_rules":
        STATE.repo.delete_world_rule(work_id, item_id)
    elif kind == "plot_threads":
        STATE.repo.delete_plot_thread(work_id, item_id)
    elif kind == "timeline":
        STATE.repo.delete_timeline_event(work_id, item_id)
    elif kind == "chapter_notes":
        STATE.repo.delete_chapter_note(work_id, item_id)
    elif kind == "historical_facts":
        STATE.repo.delete_historical_fact(work_id, item_id)
    else:
        raise ValueError("该资料类型暂不支持删除。")


def _query_int(query: dict[str, str], key: str, default: int) -> int:
    raw = str(query.get(key) or "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(f"查询参数 {key} 必须是整数。") from exc


def _optional_query_int(raw: str | None, label: str) -> int | None:
    if raw is None or not str(raw).strip():
        return None
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(f"{label}必须是整数。") from exc


def _clean_inputs(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "title": str(data.get("title") or "").strip(),
        "idea": str(data.get("idea") or "").strip(),
        "genre": str(data.get("genre") or "").strip(),
        "platform": str(data.get("platform") or "").strip(),
        "target_words": int(data.get("target_words") or 0),
        "style": str(data.get("style") or "").strip(),
        "forbidden_tropes": str(data.get("forbidden_tropes") or "").strip(),
        "protagonist_preference": str(data.get("protagonist_preference") or "").strip(),
        "reader_profile": str(data.get("reader_profile") or "").strip(),
        "locked_facts": str(data.get("locked_facts") or "").strip(),
        "writing_controls": str(data.get("writing_controls") or "").strip(),
    }


def _inputs_from_work(work: dict[str, Any]) -> dict[str, Any]:
    return _clean_inputs(
        {
            "title": work.get("title", ""),
            "idea": work.get("idea", ""),
            "genre": work.get("genre", ""),
            "platform": work.get("platform", ""),
            "target_words": work.get("target_words", 0),
            "style": work.get("style", ""),
            "reader_profile": work.get("reader_profile", ""),
            "forbidden_tropes": work.get("forbidden_tropes", ""),
            "protagonist_preference": work.get("protagonist_preference", ""),
            "locked_facts": work.get("locked_facts", ""),
        }
    )


def _validate_chapter_request(
    work_id: int,
    chapter_number: int,
    body: dict[str, Any],
    chapter: dict[str, Any] | None = None,
    *,
    require_identity: bool = False,
) -> None:
    chapter = chapter or STATE.repo.get_chapter(work_id, chapter_number)
    request_chapter_id = body.get("chapter_id")
    if require_identity and request_chapter_id in (None, ""):
        raise ValueError("当前操作缺少章节身份信息，请重新载入章节后再操作。")
    if request_chapter_id not in (None, "") and int(request_chapter_id) != int(chapter["id"]):
        raise ValueError("当前编辑区与目标章节不一致，请重新载入章节后再操作。")
    request_updated_at = str(body.get("updated_at") or "").strip()
    current_updated_at = str(chapter.get("updated_at") or "").strip()
    request_revision = body.get("revision")
    current_revision = int(chapter.get("revision") or 0)
    if request_revision not in (None, "") and int(request_revision) != current_revision:
        raise ValueError("该章节已被其他操作更新，请重新载入章节后再操作。")
    if request_revision in (None, "") and request_updated_at and current_updated_at and request_updated_at != current_updated_at:
        raise ValueError("该章节已被其他操作更新，请重新载入章节后再操作。")


def _to_int(value: str, label: str) -> int:
    try:
        return int(value)
    except ValueError as exc:
        raise ValueError(f"{label}不是有效数字。") from exc


def _content_type(path: Path) -> str:
    if path.suffix == ".html":
        return "text/html; charset=utf-8"
    if path.suffix == ".css":
        return "text/css; charset=utf-8"
    if path.suffix == ".js":
        return "application/javascript; charset=utf-8"
    if path.suffix == ".png":
        return "image/png"
    if path.suffix == ".ico":
        return "image/x-icon"
    return "application/octet-stream"
