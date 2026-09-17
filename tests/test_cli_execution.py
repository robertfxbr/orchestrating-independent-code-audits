import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts import audit_bridge as bridge


def test_module_cli_requires_arguments():
    result = subprocess.run([sys.executable, '-B', '-m', 'scripts.audit_bridge'],
                            capture_output=True, text=True)
    assert result.returncode == 2
    assert 'usage:' in result.stderr


def test_cli_package_materializes_evidence(git_repo, tmp_path, capsys):
    spec = git_repo.write_file('spec.md', 'contract\n')
    plan = git_repo.write_file('plan.md', 'plan\n')
    git_repo.commit_all('base')
    head = git_repo.head()
    code = bridge.main(['package', '--phase', 'test', '--task-id', 'cli',
                        '--base-sha', head, '--head-sha', head,
                        '--spec-path', str(spec), '--plan-path', str(plan),
                        '--runtime-root', str(tmp_path / 'runtime')])
    assert code == 0
    output = json.loads(capsys.readouterr().out.splitlines()[-1])
    assert output['status'] == 'PACKAGE_CREATED'
    assert json.loads((Path(output['attempt_dir']) / 'manifest.json').read_text())['head_sha'] == head


@pytest.mark.parametrize('verdict_name,expected', [('TASK_APPROVED', 'TASK_APPROVED'),
                                                 ('FIX_REQUIRED', 'FIX_REQUIRED')])
def test_audit_routes_wrapped_agy_result_and_saves_provenance(
    verdict_name, expected, tmp_path, schema_path, bridge_config, fake_agy_runner
):
    package = tmp_path / 'package'
    package.mkdir()
    (package / 'manifest.json').write_text(json.dumps({'head_sha': 'a' * 40}))
    approved = verdict_name == 'TASK_APPROVED'
    verdict = dict(verdict=verdict_name, spec_compliance='APPROVED' if approved else 'CHANGES_REQUIRED',
                   code_quality='APPROVED' if approved else 'CHANGES_REQUIRED',
                   test_evidence='PASS' if approved else 'FAIL', architecture_stop=False,
                   findings=[], confidence='MEDIUM')
    fake_agy_runner.output = json.dumps(dict(status='SUCCESS', structured_output=verdict))
    result = bridge.run_audit_with_retries(bridge_config.with_agy_runner(fake_agy_runner),
                                           package, 'task', schema_path)
    assert result.status == expected
    assert result.head_sha == 'a' * 40
    assert (package / 'agy-raw-output.txt').read_text() == fake_agy_runner.output
    assert json.loads((package / 'auditor-verdict.json').read_text())['verdict'] == verdict_name


def test_agy_command_uses_installed_model_and_plan_mode(tmp_path, bridge_config, fake_agy_runner):
    bridge.run_agy_audit(bridge_config.with_agy_runner(fake_agy_runner), tmp_path, 'task')
    args = fake_agy_runner.last_command
    assert args[args.index('--model') + 1] == 'Gemini 3.8 Flash (Medium)'
    assert args[args.index('--mode') + 1] == 'plan'


def test_cli_audit_fix_required_never_publishes(git_repo, tmp_path, monkeypatch, capsys):
    spec = git_repo.write_file('spec.md', 'contract\n')
    plan = git_repo.write_file('plan.md', 'plan\n')
    git_repo.commit_all('audited')
    head = git_repo.head()
    raw = json.dumps(dict(status='SUCCESS', structured_output=dict(
        verdict='FIX_REQUIRED', spec_compliance='CHANGES_REQUIRED',
        code_quality='CHANGES_REQUIRED', test_evidence='FAIL',
        architecture_stop=False, findings=[], confidence='HIGH')))
    claude_raw = json.dumps(dict(type='result', subtype='success', is_error=False,
                                 structured_output=json.loads(raw)['structured_output']))
    monkeypatch.setattr(bridge, '_invoke_auditor', lambda config, command, cwd: claude_raw)
    monkeypatch.setattr(bridge, 'run_check', lambda command: (0, '{"loggedIn": true}'))
    monkeypatch.setattr(bridge.shutil, 'which', lambda name: '/bin/' + name)
    def forbidden(*args, **kwargs):
        pytest.fail('publication is forbidden after FIX_REQUIRED')
    monkeypatch.setattr(bridge, 'finalize_after_approval', forbidden)
    body = tmp_path / 'body.md'
    body.write_text('body')
    bindings = tmp_path / 'bindings.yaml'
    bindings.write_text(Path('audit-orchestration.example.yaml').read_text(encoding='utf-8'), encoding='utf-8')
    code = bridge.main(['finalize', '--phase', 'final', '--task-id', 'cli',
                        '--base-sha', head, '--head-sha', head,
                        '--spec-path', str(spec), '--plan-path', str(plan),
                        '--runtime-root', str(tmp_path / 'runtime'), '--bindings', str(bindings),
                        '--pr-title', 'title', '--pr-body-file', str(body)])
    assert code == 1
    assert json.loads(capsys.readouterr().out.splitlines()[-1])['status'] == 'FIX_REQUIRED'
