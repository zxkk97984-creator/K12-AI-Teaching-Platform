from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_selected_config_overrides_shell_and_drives_all_qa_paths(tmp_path):
    config = tmp_path / "agent.env"
    storage = tmp_path / "storage"
    qa = tmp_path / "qa"
    config.write_text(
        f"QA_WEB_PORT=15202\nQA_API_PORT=18102\nQA_ISOLATED=1\n"
        f"K12_RUNTIME_STORAGE_ROOT={storage}\nK12_RUNTIME_STATE_DIR={tmp_path}/state\n"
        f"QA_RUNTIME_DIR={qa}\n"
    )
    config.chmod(0o600)
    env = os.environ | {
        "K12_RUNTIME_ENV_FILE": str(config),
        "QA_WEB_PORT": "15206",
        "QA_API_PORT": "18106",
        "QA_RUNTIME_DIR": "/tmp/wrong-agent",
    }
    result = subprocess.run(
        [
            "bash",
            "-c",
            ". scripts/load-runtime-env.sh && . scripts/qa-runtime.sh && "
            "python3 -c 'import json,os; print(json.dumps({k:os.environ[k] for k in "
            '["QA_WEB_URL","QA_API_URL","RESOURCE_STORAGE_ROOT","ALLOWED_ORIGINS","TMPDIR"]}))\'',
        ],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    actual = json.loads(result.stdout)
    assert actual == {
        "QA_WEB_URL": "http://127.0.0.1:15202",
        "QA_API_URL": "http://127.0.0.1:18102",
        "ALLOWED_ORIGINS": "http://127.0.0.1:15202,http://localhost:15202",
        "RESOURCE_STORAGE_ROOT": str(storage / "resources"),
        "TMPDIR": str(qa / "tmp"),
    }


def test_legacy_qa_defaults_are_loopback_and_keep_cache_storage(tmp_path):
    env = {k: v for k, v in os.environ.items() if not k.startswith("QA_")}
    env["XDG_CACHE_HOME"] = str(tmp_path)
    result = subprocess.run(
        [
            "bash",
            "-c",
            '. scripts/qa-runtime.sh && printf "%s\\n" '
            '"$QA_WEB_URL" "$QA_API_URL" "$RESOURCE_STORAGE_ROOT"',
        ],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout.splitlines() == [
        "http://127.0.0.1:15174",
        "http://127.0.0.1:18082",
        str(tmp_path / "k12/learning-browser-runtime/resources"),
    ]
