"""Exercise the actual workflow shell block with local upstream Git history."""

import os
import shlex
import subprocess
from pathlib import Path

import pytest
import yaml


@pytest.mark.parametrize(
    "csv_changed,date_changed",
    [(True, False), (False, True), (True, True), (False, False)],
)
def test_sync_detects_staged_csv_and_readme_updates(
    tmp_path, csv_changed, date_changed
):
    upstream = tmp_path / "upstream"
    upstream.mkdir()
    local = tmp_path / "local"
    env = dict(
        os.environ,
        GIT_AUTHOR_DATE="2026-10-09T12:00:00Z",
        GIT_COMMITTER_DATE="2026-10-09T12:00:00Z",
        GIT_AUTHOR_NAME="Regression",
        GIT_AUTHOR_EMAIL="regression@example.invalid",
        GIT_COMMITTER_NAME="Regression",
        GIT_COMMITTER_EMAIL="regression@example.invalid",
    )

    def git(directory, *args):
        return subprocess.run(
            ["git", *args],
            cwd=directory,
            env=env,
            check=True,
            capture_output=True,
            text=True,
        ).stdout

    git(upstream, "init", "-q", "-b", "main")
    (upstream / "retraction_watch.csv").write_text("old\n")
    readme = (
        "This repository contains the latest mirrored snapshot of "
        "[Crossref's Retraction Watch dataset](https://gitlab.com/crossref/retraction-watch-data), "
        "generated on **2026-10-09**.\n"
    )
    (upstream / "README.md").write_text(readme)
    git(upstream, "add", ".")
    git(upstream, "commit", "-qm", "initial")
    git(tmp_path, "clone", "-q", str(upstream), str(local))
    if csv_changed:
        (upstream / "retraction_watch.csv").write_text("updated\n")
    if date_changed:
        env.update(
            GIT_AUTHOR_DATE="2026-10-10T12:00:00Z",
            GIT_COMMITTER_DATE="2026-10-10T12:00:00Z",
        )
    if csv_changed or date_changed:
        git(upstream, "add", ".")
        git(upstream, "commit", "--allow-empty", "-qm", "upstream update")
    workflow = yaml.safe_load(
        (Path(__file__).parents[1] / ".github/workflows/sync-gitlab.yml").read_text()
    )
    script = next(
        s["run"] for s in workflow["jobs"]["sync"]["steps"] if s.get("id") == "sync"
    )
    script = script.replace(
        "https://gitlab.com/crossref/retraction-watch-data.git",
        shlex.quote(str(upstream)),
    )
    output = tmp_path / "github-output"
    env["GITHUB_OUTPUT"] = str(output)
    subprocess.run(
        ["bash", "-e", "-o", "pipefail", "-c", script],
        cwd=local,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    changed = csv_changed or date_changed
    assert output.read_text().strip() == f"data_changed={str(changed).lower()}"
    if csv_changed:
        assert git(local, "show", "HEAD:retraction_watch.csv") == "updated\n"
    expected_date = "2026-10-10" if date_changed else "2026-10-09"
    assert (local / "README.md").read_text() == readme.replace("2026-10-09", expected_date)
    assert not git(local, "status", "--porcelain")
