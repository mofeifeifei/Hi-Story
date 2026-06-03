from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable
from urllib.parse import unquote, urlparse

from app.core.contracts import normalize_work_plan
from app.exporters.export_docx import export_chapter_docx, export_docx, export_range_docx
from app.exporters.export_txt import export_chapter_txt, export_range_txt, export_txt
from app.exporters.naming import book_export_path, chapter_export_path, chapter_range_export_path
from app.utils.config import RESOURCE_DIR, ROOT_DIR, load_config, save_config
from app.utils.formatters import (
    format_context_readable,
    format_memory_readable,
    format_outline_readable,
    format_project_readable,
    format_review_readable,
)
from app.utils.json_parser import json_dumps, parse_json_object
from app.web.config_api import public_config, sanitize_config_update
from app.web.state import STATE


STATIC_DIR = RESOURCE_DIR / "web"
BRAND_LOGO_PATH = ROOT_DIR / "Hi Story.png"
TASK_CANCELLED_PREFIX = "任务已停止"


class HiStoryWebHandler(BaseHTTPRequestHandler):
    server_version = "HiStoryWeb/1.0"

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path.startswith("/api/"):
            self._handle_api("GET", parsed.path)
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

    def _handle_api(self, method: str, path: str) -> None:
        try:
            result = self._route_api(method, self._parts(path), self._read_json())
            self._send_json({"ok": True, "data": result})
        except ValueError as exc:
            self._send_json({"ok": False, "error": str(exc)}, status=400)
        except Exception as exc:  # noqa: BLE001
            self._send_json({"ok": False, "error": str(exc)}, status=500)

    def _route_api(self, method: str, parts: list[str], body: dict[str, Any]) -> Any:
        if parts == ["api", "health"]:
            config = load_config()
            return {
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
            return STATE.workflow.client.test_connection()
        if parts == ["api", "shutdown"] and method == "POST":
            threading.Thread(target=self.server.shutdown, daemon=True).start()
            return {"message": "服务正在关闭"}
        if len(parts) == 4 and parts[:2] == ["api", "tasks"] and parts[3] == "cancel" and method == "POST":
            STATE.cancel_task(parts[2])
            return STATE.task_status(parts[2]) or {"cancelled": True}
        if len(parts) == 3 and parts[:2] == ["api", "tasks"] and method == "GET":
            return STATE.task_status(parts[2])
        if parts == ["api", "works"] and method == "GET":
            return {"works": STATE.repo.list_works()}
        if parts == ["api", "works"] and method == "POST":
            work_id = STATE.repo.create_empty_work(_clean_inputs(body))
            return _work_state(work_id)

        if len(parts) >= 3 and parts[:2] == ["api", "works"]:
            work_id = _to_int(parts[2], "作品 ID")
            if len(parts) == 3:
                if method == "GET":
                    return _work_state(work_id)
                if method == "PUT":
                    STATE.repo.update_work_basic(work_id, _clean_inputs(body))
                    return _work_state(work_id)
                if method == "DELETE":
                    STATE.repo.delete_work(work_id)
                    return {"works": STATE.repo.list_works()}

            if len(parts) == 4 and parts[3] == "settings-lock" and method in {"POST", "PUT"}:
                STATE.repo.set_work_settings_locked(work_id, bool(body.get("locked", False)))
                return _work_state(work_id)

            if len(parts) == 4 and parts[3] == "book-contract" and method in {"POST", "PUT"}:
                STATE.repo.save_book_contract(work_id, body)
                return _work_state(work_id)

            if len(parts) == 4 and parts[3] == "plan-draft" and method == "POST":
                task_id = _task_id(body)
                _start_task(task_id, work_id, kind="plan", title="生成设定草稿", stage="project", input_data=body)
                try:
                    inputs = _clean_inputs(body or _inputs_from_work(STATE.repo.get_work(work_id)))
                    plan = normalize_work_plan(STATE.workflow.planner.generate_work_plan(inputs))
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
                    model=STATE.workflow.client.model_for("planner"),
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
                        STATE.workflow.generate_outline(work_id, should_stop=lambda: STATE.task_cancelled(task_id))
                        return _work_state(work_id)
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
                _start_task(task_id, work_id, kind="chapterOutlines", title="生成章节细纲", stage="chapter_outline", input_data=body)
                try:
                    start = max(1, int(body.get("start_chapter") or 1))
                    count = min(30, max(1, int(body.get("count") or 3)))
                    volume_number = max(1, int(body.get("volume_number") or 1))
                    chapters = STATE.workflow.generate_chapter_outlines(
                        work_id,
                        start_chapter=start,
                        count=count,
                        volume_number=volume_number,
                        should_stop=lambda: STATE.task_cancelled(task_id),
                    )
                    return {"chapters": chapters, **_work_state(work_id)}
                except Exception as exc:
                    _finish_task_error(task_id, exc, work_id=work_id)
                    raise
                finally:
                    if not STATE.task_status(task_id).get("finished_at"):
                        _finish_task(task_id, work_id)

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

            if len(parts) == 5 and parts[3] == "library" and method in {"POST", "PUT"}:
                return _save_library_item(work_id, parts[4], body)

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
                        STATE.repo.delete_chapter(work_id, chapter_number, delete_related=True)
                        return _work_state(work_id)
                if len(parts) == 6 and parts[5] == "outline" and method == "PUT":
                    return _save_chapter_outline(work_id, chapter_number, body)
                if len(parts) == 6 and parts[5] == "generate" and method == "POST":
                    task_id = _task_id(body)
                    chapter_id = _chapter_id_or_none(work_id, chapter_number)
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
                        result = STATE.workflow.generate_chapter(
                            work_id,
                            chapter_number,
                            do_review=mode in {"standard", "polish"},
                            do_revise=mode == "polish",
                            do_memory=bool(body.get("do_memory", False)),
                            should_stop=lambda: STATE.task_cancelled(task_id),
                        )
                        return _chapter_result(work_id, chapter_number, result)
                    except Exception as exc:
                        _finish_task_error(task_id, exc, work_id=work_id, chapter_id=chapter_id)
                        raise
                    finally:
                        if not STATE.task_status(task_id).get("finished_at"):
                            _finish_task(task_id, work_id, chapter_id=chapter_id)
                if len(parts) == 6 and parts[5] == "memory" and method == "POST":
                    task_id = _task_id(body)
                    chapter_id = _chapter_id_or_none(work_id, chapter_number)
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
                        return _generate_memory(
                            work_id,
                            chapter_number,
                            should_stop=lambda: STATE.task_cancelled(task_id),
                        )
                    except Exception as exc:
                        _finish_task_error(task_id, exc, work_id=work_id, chapter_id=chapter_id)
                        raise
                    finally:
                        if not STATE.task_status(task_id).get("finished_at"):
                            _finish_task(task_id, work_id, chapter_id=chapter_id)
                if len(parts) == 6 and parts[5] == "revise" and method == "POST":
                    task_id = _task_id(body)
                    chapter_id = _chapter_id_or_none(work_id, chapter_number)
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
                        return _revise_chapter_with_instruction(
                            work_id,
                            chapter_number,
                            body,
                            should_stop=lambda: STATE.task_cancelled(task_id),
                        )
                    except Exception as exc:
                        _finish_task_error(task_id, exc, work_id=work_id, chapter_id=chapter_id)
                        raise
                    finally:
                        if not STATE.task_status(task_id).get("finished_at"):
                            _finish_task(task_id, work_id, chapter_id=chapter_id)

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
        self.send_response(200)
        self.send_header("Content-Type", content_type)
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
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        try:
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            return

    @staticmethod
    def _parts(path: str) -> list[str]:
        return [part for part in path.strip("/").split("/") if part]


def run(host: str = "127.0.0.1", port: int = 8765, *, open_browser: bool = True) -> None:
    actual_port = _available_port(host, port)
    server = ThreadingHTTPServer((host, actual_port), HiStoryWebHandler)
    url = f"http://{host}:{actual_port}/"
    if open_browser:
        threading.Timer(0.4, lambda: webbrowser.open(url)).start()
    server.serve_forever()


def _available_port(host: str, start: int) -> int:
    for port in range(start, start + 50):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.bind((host, port))
            except OSError:
                continue
            return port
    raise RuntimeError("没有找到可用的本地端口。")


def _task_id(body: dict[str, Any]) -> str:
    return str(body.get("task_id") or "").strip()


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
    STATE.start_task(task_id, kind=kind, title=title)
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


def _finish_task(
    task_id: str,
    work_id: int,
    *,
    status: str = "done",
    error: str = "",
    chapter_id: int | None = None,
) -> None:
    STATE.finish_task(task_id, status=status, error=error)
    task = STATE.task_status(task_id) or {}
    STATE.repo.log_task_run(
        task_id=task_id,
        work_id=work_id,
        chapter_id=chapter_id,
        status=str(task.get("status") or status),
        error=str(task.get("error") or error),
        finished_at=str(task.get("finished_at") or ""),
    )


def _finish_task_error(task_id: str, exc: Exception, *, work_id: int | None = None, chapter_id: int | None = None) -> None:
    status = "cancelled" if str(exc).startswith(TASK_CANCELLED_PREFIX) else "failed"
    if work_id is None:
        STATE.finish_task(task_id, status=status, error=str(exc))
    else:
        _finish_task(task_id, work_id, status=status, error=str(exc), chapter_id=chapter_id)


def _chapter_id_or_none(work_id: int, chapter_number: int) -> int | None:
    try:
        chapter = STATE.repo.get_chapter(work_id, chapter_number)
        return int(chapter["id"])
    except Exception:  # noqa: BLE001
        return None


def _work_state(work_id: int) -> dict[str, Any]:
    work = STATE.repo.get_work(work_id)
    bundle = STATE.repo.get_work_bundle(work_id)
    chapters = STATE.repo.list_chapters(work_id)
    outline = _outline_data(work_id)
    return {
        "work": work,
        "works": STATE.repo.list_works(),
        "chapters": chapters,
        "book_contract": STATE.repo.get_book_contract(work_id),
        "workflow_state": STATE.repo.workflow_state(work_id),
        "project_readable": format_project_readable(bundle),
        "outline": outline,
        "outline_readable": format_outline_readable(outline),
        "characters": STATE.repo.list_characters(work_id),
        "world_rules": STATE.repo.list_world_rules(work_id),
        "plot_threads": STATE.repo.list_plot_threads(work_id),
        "timeline": STATE.repo.list_timeline(work_id, limit=50),
        "historical_profile": STATE.repo.get_historical_profile(work_id),
        "historical_facts": STATE.repo.list_historical_facts(work_id),
        "chapter_notes": STATE.repo.list_chapter_notes(work_id),
        "sync_events": STATE.repo.list_sync_events(work_id),
        "agent_runs": STATE.repo.list_agent_runs(work_id, limit=120),
        "task_runs": STATE.repo.list_task_runs(work_id, limit=120),
        "export_dir": str(_current_export_dir(work_id)),
        "default_export_dir": str(STATE.repo.export_dir(work_id)),
        "custom_export_dir": work_id in STATE.custom_export_dirs,
    }


def _chapter_state(work_id: int, chapter_number: int) -> dict[str, Any]:
    chapter = STATE.repo.get_chapter(work_id, chapter_number)
    memory = parse_json_object(chapter.get("memory_json") or "{}", default={}) or {}
    context = {}
    context_readable = ""
    context_error = ""
    try:
        context = STATE.workflow.build_chapter_context(work_id, chapter_number)
        context_readable = format_context_readable(context)
    except Exception as exc:  # noqa: BLE001
        context_error = str(exc)
    return {
        "chapter": chapter,
        "context": context,
        "context_readable": context_readable,
        "context_error": context_error,
        "memory_readable": format_memory_readable(memory),
        "outline_readable": format_outline_readable({"chapters": [chapter]}),
    }


def _chapter_result(work_id: int, chapter_number: int, result: dict[str, Any]) -> dict[str, Any]:
    return {
        **_chapter_state(work_id, chapter_number),
        "draft": result.get("draft", ""),
        "final_text": result.get("final_text", ""),
        "review": result.get("review"),
        "review_readable": format_review_readable(result.get("review")),
        "memory": result.get("memory"),
        "memory_readable": format_memory_readable(result.get("memory")),
        "work_state": _work_state(work_id),
    }


def _save_chapter_text(work_id: int, chapter_number: int, body: dict[str, Any]) -> dict[str, Any]:
    chapter = STATE.repo.get_chapter(work_id, chapter_number)
    title = str(body.get("title") or chapter.get("title") or f"第{chapter_number}章").strip()
    text = str(body.get("final_text") or "")
    if chapter.get("final_text"):
        STATE.repo.add_version(work_id, chapter["id"], "web_manual_before_save", chapter.get("final_text") or "")
    STATE.repo.save_final_after_manual_edit(
        work_id,
        chapter["id"],
        text,
        title=title,
        ending_hook=chapter.get("ending_hook") or "",
        handoff=chapter.get("handoff") or "",
        memory_json=chapter.get("memory_json") or "",
        invalidate_memory=bool(body.get("invalidate_memory", False)),
    )
    return _chapter_state(work_id, chapter_number)


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
    )
    return _chapter_state(work_id, chapter_number)


def _generate_memory(
    work_id: int,
    chapter_number: int,
    *,
    should_stop: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    chapter = STATE.repo.get_chapter(work_id, chapter_number)
    final_text = str(chapter.get("final_text") or "").strip()
    if not final_text:
        raise ValueError("当前章节没有已保存最终稿，无法生成记忆。")
    context = STATE.workflow.build_chapter_context(work_id, chapter_number)
    memory = STATE.workflow.memory.make_memory_card(context, final_text)
    if should_stop and should_stop():
        raise RuntimeError("任务已停止：章节记忆已返回，但未入库。")
    memory = STATE.workflow.normalize_output_names(work_id, memory)
    STATE.repo.apply_memory_card(
        work_id=work_id,
        chapter_id=chapter["id"],
        chapter_number=chapter_number,
        memory=memory,
    )
    STATE.repo.log_agent_run(
        work_id=work_id,
        chapter_id=chapter["id"],
        agent_name="memory",
        model=STATE.workflow.client.model_for("memory"),
        prompt_name="memory_prompt.md",
        input_preview=json_dumps({"context": context, "final_text": final_text[:3000]}),
        output=json_dumps(memory),
    )
    return {**_chapter_state(work_id, chapter_number), "memory": memory, "memory_readable": format_memory_readable(memory)}


def _revise_chapter_with_instruction(
    work_id: int,
    chapter_number: int,
    body: dict[str, Any],
    *,
    should_stop: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    instruction = str(body.get("instruction") or "").strip()
    current_text = str(body.get("current_text") or "").strip()
    if not instruction:
        raise ValueError("请先填写修改意见。")
    if not current_text:
        raise ValueError("当前正文为空，无法按意见修订。")
    chapter = STATE.repo.get_chapter(work_id, chapter_number)
    context = STATE.workflow.build_chapter_context(work_id, chapter_number)
    revised = STATE.workflow.reviser.revise_with_instruction(context, current_text, instruction)
    if should_stop and should_stop():
        raise RuntimeError("任务已停止：修订稿已返回，但未写入界面。")
    revised = STATE.workflow.normalize_output_names(work_id, revised)
    STATE.repo.add_version(work_id, chapter["id"], "web_user_instruction_before_revise", current_text)
    STATE.repo.log_agent_run(
        work_id=work_id,
        chapter_id=chapter["id"],
        agent_name="reviser",
        model=STATE.workflow.client.model_for("reviser"),
        prompt_name="reviser_prompt.md",
        input_preview=json_dumps({"context": context, "instruction": instruction, "current_text": current_text[:3000]}),
        output=revised,
    )
    return {**_chapter_state(work_id, chapter_number), "revised_text": revised}


def _outline_data(work_id: int) -> dict[str, Any]:
    work = STATE.repo.get_work(work_id)
    return {
        "full_outline": work.get("full_outline") or "",
        "volume_outline": parse_json_object(work.get("volume_outline") or "[]", default=[]),
        "chapters": STATE.repo.list_chapter_outlines(work_id),
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
    return _work_state(work_id)


def _export_work(work_id: int, body: dict[str, Any]) -> dict[str, Any]:
    fmt = str(body.get("format") or "txt").lower()
    scope = str(body.get("scope") or "book")
    include_draft = bool(body.get("include_draft", False))
    work = STATE.repo.get_work(work_id)
    output_dir = _current_export_dir(work_id)
    custom = work_id in STATE.custom_export_dirs
    if scope == "chapter":
        chapter_number = max(1, int(body.get("chapter_number") or 1))
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
        output_path = chapter_range_export_path(work, start, end, fmt, output_dir.parent if not custom else None)
        if custom:
            output_path = output_dir / output_path.name
        path = (
            export_range_txt(STATE.repo, work_id, start, end, output_path, include_draft=include_draft)
            if fmt == "txt"
            else export_range_docx(STATE.repo, work_id, start, end, output_path, include_draft=include_draft)
        )
    else:
        output_path = book_export_path(work, fmt, output_dir.parent if not custom else None)
        if custom:
            output_path = output_dir / output_path.name
        path = (
            export_txt(STATE.repo, work_id, output_path, include_draft=include_draft)
            if fmt == "txt"
            else export_docx(STATE.repo, work_id, output_path, include_draft=include_draft)
        )
    return {"path": str(path)}


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
    else:
        raise ValueError("该资料类型暂不支持保存。")
    return {"id": item_id, **_library_state(work_id)}


def _delete_library_item(work_id: int, kind: str, item_id: int) -> dict[str, Any]:
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
    else:
        raise ValueError("该资料类型暂不支持删除。")
    return _library_state(work_id)


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
