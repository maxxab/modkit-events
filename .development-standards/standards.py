#!/usr/bin/env python3
"""Dependency-free Conventional Commits and deterministic changelog checks."""
import argparse
from collections import defaultdict
import json
from pathlib import Path
import re
import subprocess
import sys
from urllib.parse import quote, urlsplit

CATEGORIES = {'feat': 'Features', 'fix': 'Bug Fixes', 'perf': 'Performance',
              'security': 'Security', 'refactor': 'Refactoring', 'docs': 'Documentation',
              'test': 'Testing', 'build': 'Build System', 'ci': 'CI/CD',
              'chore': 'Maintenance', 'style': 'Maintenance', 'revert': 'Reverts'}
DEFAULT = {'types': list(CATEGORIES), 'scopes': [], 'require_scope': False,
           'max_subject_length': 100, 'changelog': 'CHANGELOG.md'}
HEADER = re.compile(r'([a-z]+)(?:\(([^()\s]+)\))?(!)?: (\S.*)')


class StandardsError(Exception):
    pass


def git(*args, optional=False):
    result = subprocess.run(['git', *args], capture_output=True, text=True, encoding='utf-8', errors='replace')
    if result.returncode and not optional:
        # Git diagnostics can include a remote URL containing credentials.
        raise StandardsError('Git command failed: ' + ' '.join(args[:2]) + '. Check repository and references.')
    return result.stdout if not result.returncode else ''


def root():
    value = git('rev-parse', '--show-toplevel', optional=True).strip()
    return Path(value) if value else Path.cwd()


def config_load(explicit=None):
    project = root() / '.development-standards' / 'conventional.json'
    path = Path(explicit) if explicit else project if project.exists() else Path(__file__).with_name('conventional.json')
    config = dict(DEFAULT)
    if explicit or path.exists():
        try:
            supplied = json.loads(path.read_text(encoding='utf-8'))
            if not isinstance(supplied, dict) or set(supplied) - set(DEFAULT):
                raise ValueError('unknown configuration keys')
            config.update(supplied)
        except (OSError, ValueError) as exc:
            raise StandardsError(f'Invalid configuration {path}: {exc}') from exc
    override = root() / '.development-standards' / 'project.json'
    if override.exists():
        try:
            supplied = json.loads(override.read_text(encoding='utf-8'))
            if not isinstance(supplied, dict) or set(supplied) - {'scopes', 'require_scope'}:
                raise ValueError('project overrides may contain only scopes and require_scope')
            config.update(supplied)
        except (OSError, ValueError) as exc:
            raise StandardsError(f'Invalid project configuration {override}: {exc}') from exc
    for key in ('types', 'scopes'):
        if not isinstance(config[key], list) or any(not isinstance(item, str) or not item for item in config[key]):
            raise StandardsError(f'Configuration {key} must be a list of nonempty strings')
    if not config['types'] or set(config['types']) - set(CATEGORIES):
        raise StandardsError('Configuration types must be supported Conventional Commit types')
    if type(config['require_scope']) is not bool or type(config['max_subject_length']) is not int or config['max_subject_length'] < 1:
        raise StandardsError('Invalid require_scope or max_subject_length configuration')
    if not isinstance(config['changelog'], str) or not config['changelog'] or Path(config['changelog']).is_absolute() or '..' in Path(config['changelog']).parts:
        raise StandardsError('Configuration changelog must be a relative project path')
    return config


def parse_message(message, config):
    lines = message.splitlines()
    if not lines:
        raise StandardsError('Commit message is empty')
    subject = lines[0]
    match = HEADER.fullmatch(subject)
    if not match:
        raise StandardsError('Expected type(scope)!: description (scope and ! are optional)')
    kind, scope, bang, description = match.groups()
    if kind not in config['types']:
        raise StandardsError(f'Unsupported commit type: {kind}')
    if scope and config['scopes'] and scope not in config['scopes']:
        raise StandardsError(f'Unsupported commit scope: {scope}')
    if config['require_scope'] and not scope:
        raise StandardsError('Commit scope is required')
    if len(subject) > config['max_subject_length']:
        raise StandardsError(f'Commit subject exceeds {config["max_subject_length"]} characters')
    if len(lines) > 1 and lines[1].strip():
        raise StandardsError('Separate subject and body with a blank line')
    footer_started = False
    breaking = bool(bang)
    for index, line in enumerate(lines[2:], 2):
        marker = re.match(r'^BREAKING(?: CHANGE|-CHANGE):[ \t]*(.*)$', line)
        is_footer = re.match(r'^(?:[A-Za-z][A-Za-z-]*|BREAKING CHANGE)(?:: | #)\S', line)
        if is_footer and not lines[index - 1].strip():
            footer_started = True
        if marker:
            if not marker.group(1).strip():
                raise StandardsError('Breaking footer requires a nonempty description on its first line')
            if not footer_started:
                raise StandardsError('Breaking footer must begin a footer section separated by a blank line')
            breaking = True
    return {'type': kind, 'scope': scope, 'description': description.strip(), 'breaking': breaking}


def history_ready(allow_empty=False):
    git('rev-parse', '--git-dir')
    if git('rev-parse', '--is-shallow-repository').strip() == 'true':
        raise StandardsError('Shallow history is incomplete; fetch full history before checking standards')
    if allow_empty and not git('rev-parse', '--verify', 'HEAD', optional=True):
        if git('symbolic-ref', '-q', 'HEAD', optional=True) and not git('show-ref', optional=True):
            return None
    return revision('HEAD')


def revision(ref):
    value = git('rev-parse', '--verify', '--end-of-options', ref + '^{commit}', optional=True).strip()
    if not value:
        raise StandardsError(f'Missing or invalid commit reference: {ref}')
    return value


def ancestor(base, head):
    return subprocess.run(['git', 'merge-base', '--is-ancestor', base, head], capture_output=True).returncode == 0


def commits(revs):
    hashes = git('rev-list', '--reverse', '--topo-order', revs).splitlines()
    return [(sha, git('show', '-s', '--format=%B', sha).rstrip('\n')) for sha in hashes]


def validate_range(base, head, config):
    history_ready()
    base, head = revision(base), revision(head)
    if not ancestor(base, head):
        raise StandardsError('Range base must be an ancestor of head')
    manifest = root() / '.development-standards' / 'manifest.json'
    if manifest.exists():
        try:
            baseline = json.loads(manifest.read_text(encoding='utf-8')).get('baseline')
        except (OSError, ValueError, AttributeError) as exc:
            raise StandardsError('Invalid standards manifest') from exc
        if baseline:
            baseline = revision(baseline)
            if not ancestor(baseline, head):
                raise StandardsError('Adoption baseline must be an ancestor of head')
            if ancestor(base, baseline):
                base = baseline
    errors = []
    for sha, message in commits(base + '..' + head):
        try:
            parse_message(message, config)
        except StandardsError as exc:
            errors.append(f'{sha[:12]} {message.splitlines()[0] if message else "<empty>"}: {exc}')
    if errors:
        raise StandardsError('\n'.join(errors))
    return base, head


def origin_url():
    remote = git('remote', 'get-url', 'origin', optional=True).strip()
    if re.fullmatch(r'git@[^: /]+:[^\s?#]+', remote):
        host, path = remote[4:].split(':', 1)
        remote = 'https://' + host + '/' + path
    try:
        parsed = urlsplit(remote)
        if parsed.scheme not in ('https', 'http', 'ssh') or not parsed.hostname or parsed.query or parsed.fragment:
            return None
        host = parsed.hostname
        if ':' in host:
            host = '[' + host + ']'
        port = parsed.port
        if port and parsed.scheme != 'ssh':
            host += ':' + str(port)
        path = parsed.path.rstrip('/').removesuffix('.git')
        if not path or any(char in path for char in '\n\r'):
            return None
        return 'https://' + host + quote(path, safe='/~._-')
    except ValueError:
        return None


def markdown(value):
    return re.sub(r'([\\`*\[\]<>_])', r'\\\1', value)


def changelog(config, head='HEAD'):
    has_history = history_ready(allow_empty=True)
    head = revision(head) if has_history or head != 'HEAD' else None
    groups = defaultdict(list)
    remote = origin_url()
    for sha, message in (commits(head) if head else []):
        # A generated-file-only update must not recursively include its own hash.
        paths = git('diff-tree', '--root', '--no-commit-id', '--name-only', '-r', sha).splitlines()
        if paths and set(paths) == {config['changelog']}:
            continue
        try:
            item = parse_message(message, config)
        except StandardsError:
            continue  # Historical exceptions never affect validation of the new range.
        text = (f'**{markdown(item["scope"])}:** ' if item['scope'] else '') + markdown(item['description'])
        reference = f'[{sha[:12]}]({remote}/commit/{sha})' if remote else f'`{sha[:12]}`'
        entry = f'- {text} ({reference})'
        groups[CATEGORIES[item['type']]].append(entry)
        if item['breaking']:
            groups['Breaking Changes'].append(entry)
    lines = ['# Changelog', '', '<!-- Generated by development-standards. Do not edit manually. -->', '']
    for category in dict.fromkeys(['Breaking Changes', *CATEGORIES.values()]):
        if groups[category]:
            lines += ['### ' + category, '', *groups[category], '']
    if not any(groups.values()):
        lines += ['No conventional commits recorded.', '']
    return '\n'.join(lines)


def check_changelog(config, output=None, check=False, head='HEAD'):
    rendered = changelog(config, head)
    path = root() / (output or config['changelog'])
    if check:
        if not path.exists() or path.read_text(encoding='utf-8') != rendered:
            raise StandardsError(f'{path} is missing or outdated; run changelog --output {output or config["changelog"]}, then commit the generated file alone')
    elif output:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(rendered, encoding='utf-8')
    else:
        sys.stdout.write(rendered)


def release_suggestion(base, head, config, current=None):
    base, head = validate_range(base, head, config)
    items = [parse_message(message, config) for _, message in commits(base + '..' + head)]
    level = 'major' if any(item['breaking'] for item in items) else 'minor' if any(item['type'] == 'feat' for item in items) else 'patch' if any(item['type'] in ('fix', 'perf', 'security') for item in items) else 'none'
    result = {'suggestion': level, 'publishes': False}
    if current is not None:
        if not re.fullmatch(r'(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)', current):
            raise StandardsError('Current version must be a stable X.Y.Z SemVer version')
        major, minor, patch = map(int, current.split('.'))
        if level == 'major':
            major, minor, patch = major + 1, 0, 0
        elif level == 'minor':
            minor, patch = minor + 1, 0
        elif level == 'patch':
            patch += 1
        result['next_version'] = f'{major}.{minor}.{patch}'
    print(json.dumps(result, sort_keys=True))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    message = sub.add_parser('validate-message')
    message.add_argument('file')
    ranges = sub.add_parser('validate-range')
    ranges.add_argument('base')
    ranges.add_argument('head')
    log = sub.add_parser('changelog')
    log.add_argument('--output')
    log.add_argument('--check', action='store_true')
    check = sub.add_parser('check')
    check.add_argument('--base', required=True)
    check.add_argument('--head', required=True)
    release = sub.add_parser('release-suggestion')
    release.add_argument('base')
    release.add_argument('head')
    release.add_argument('--current')
    sub.add_parser('staged')
    for command in (message, ranges, log, check, release):
        command.add_argument('--config')
    args = parser.parse_args(argv)
    try:
        if args.command == 'staged':
            result = subprocess.run(['git', 'diff', '--cached', '--check'], capture_output=True, text=True)
            paths = git('diff', '--cached', '--name-only')
            print('Staged paths for human atomicity review:')
            print(paths or '(none)', end='' if paths else '\n')
            print('Confirm one logical change and review the staged diff before committing.')
            if result.returncode:
                raise StandardsError(result.stdout.strip() or 'Staged diff whitespace check failed')
            return 0
        config = config_load(args.config)
        if args.command == 'validate-message':
            parse_message(Path(args.file).read_text(encoding='utf-8'), config)
        elif args.command == 'validate-range':
            validate_range(args.base, args.head, config)
        elif args.command == 'changelog':
            check_changelog(config, args.output, args.check)
        elif args.command == 'release-suggestion':
            release_suggestion(args.base, args.head, config, args.current)
        elif args.command == 'check':
            validate_range(args.base, args.head, config)
            check_changelog(config, check=True, head=args.head)
        return 0
    except (StandardsError, OSError, UnicodeError) as exc:
        print(f'standards: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
