"""
tests/test_frontend_sri.py — Audit test verifying Subresource Integrity (SRI) and version pinning on CDN scripts.
"""

import re
from pathlib import Path
import pytest

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"


def test_html_cdn_scripts_have_sri_and_pinned_versions():
    """Verify no external script tags use @latest and all CDN scripts enforce SRI."""
    html_files = list(FRONTEND_DIR.glob("*.html"))
    assert len(html_files) >= 5, "Expected at least index, dashboard, login, signup, and 404 html files"

    script_tag_pattern = re.compile(r'<script\b([^>]*)>', re.IGNORECASE)
    src_pattern = re.compile(r'src=["\'](https?://[^"\']+)["\']', re.IGNORECASE)
    integrity_pattern = re.compile(r'integrity=["\'](sha(?:256|384|512)-[A-Za-z0-9+/=]+)["\']', re.IGNORECASE)
    crossorigin_pattern = re.compile(r'crossorigin=["\']anonymous["\']', re.IGNORECASE)

    audited_scripts = 0

    for html_path in html_files:
        content = html_path.read_text(encoding="utf-8")
        matches = script_tag_pattern.findall(content)

        for attrs in matches:
            src_match = src_pattern.search(attrs)
            if not src_match:
                continue

            script_url = src_match.group(1)
            audited_scripts += 1

            # 1. Reject unpinned floating versions
            assert "@latest" not in script_url, (
                f"Floating version '@latest' forbidden in {html_path.name}: {script_url}"
            )

            # 2. Require SRI integrity hash
            integrity_match = integrity_pattern.search(attrs)
            assert integrity_match is not None, (
                f"Missing Subresource Integrity attribute in {html_path.name}: {script_url}"
            )
            assert integrity_match.group(1).startswith("sha384-"), (
                f"Expected sha384 integrity hash in {html_path.name}: {script_url}"
            )

            # 3. Require crossorigin="anonymous"
            crossorigin_match = crossorigin_pattern.search(attrs)
            assert crossorigin_match is not None, (
                f"Missing crossorigin=\"anonymous\" attribute in {html_path.name}: {script_url}"
            )

    assert audited_scripts >= 6, f"Expected at least 6 external CDN scripts across HTML files, found {audited_scripts}"
