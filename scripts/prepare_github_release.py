"""Export a reviewed source-only GitHub folder without Git or network operations.

Original evidence is never modified. Local-only Markdown links become labelled
references in the export, and workstation paths are redacted there. The manifest
records both source and exported hashes so these edits are visible.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]
CODE_DIRS = ("hpo", "evaluation", "pilot", "runtime", "configs", "schemas", "scripts", "tests")
ROOT_FILES = ("README.md", "GITHUB_UPLOAD.md", "THIRD_PARTY_NOTICES.md", ".gitignore",
              ".gitattributes", "requirements-hpo.lock")
LOCAL_DOCS = {"project_audit_and_team_plan_20261028.md", "project_progress_audit_20261028.md"}
LINK = re.compile(r'(?<!!)\[([^\]\n]+)\]\((<[^>]+>|[^)\n]+)\)')
SECRETS = {
    "provider_key": re.compile(rb'(?<![A-Za-z0-9_-])sk-(?:or-v1-)?[A-Za-z0-9_-]{24,}'),
    "github_token": re.compile(rb'(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,})'),
    "private_key": re.compile(rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'),
    "aws_access_id": re.compile(rb'AKIA[0-9A-Z]{16}'),
}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def selected_files():
    result = {ROOT / n for n in ROOT_FILES}
    for folder in CODE_DIRS:
        result.update(p for p in (ROOT / folder).rglob('*') if p.is_file()
                      and '__pycache__' not in p.parts and p.suffix not in ('.pyc', '.pyo')
                      and p.name != '.DS_Store')
    for p in (ROOT / 'docs').rglob('*'):
        rel = p.relative_to(ROOT).as_posix()
        if p.suffix not in ('.md', '.json') or p.name in LOCAL_DOCS:
            continue
        if rel.startswith(('docs/sources/research/', 'docs/sources/hpo/smac/',
                           'docs/sources/hpo/ConfigSpace/')):
            continue
        result.add(p)
    result.update(p for p in (ROOT / 'artifacts/release-verification').rglob('*')
                  if p.is_file() and p.suffix in ('.md', '.json', '.svg'))
    return sorted(result)


def local_target(document, target):
    target = target.strip('<>')
    if not target or target.startswith('#') or re.match(r'^[a-zA-Z][\w+.-]*:', target):
        return None
    return (document.parent / unquote(target.split('#')[0])).resolve()


def export(output):
    output = Path(output).resolve()
    if output == ROOT or ROOT.is_relative_to(output):
        raise ValueError('Output must be a new export directory, never the project root or its parent')
    if output.is_relative_to(ROOT) and output.parts[len(ROOT.parts)] not in ('runs',) and not output.name.startswith('github-upload'):
        raise ValueError('Inside this project, use runs/... or a github-upload* directory')
    files = selected_files()
    names = {p.resolve() for p in files}
    directories = {parent for p in names for parent in p.parents if parent.is_relative_to(ROOT)}
    payloads, records, link_changes = {}, {}, []
    for p in files:
        if p.is_symlink():
            raise ValueError(f'Symlinks are not exported: {p.relative_to(ROOT)}')
        original = p.read_bytes()
        rel = p.relative_to(ROOT).as_posix()
        for kind, pattern in SECRETS.items():
            if pattern.search(original):
                raise ValueError(f'Potential {kind} in {rel}; contents not printed')
        value = original.decode('utf-8')
        if p.suffix in ('.md', '.json', '.svg'):
            value = value.replace(str(ROOT), '<project-root>')
            # Redact prose/data only; never rewrite executable code or regexes.
            value = re.sub(r'/Users/[A-Za-z0-9._ -]+/', '<user-home>/', value)
        if p.suffix == '.md':
            def replace(match):
                label, target = match.groups()
                resolved = local_target(p, target)
                if resolved is None or resolved in names or resolved in directories:
                    return match.group(0)
                link_changes.append({'document': rel, 'target': target})
                return f'{label}（本地或历史材料，未打包：`{target.strip(chr(60)+chr(62))}`）'
            value = LINK.sub(replace, value)
        payload = value.encode('utf-8')
        payloads[rel] = (payload, p.stat().st_mode & 0o777)
        records[rel] = {'source_sha256': sha(original), 'exported_sha256': sha(payload),
                        'bytes': len(payload), 'transformed': original != payload}
    # Finish review before creating anything in the destination.
    output.mkdir(parents=True, exist_ok=False)
    for name, (payload, mode) in payloads.items():
        p = output / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(payload)
        p.chmod(mode)
    manifest = {
        'created_at_utc': datetime.now(timezone.utc).isoformat(),
        'status': 'engineering_snapshot_not_completed_research',
        'git_initialized': False, 'published': False, 'model_calls_by_export': 0,
        'file_count_excluding_this_manifest': len(records),
        'excluded': ['runs/', 'logs/', '.venv*/', 'third_party/', 'course documents',
                     'paper PDFs', 'downloaded source excerpts', 'raw archives', 'team work notes'],
        'local_links_converted_to_labelled_references': link_changes,
        'files': records,
        'limits': ['Pattern scanning is not an exhaustive secret or license audit.',
                   'Historical manifests stay historical; use the release protocol for current hashes.',
                   'Local evidence scripts require the separately retained original runs.'],
    }
    (output / 'UPLOAD_MANIFEST.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps({'output': str(output), 'files': len(records)+1,
                      'local_links_labelled': len(link_changes), 'model_calls': 0}, ensure_ascii=False))
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', default=str(ROOT / 'github-upload'))
    export(parser.parse_args().output)
