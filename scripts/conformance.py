"""適合テストを実行する。相手の実装が、プロファイルの決まりどおりに答えるかを確かめる。

自分の実装を試す（相手は A2A のエージェントとして待ち受けていること）:
    uv run python scripts\\conformance.py --target http://127.0.0.1:8027
この見本の実装で試す（待ち受けを自動で起動し、終わったら止める）:
    uv run python scripts\\conformance.py --self-test

終了コード：0＝対象のテストがすべて合格、1＝不合格あり、2＝相手につながらない など。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from trade_agent_profile import i18n  # noqa: E402
from trade_agent_profile.a2a_agent import card_summary, fetch_card, free_port, serve  # noqa: E402
from trade_agent_profile.cli import setup_stdio  # noqa: E402
from trade_agent_profile.conformance import CaseResult, load_cases, run_conformance  # noqa: E402
from trade_agent_profile.reference import broker_app, quiet_logs  # noqa: E402

EXIT_OK, EXIT_FAILED, EXIT_UNREACHABLE = 0, 1, 2


def _both(langs: tuple[str, ...], key: str, **params: object) -> str:
    return " / ".join(i18n.catalog(lang)["conformance"][key].format(**params) for lang in langs)


def _problem_text(lang: str, key: str, params: dict) -> str:
    cat = i18n.catalog(lang)["conformance"]
    shown = dict(params)
    if key == "p_reply_place":
        for name in ("actual", "expected"):
            shown[name] = cat["place"].get(shown[name], shown[name])
    return cat["problems"][key].format(**shown)


def _report(
    url: str, name: str, results: list[CaseResult], langs: tuple[str, ...], quiet: bool = False
) -> None:
    """結果を人が読む形で出す。quiet のときは、不合格のテストと、まとめだけを出す。"""
    if not quiet:
        for lang in langs:
            print(i18n.catalog(lang)["ui"]["notice"])
        print()
        print(_both(langs, "title"))
        print(_both(langs, "target", url=url, name=name))
        print()
    for result in results:
        if quiet and not result.problems:
            continue
        key = "skip" if result.skipped else "pass" if result.passed else "fail"
        title = " / ".join(result.title[lang] for lang in langs)
        print(f"[{_both(langs, key)}] {result.case_id} {title}")
        if result.skipped:
            print(f"    {_both(langs, 'skip_reason')}")
        for problem_key, params in result.problems:
            for lang in langs:
                print(f"    {_problem_text(lang, problem_key, params)}")
    if not quiet:
        print()
    counts = _counts(results)
    for lang in langs:
        cat = i18n.catalog(lang)["conformance"]
        print(cat["summary"].format(**counts))
        print(cat[_verdict(counts)])


def _counts(results: list[CaseResult]) -> dict[str, int]:
    return {
        "total": len(results),
        "passed": sum(1 for result in results if result.passed),
        "failed": sum(1 for result in results if result.problems),
        "skipped": sum(1 for result in results if result.skipped),
    }


def _verdict(counts: dict[str, int]) -> str:
    if counts["failed"]:
        return "some_failed"
    return "all_passed" if counts["passed"] else "nothing_ran"


async def _run(url: str, args: argparse.Namespace, langs: tuple[str, ...]) -> int:
    try:
        card = await fetch_card(url)
    except Exception as error:  # つながらない・AgentCard がない、など
        detail = f"{type(error).__name__}: {error}"[:200]
        print(_both(langs, "no_card", detail=detail), file=sys.stderr)
        return EXIT_UNREACHABLE
    accepts = args.accepts.split(",") if args.accepts is not None else None
    results = await run_conformance(card, load_cases(args.cases), accepts=accepts)
    counts = _counts(results)
    if args.as_json:
        payload = {
            "target": url,
            "agent": card_summary(card),
            "summary": counts,
            "results": [
                {
                    "id": result.case_id,
                    "title": result.title,
                    "status": "skip" if result.skipped else "pass" if result.passed else "fail",
                    "problems": [
                        {lang: _problem_text(lang, key, params) for lang in i18n.LANGS}
                        for key, params in result.problems
                    ],
                }
                for result in results
            ],
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        _report(url, card.name, results, langs, args.quiet)
    return EXIT_OK if _verdict(counts) == "all_passed" else EXIT_FAILED


def main() -> int:
    setup_stdio()
    quiet_logs()
    parser = argparse.ArgumentParser(description="適合テスト / Conformance test")
    where = parser.add_mutually_exclusive_group(required=True)
    where.add_argument("--target", metavar="URL", help="試す相手の URL / URL of the agent to test")
    where.add_argument(
        "--self-test",
        action="store_true",
        help="この見本の実装を自動で起動して試す / start the reference agent and test it",
    )
    parser.add_argument(
        "--cases",
        default=str(ROOT / "conformance" / "cases"),
        help="テストのフォルダ / folder of test cases",
    )
    parser.add_argument(
        "--accepts",
        metavar="TYPES",
        help=(
            "相手が引き受ける種類をカンマ区切りで指定（指定しなければ AgentCard から読む） / "
            "comma-separated message types the target accepts (default: read from the AgentCard)"
        ),
    )
    parser.add_argument("--lang", choices=("both", "ja", "en"), default="both")
    parser.add_argument("--json", dest="as_json", action="store_true")
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="不合格のテストと、まとめだけを出す / print only failures and the summary",
    )
    args = parser.parse_args()
    langs = i18n.LANGS if args.lang == "both" else (args.lang,)

    if args.self_test:
        port = free_port()
        app, _ = broker_app(port)
        with serve(app, port) as url:
            return asyncio.run(_run(url, args, langs))
    return asyncio.run(_run(args.target.rstrip("/"), args, langs))


if __name__ == "__main__":
    raise SystemExit(main())
