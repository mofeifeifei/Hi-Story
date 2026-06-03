from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import Any

from app.database.repository import Repository
from app.exporters.export_docx import export_chapter_docx, export_docx
from app.exporters.export_txt import export_chapter_txt, export_txt
from app.services.ai_client import AIClientError
from app.utils.config import CONFIG_PATH, load_config, parse_bool, save_config
from app.utils.json_parser import json_dumps
from app.web.config_api import sanitize_config_update
from app.workflow import NovelWorkflow


def print_json(data: Any) -> None:
    print(json_dumps(data))


def build_work_inputs(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "title": getattr(args, "title", ""),
        "idea": args.idea,
        "genre": args.genre,
        "platform": args.platform,
        "target_words": args.target_words,
        "style": args.style,
        "forbidden_tropes": args.forbidden_tropes,
        "protagonist_preference": args.protagonist_preference,
        "reader_profile": args.reader_profile,
        "locked_facts": getattr(args, "locked_facts", ""),
        "writing_controls": getattr(args, "writing_controls", ""),
    }


def add_work_input_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--title", default="", help="文章名称")
    parser.add_argument("--idea", required=True, help="一句话创意")
    parser.add_argument("--genre", default="", help="小说题材")
    parser.add_argument("--platform", default="", help="目标平台")
    parser.add_argument("--target-words", type=int, default=0, help="目标字数")
    parser.add_argument("--style", default="", help="写作风格")
    parser.add_argument("--forbidden-tropes", default="", help="禁用套路")
    parser.add_argument("--protagonist-preference", default="", help="主角偏好")
    parser.add_argument("--reader-profile", default="", help="读者定位")
    parser.add_argument("--locked-facts", default="", help="锁定设定")
    parser.add_argument("--writing-controls", default="", help="其他写作控制")


def command_init_db(_: argparse.Namespace) -> None:
    Repository().init()
    print("数据库已初始化。")


def command_set_config(args: argparse.Namespace) -> None:
    config = load_config()
    updates: dict[str, Any] = {}
    if args.model_provider is not None:
        updates["provider"] = args.model_provider
        updates["model_provider"] = args.model_provider
    if args.api_key is not None:
        updates["api_key"] = args.api_key
    if args.base_url is not None:
        updates["base_url"] = args.base_url
    if args.wire_api is not None:
        updates["wire_api"] = args.wire_api
    if args.default_model is not None:
        updates["default_model"] = args.default_model
    if args.review_model is not None:
        updates["review_model"] = args.review_model
    if args.reasoning_effort is not None:
        updates["model_reasoning_effort"] = args.reasoning_effort
    if args.disable_response_storage is not None:
        updates["disable_response_storage"] = parse_bool(args.disable_response_storage)
    if args.context_window is not None:
        updates["model_context_window"] = args.context_window
    if args.auto_compact_token_limit is not None:
        updates["model_auto_compact_token_limit"] = args.auto_compact_token_limit
    if args.temperature is not None:
        updates["temperature"] = args.temperature
    if args.timeout is not None:
        updates["timeout"] = args.timeout
    if args.max_output_tokens is not None:
        updates["max_output_tokens"] = args.max_output_tokens
    if args.mock_mode is not None:
        updates["mock_mode"] = parse_bool(args.mock_mode)

    agent_updates = {
        "planner": args.planner_model,
        "writer": args.writer_model,
        "reviewer": args.reviewer_model,
        "reviser": args.reviser_model,
        "memory": args.memory_model,
    }
    agent_models = dict(config.get("agent_models", {}))
    for name, model in agent_updates.items():
        if model is not None:
            agent_models[name] = model
    if agent_models != config.get("agent_models", {}):
        updates["agent_models"] = agent_models

    config = sanitize_config_update(config, updates)
    save_config(config)
    print(f"配置已保存：{CONFIG_PATH}")


def command_create_work(args: argparse.Namespace) -> None:
    workflow = NovelWorkflow()
    work_id, plan = workflow.create_work(build_work_inputs(args))
    print(f"文章已创建，work_id={work_id}")
    print_json(plan)


def command_list_works(_: argparse.Namespace) -> None:
    print_json(Repository().list_works())


def command_show_work(args: argparse.Namespace) -> None:
    print_json(Repository().get_work_bundle(args.work_id))


def command_generate_outline(args: argparse.Namespace) -> None:
    outline = NovelWorkflow().generate_outline(args.work_id)
    print("大纲已保存。")
    print_json(outline)


def command_generate_chapter_outlines(args: argparse.Namespace) -> None:
    chapters = NovelWorkflow().generate_chapter_outlines(
        args.work_id,
        start_chapter=args.start,
        count=args.count,
    )
    print(f"已保存 {len(chapters)} 章细纲。")
    print_json(chapters)


def command_list_chapters(args: argparse.Namespace) -> None:
    print_json(Repository().list_chapters(args.work_id))


def command_show_chapter(args: argparse.Namespace) -> None:
    print_json(Repository().get_chapter(args.work_id, args.chapter))


def command_generate_chapter(args: argparse.Namespace) -> None:
    result = NovelWorkflow().generate_chapter(
        args.work_id,
        args.chapter,
        do_review=not args.skip_review,
        do_revise=not args.skip_revise,
        do_memory=(not args.skip_memory) and args.apply_memory,
    )
    chapter = result["chapter"]
    print(f"第 {chapter['chapter_number']} 章已生成：{chapter.get('title')}")
    if result.get("review"):
        review = result["review"]
        print(
            "审稿评分："
            f"连贯 {review.get('continuity_score')} / "
            f"人设 {review.get('character_score')} / "
            f"情绪 {review.get('emotion_score')} / "
            f"节奏 {review.get('rhythm_score')} / "
            f"伏笔 {review.get('foreshadow_score')}"
        )
    if result.get("memory"):
        print(f"记忆卡摘要：{result['memory'].get('summary', '')}")


def command_generate_chapters(args: argparse.Namespace) -> None:
    results = NovelWorkflow().generate_chapters(
        args.work_id,
        start_chapter=args.start,
        count=args.count,
        do_review=not args.skip_review,
        do_revise=not args.skip_revise,
        do_memory=(not args.skip_memory) and args.apply_memory,
    )
    last = results[-1]["chapter"] if results else None
    if last:
        print(f"连续生成完成：第 {args.start} 章到第 {last['chapter_number']} 章。")
    else:
        print("没有生成章节。")


def command_export_txt(args: argparse.Namespace) -> None:
    path = export_txt(Repository(), args.work_id, Path(args.output) if args.output else None)
    print(f"TXT 已导出：{path}")


def command_export_docx(args: argparse.Namespace) -> None:
    path = export_docx(Repository(), args.work_id, Path(args.output) if args.output else None)
    print(f"DOCX 已导出：{path}")


def command_export_chapter_txt(args: argparse.Namespace) -> None:
    path = export_chapter_txt(
        Repository(),
        args.work_id,
        args.chapter,
        Path(args.output) if args.output else None,
    )
    print(f"章节 TXT 已导出：{path}")


def command_export_chapter_docx(args: argparse.Namespace) -> None:
    path = export_chapter_docx(
        Repository(),
        args.work_id,
        args.chapter,
        Path(args.output) if args.output else None,
    )
    print(f"章节 DOCX 已导出：{path}")


def command_demo(args: argparse.Namespace) -> None:
    workflow = NovelWorkflow()
    workflow.repo.init()
    work_id, plan = workflow.create_work(build_work_inputs(args))
    outline = workflow.generate_outline(work_id)
    chapters = workflow.generate_chapter_outlines(work_id, start_chapter=1, count=1)
    result = workflow.generate_chapter(work_id, 1)
    output = export_txt(workflow.repo, work_id)

    print(f"Demo 跑通，work_id={work_id}")
    print(f"候选书名：{', '.join(plan.get('title_candidates', []))}")
    print(f"全书大纲：{outline.get('full_outline', '')}")
    print(f"第 1 章细纲：{chapters[0].get('outline', '') if chapters else ''}")
    print(f"第 1 章审稿：{json_dumps(result.get('review', {}))}")
    print(f"TXT 已导出：{output}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Hi Story - 命令行工具")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_db = subparsers.add_parser("init-db", help="初始化 SQLite 数据库")
    init_db.set_defaults(func=command_init_db)

    set_config = subparsers.add_parser("set-config", help="设置 API 和模型配置")
    set_config.add_argument("--model-provider")
    set_config.add_argument("--api-key")
    set_config.add_argument("--base-url")
    set_config.add_argument("--wire-api", choices=["responses", "chat_completions"])
    set_config.add_argument("--default-model")
    set_config.add_argument("--review-model")
    set_config.add_argument("--reasoning-effort")
    set_config.add_argument("--disable-response-storage", help="true/false")
    set_config.add_argument("--context-window", type=int)
    set_config.add_argument("--auto-compact-token-limit", type=int)
    set_config.add_argument("--temperature", type=float)
    set_config.add_argument("--timeout", type=int)
    set_config.add_argument("--max-output-tokens", type=int)
    set_config.add_argument("--mock-mode", help="true/false")
    set_config.add_argument("--planner-model")
    set_config.add_argument("--writer-model")
    set_config.add_argument("--reviewer-model")
    set_config.add_argument("--reviser-model")
    set_config.add_argument("--memory-model")
    set_config.set_defaults(func=command_set_config)

    create_work = subparsers.add_parser("create-work", help="创建文章并生成基础设定")
    add_work_input_args(create_work)
    create_work.set_defaults(func=command_create_work)

    list_works = subparsers.add_parser("list-works", help="列出文章")
    list_works.set_defaults(func=command_list_works)

    show_work = subparsers.add_parser("show-work", help="查看文章资料包")
    show_work.add_argument("--work-id", type=int, required=True)
    show_work.set_defaults(func=command_show_work)

    outline = subparsers.add_parser("generate-outline", help="生成全书大纲和分卷大纲")
    outline.add_argument("--work-id", type=int, required=True)
    outline.set_defaults(func=command_generate_outline)

    chapter_outlines = subparsers.add_parser("generate-chapter-outlines", help="生成章节细纲")
    chapter_outlines.add_argument("--work-id", type=int, required=True)
    chapter_outlines.add_argument("--start", type=int, default=1)
    chapter_outlines.add_argument("--count", type=int, default=30)
    chapter_outlines.set_defaults(func=command_generate_chapter_outlines)

    list_chapters = subparsers.add_parser("list-chapters", help="列出章节")
    list_chapters.add_argument("--work-id", type=int, required=True)
    list_chapters.set_defaults(func=command_list_chapters)

    show_chapter = subparsers.add_parser("show-chapter", help="查看章节")
    show_chapter.add_argument("--work-id", type=int, required=True)
    show_chapter.add_argument("--chapter", type=int, required=True)
    show_chapter.set_defaults(func=command_show_chapter)

    generate_chapter = subparsers.add_parser("generate-chapter", help="生成单章正文")
    generate_chapter.add_argument("--work-id", type=int, required=True)
    generate_chapter.add_argument("--chapter", type=int, required=True)
    add_generation_flags(generate_chapter)
    generate_chapter.add_argument("--apply-memory", action="store_true", help="生成后自动将记忆卡入库")
    generate_chapter.set_defaults(func=command_generate_chapter)

    generate_chapters = subparsers.add_parser("generate-chapters", help="连续生成多章正文")
    generate_chapters.add_argument("--work-id", type=int, required=True)
    generate_chapters.add_argument("--start", type=int, default=1)
    generate_chapters.add_argument("--count", type=int, required=True)
    add_generation_flags(generate_chapters)
    generate_chapters.add_argument("--apply-memory", action="store_true", help="连续生成时自动将记忆卡入库")
    generate_chapters.set_defaults(func=command_generate_chapters)

    txt = subparsers.add_parser("export-txt", help="导出 TXT")
    txt.add_argument("--work-id", type=int, required=True)
    txt.add_argument("--output")
    txt.set_defaults(func=command_export_txt)

    docx = subparsers.add_parser("export-docx", help="导出 DOCX")
    docx.add_argument("--work-id", type=int, required=True)
    docx.add_argument("--output")
    docx.set_defaults(func=command_export_docx)

    chapter_txt = subparsers.add_parser("export-chapter-txt", help="导出当前章节 TXT")
    chapter_txt.add_argument("--work-id", type=int, required=True)
    chapter_txt.add_argument("--chapter", type=int, required=True)
    chapter_txt.add_argument("--output")
    chapter_txt.set_defaults(func=command_export_chapter_txt)

    chapter_docx = subparsers.add_parser("export-chapter-docx", help="导出当前章节 DOCX")
    chapter_docx.add_argument("--work-id", type=int, required=True)
    chapter_docx.add_argument("--chapter", type=int, required=True)
    chapter_docx.add_argument("--output")
    chapter_docx.set_defaults(func=command_export_chapter_docx)

    demo = subparsers.add_parser("demo", help="用 mock 模式跑通完整 MVP")
    add_work_input_args(demo)
    demo.set_defaults(func=command_demo)

    return parser


def add_generation_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--skip-review", action="store_true", help="跳过审稿")
    parser.add_argument("--skip-revise", action="store_true", help="跳过修订")
    parser.add_argument("--skip-memory", action="store_true", help="跳过记忆卡")


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        args.func(args)
    except (AIClientError, RuntimeError, ValueError) as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
