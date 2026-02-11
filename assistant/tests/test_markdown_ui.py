"""Tests for Markdown rendering in Web UI (Issue #29)"""
import re
from pathlib import Path

# Get project root
ASSISTANT_DIR = Path(__file__).parent.parent
UI_DIR = ASSISTANT_DIR / "ui"


def test_index_html_has_markdown_libraries():
    """Verify index.html includes marked.js and DOMPurify from local vendor/"""
    index_path = UI_DIR / "index.html"
    assert index_path.exists(), "index.html not found"

    content = index_path.read_text()

    # Check for marked.js local path (Issue #35: bundled locally)
    assert "marked" in content.lower(), "marked.js library not found in index.html"
    assert "/static/vendor/marked.min.js" in content, "marked.js local path missing"

    # Check for DOMPurify local path (Issue #35: bundled locally)
    assert "purify" in content.lower(), "DOMPurify library not found in index.html"
    assert "/static/vendor/purify.min.js" in content, "DOMPurify local path missing"

    # Verify NO external CDN links (local-first promise)
    assert "cdn.jsdelivr.net" not in content or content.count("cdn.jsdelivr.net") == 0, \
        "CDN links found - should use local vendor files"


def test_vendor_libraries_exist_locally():
    """Verify marked.js and DOMPurify are bundled in ui/vendor/ (Issue #35)"""
    vendor_dir = UI_DIR / "vendor"
    assert vendor_dir.exists(), "vendor directory not found"
    assert vendor_dir.is_dir(), "vendor is not a directory"

    # Check marked.min.js
    marked_path = vendor_dir / "marked.min.js"
    assert marked_path.exists(), "marked.min.js not found in vendor/"
    assert marked_path.stat().st_size > 10000, "marked.min.js file too small (possibly empty)"

    # Verify it's valid JavaScript (starts with comment or code)
    marked_content = marked_path.read_text()
    assert marked_content.startswith("/*") or marked_content.startswith("!function"), \
        "marked.min.js doesn't look like valid minified JS"
    assert "marked" in marked_content.lower(), "marked.min.js missing 'marked' identifier"

    # Check purify.min.js
    purify_path = vendor_dir / "purify.min.js"
    assert purify_path.exists(), "purify.min.js not found in vendor/"
    assert purify_path.stat().st_size > 10000, "purify.min.js file too small (possibly empty)"

    # Verify it's valid JavaScript
    purify_content = purify_path.read_text()
    assert purify_content.startswith("/*") or purify_content.startswith("!function"), \
        "purify.min.js doesn't look like valid minified JS"
    assert "DOMPurify" in purify_content, "purify.min.js missing 'DOMPurify' identifier"


def test_app_js_uses_markdown_rendering():
    """Verify app.js uses marked.parse() and DOMPurify.sanitize()"""
    app_js_path = UI_DIR / "app.js"
    assert app_js_path.exists(), "app.js not found"

    content = app_js_path.read_text()

    # Check for marked.parse() usage
    assert "marked.parse" in content, "marked.parse() not found in app.js"

    # Check for DOMPurify.sanitize() usage
    assert "DOMPurify.sanitize" in content, "DOMPurify.sanitize() not found in app.js"

    # Check for marked configuration
    assert "marked.setOptions" in content, "marked.setOptions() not found"
    assert "gfm: true" in content, "GitHub Flavored Markdown not enabled"
    assert "breaks: true" in content, "Line breaks not enabled"


def test_app_js_sets_innerHTML_not_textContent():
    """Verify app.js uses innerHTML for assistant messages"""
    app_js_path = UI_DIR / "app.js"
    content = app_js_path.read_text()

    # Should use innerHTML for rendered markdown
    assert "innerHTML = cleanHtml" in content or "innerHTML=cleanHtml" in content, \
        "innerHTML not used for markdown rendering"


def test_streaming_converts_to_markdown():
    """Verify streaming completion converts accumulated text to markdown"""
    app_js_path = UI_DIR / "app.js"
    content = app_js_path.read_text()

    # Check that streaming finalization includes markdown conversion
    # Should parse accumulated text after streaming completes
    assert "accumulatedText" in content, "accumulatedText not tracked during streaming"

    # Should convert to markdown after streaming finishes
    # Look for markdown parsing after streaming is done
    finalize_section = content.split("// Finalize the message")[1].split("function handleStreamEvent")[0]
    assert "marked.parse" in finalize_section, "Streaming doesn't convert to markdown at end"


def test_style_css_has_markdown_styles():
    """Verify style.css includes styles for markdown elements"""
    style_path = UI_DIR / "style.css"
    assert style_path.exists(), "style.css not found"

    content = style_path.read_text()

    # Check for markdown-specific styles
    required_selectors = [
        ".message.assistant h1",
        ".message.assistant h2",
        ".message.assistant code",
        ".message.assistant pre",
        ".message.assistant ul",
        ".message.assistant ol",
        ".message.assistant blockquote",
        ".message.assistant table",
        ".message.assistant a",
    ]

    for selector in required_selectors:
        assert selector in content, f"CSS selector '{selector}' not found"


def test_code_blocks_have_background_color():
    """Verify code blocks have distinct styling"""
    style_path = UI_DIR / "style.css"
    content = style_path.read_text()

    # Find code block styles
    code_section = re.search(
        r'\.message\.assistant\s+code\s*\{[^}]+\}',
        content,
        re.DOTALL
    )
    assert code_section, "Code block styling not found"

    code_styles = code_section.group()
    assert "background-color" in code_styles, "Code blocks missing background color"
    assert "font-family" in code_styles, "Code blocks missing monospace font"


def test_pre_code_blocks_have_styling():
    """Verify pre code blocks (multi-line) have styling"""
    style_path = UI_DIR / "style.css"
    content = style_path.read_text()

    # Find pre block styles
    pre_section = re.search(
        r'\.message\.assistant\s+pre\s*\{[^}]+\}',
        content,
        re.DOTALL
    )
    assert pre_section, "Pre block styling not found"

    pre_styles = pre_section.group()
    assert "background-color" in pre_styles, "Pre blocks missing background color"
    assert "border" in pre_styles or "border:" in pre_styles, "Pre blocks missing border"
    assert "overflow-x" in pre_styles, "Pre blocks missing horizontal scroll"


def test_tables_have_border_styling():
    """Verify tables have proper border styling"""
    style_path = UI_DIR / "style.css"
    content = style_path.read_text()

    # Check for table styling
    assert ".message.assistant table" in content, "Table styling not found"
    assert ".message.assistant th" in content, "Table header styling not found"
    assert ".message.assistant td" in content, "Table cell styling not found"

    # Find th/td styles and check for borders
    th_section = re.search(
        r'\.message\.assistant\s+(th|td)\s*\{[^}]+\}',
        content,
        re.DOTALL
    )
    assert th_section, "Table cell styling not found"
    th_styles = th_section.group()
    assert "border" in th_styles, "Table cells missing borders"


def test_security_sanitization_present():
    """Verify DOMPurify is used to prevent XSS attacks"""
    app_js_path = UI_DIR / "app.js"
    content = app_js_path.read_text()

    # Find markdown rendering sections
    markdown_sections = re.findall(
        r'marked\.parse\([^)]+\)[^;]*',
        content
    )

    assert len(markdown_sections) > 0, "No markdown parsing found"

    # Every marked.parse should be followed by DOMPurify.sanitize
    for section in markdown_sections:
        # Look at context around marked.parse
        start_idx = content.find(section)
        context = content[start_idx:start_idx + 300]
        assert "DOMPurify.sanitize" in context, \
            f"marked.parse() not sanitized: {section}"


def test_user_messages_remain_plain_text():
    """Verify user messages still use textContent (not HTML) for security"""
    app_js_path = UI_DIR / "app.js"
    content = app_js_path.read_text()

    # Find addMessageToUI function
    func_match = re.search(
        r'function addMessageToUI\([^)]+\)\s*\{.*?\n\}',
        content,
        re.DOTALL
    )
    assert func_match, "addMessageToUI function not found"

    func_body = func_match.group()

    # Should have conditional: render markdown for assistant, plain text for user
    assert "role === 'assistant'" in func_body or 'role === "assistant"' in func_body, \
        "No conditional check for assistant role"

    # Should have textContent as fallback
    assert "textContent = content" in func_body or "textContent=content" in func_body, \
        "No plain text fallback for user messages"


def test_markdown_libraries_loaded_before_app_js():
    """Verify markdown libraries are loaded before app.js"""
    index_path = UI_DIR / "index.html"
    content = index_path.read_text()

    # Find script tags
    marked_pos = content.find("marked")
    dompurify_pos = content.find("purify.min.js")
    app_js_pos = content.find("/static/app.js")

    assert marked_pos > 0, "marked.js not found"
    assert dompurify_pos > 0, "DOMPurify not found"
    assert app_js_pos > 0, "app.js not found"

    # Markdown libraries must load before app.js
    assert marked_pos < app_js_pos, "marked.js loaded after app.js"
    assert dompurify_pos < app_js_pos, "DOMPurify loaded after app.js"
