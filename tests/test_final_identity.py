import json

import pytest

from scripts.audit_bridge import finalize_after_approval, _run_git


@pytest.mark.parametrize('mutation', ['head', 'dirty', 'branch', 'missing_manifest', 'tree'])
def test_final_gate_rejects_unapproved_git_state(
    mutation, git_repo, tmp_path, bridge_config, fake_git_runner, fake_gh_runner
):
    git_repo.write_file('source.py', 'value = 1\n')
    git_repo.commit_all('audited')
    _run_git(git_repo.path, 'checkout', '-b', 'feature/audit-bridge')
    package = tmp_path / 'package'
    package.mkdir()
    manifest = dict(worktree=str(git_repo.path), head_sha=git_repo.head(),
                    tree_sha=_run_git(git_repo.path, 'rev-parse', 'HEAD^{tree}').strip(),
                    branch='feature/audit-bridge')
    (package / 'manifest.json').write_text(json.dumps(manifest))
    (package / 'auditor-verdict.json').write_text(json.dumps(dict(
        verdict='TASK_APPROVED', spec_compliance='APPROVED', code_quality='APPROVED',
        test_evidence='PASS', architecture_stop=False, findings=[], confidence='HIGH',
        prompt_kind='final')))
    if mutation in ('head', 'dirty'):
        git_repo.write_file('source.py', 'value = 2\n')
        if mutation == 'head':
            git_repo.commit_all('not audited')
    elif mutation == 'branch':
        _run_git(git_repo.path, 'checkout', '-b', 'feature/other')
    elif mutation == 'missing_manifest':
        (package / 'manifest.json').unlink()
    elif mutation == 'tree':
        manifest['tree_sha'] = '0' * 40
        (package / 'manifest.json').write_text(json.dumps(manifest))
    result = finalize_after_approval(
        bridge_config.with_git_runner(fake_git_runner).with_gh_runner(fake_gh_runner),
        package, 'origin', 'feature/audit-bridge', 'title', 'body')
    assert result.status == 'REPOSITORY_SAFETY_STOP'
    assert fake_git_runner.commands == []
    assert fake_gh_runner.commands == []
