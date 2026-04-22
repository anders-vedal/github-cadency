"""CODEOWNERS parsing and bypass detection.

Implements just enough of GitHub's CODEOWNERS spec to evaluate whether a PR's
merge skipped matching owner approval. The real GitHub spec is richer (e.g.
nested globs, team expansion) — we handle the common cases: comment lines,
blank lines, path patterns (including ``*`` and ``**``), and owner tokens
starting with ``@`` (either ``@user`` or ``@org/team``) or an e-mail.

Team expansion is intentionally NOT performed here — callers that care about
team membership should pass in resolved members. ``check_bypass`` compares
reviewer logins / team tokens against the CODEOWNERS owner list verbatim,
which is how the signal is computed deterministically from synced data.
"""

from __future__ import annotations

import fnmatch


def parse_codeowners(text: str) -> list[tuple[str, list[str]]]:
    """Parse a CODEOWNERS file body.

    Returns a list of ``(pattern, owners)`` tuples in file order. Later entries
    override earlier ones — callers should iterate the returned list in reverse
    when looking up the rule for a given path.

    Lines that are blank or start with ``#`` are skipped. Each non-comment line
    must have at least a pattern and one owner token, otherwise it is silently
    ignored (matches GitHub's fail-soft behavior).
    """
    rules: list[tuple[str, list[str]]] = []
    if not text:
        return rules

    for raw_line in text.splitlines():
        # Strip inline comments first (GitHub-style: `#` starts a comment
        # unless escaped, which is rare in practice).
        line = raw_line.split("#", 1)[0].strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        pattern, *owners = parts
        # Keep only non-empty owner tokens.
        owners = [o for o in owners if o]
        if not owners:
            continue
        rules.append((pattern, owners))

    return rules


def _normalize_pattern(pattern: str) -> tuple[str, bool, bool]:
    """Return (pattern_body, rooted, directory_only).

    ``rooted=True`` means the pattern must match from the repo root (leading
    ``/``). ``directory_only=True`` means the pattern referred to a directory
    (trailing ``/``) and should match any path beneath it.
    """
    rooted = pattern.startswith("/")
    body = pattern[1:] if rooted else pattern
    directory_only = body.endswith("/")
    if directory_only:
        body = body[:-1]
    return body, rooted, directory_only


def _pattern_matches(pattern: str, path: str) -> bool:
    """Whether a CODEOWNERS pattern matches the given file path.

    Implements the subset of the CODEOWNERS spec most commonly seen in real
    repos: ``/``-rooted paths, trailing ``/`` directory markers, ``*`` glob,
    ``**`` recursive glob, and basename-only patterns like ``*.py`` that
    match anywhere in the tree.
    """
    if not pattern or not path:
        return False

    body, rooted, directory_only = _normalize_pattern(pattern)
    if not body:
        return False

    # Directory pattern matches any file under that directory.
    if directory_only:
        if rooted:
            prefix = body + "/"
            return path.startswith(prefix)
        # Unrooted directory — match any segment.
        return f"/{body}/" in f"/{path}" or path.startswith(body + "/")

    # If the pattern has no slash, it's a basename / simple glob — match
    # anywhere in the tree.
    if "/" not in body:
        basename = path.rsplit("/", 1)[-1]
        return fnmatch.fnmatch(basename, body)

    # Patterns containing ``**`` — expand by splitting on the token.
    if "**" in body:
        return _match_doublestar(body, path if rooted else _anchor_anywhere(body, path))

    if rooted:
        return fnmatch.fnmatch(path, body)

    # Unrooted path-shaped pattern — match as a suffix.
    return path.endswith(body) or fnmatch.fnmatch(path, f"*/{body}")


def _anchor_anywhere(body: str, path: str) -> str:
    # Unrooted ``**`` pattern — treat as "anywhere in the tree".
    return path


def _match_doublestar(pattern_body: str, path: str) -> bool:
    """Support ``**`` in a path-style pattern (rooted or otherwise).

    Replaces ``**`` with a regex-equivalent and delegates to ``re.fullmatch``.
    """
    import re

    # Escape everything, then un-escape glob metacharacters we want to honor.
    parts = pattern_body.split("**")
    # fnmatch.translate each part individually then glue with `.*` between.
    translated = []
    for part in parts:
        # Strip fnmatch's end-of-string anchor and leading flags from translate.
        tr = fnmatch.translate(part)
        # Python's fnmatch.translate wraps the regex as `(?s:...)\\Z` (or \\z
        # on newer Pythons) — peel the wrapper so we can join segments with `.*`.
        if tr.startswith("(?s:"):
            # trim the `(?s:` prefix and the trailing `)\\Z` or `)\\z`
            tr = tr[4:]
            if tr.endswith(")\\Z") or tr.endswith(")\\z"):
                tr = tr[:-3]
            elif tr.endswith(")"):
                tr = tr[:-1]
        translated.append(tr)
    regex = ".*".join(translated)
    return re.fullmatch(regex, path) is not None


def matching_owners(
    rules: list[tuple[str, list[str]]],
    changed_paths: list[str],
) -> set[str]:
    """Return the set of owner tokens that own at least one of the changed paths.

    GitHub resolves CODEOWNERS by using the *last* matching rule for a given
    path — so we walk the rules in reverse for each path and take the first
    match. If a path has no match, it simply contributes no owners.
    """
    owners: set[str] = set()
    if not rules or not changed_paths:
        return owners

    for path in changed_paths:
        for pattern, rule_owners in reversed(rules):
            if _pattern_matches(pattern, path):
                owners.update(rule_owners)
                break
    return owners


def check_bypass(
    changed_paths: list[str],
    rules: list[tuple[str, list[str]]],
    approver_tokens: list[str],
    *,
    merged: bool = True,
    review_decision: str | None = None,
) -> bool:
    """Return True if a merged PR bypassed CODEOWNERS.

    A "bypass" here means:
      - the PR merged, AND
      - there was at least one required owner for a touched file, AND
      - at least one required owner did not submit an approving review.

    Per-path semantics: for each touched path, *the last matching rule wins*
    (GitHub's spec). If that rule's owner list has no intersection with the
    approvers, we treat the PR as having bypassed the required reviewer set.
    The function returns True as soon as any path fails its owner check.

    ``approver_tokens`` should be the set of reviewer logins/team refs that
    submitted an APPROVED review. If ``review_decision`` is provided and
    already equals ``"APPROVED"``, we short-circuit to "not a bypass" — GitHub
    itself already signaled a clean approval path.

    If ``changed_paths`` or ``rules`` is empty we return ``False`` — we never
    falsely flag a PR as a bypass when there is no basis to compute one.
    """
    if not merged:
        return False
    if review_decision and review_decision.upper() == "APPROVED":
        return False
    if not rules or not changed_paths:
        return False

    approver_set = {_normalize(a) for a in approver_tokens if a}
    found_any_owner = False

    for path in changed_paths:
        # Find the last matching rule for this path (GitHub's last-wins rule).
        path_owners: list[str] = []
        for pattern, rule_owners in reversed(rules):
            if _pattern_matches(pattern, path):
                path_owners = rule_owners
                break
        if not path_owners:
            continue
        found_any_owner = True
        normalized_owners = {_normalize(o) for o in path_owners}
        # If NONE of this path's required owners approved, that's a bypass.
        if not (normalized_owners & approver_set):
            return True

    # If no path had an owner, no "bypass" can be claimed.
    if not found_any_owner:
        return False
    # Every path's required set had at least one approver in it.
    return False


def _normalize(token: str) -> str:
    """Lowercase owner/approver tokens and strip the leading ``@`` if present."""
    if not token:
        return ""
    t = token.strip().lower()
    if t.startswith("@"):
        t = t[1:]
    return t
