"""Tests for syntax highlighting with highlight.js (Issue #39)"""
import re
from pathlib import Path

# Get project root
ASSISTANT_DIR = Path(__file__).parent.parent
UI_DIR = ASSISTANT_DIR / "ui"


def test_highlightjs_library_exists_locally():
    """Verify highlight.js is bundled in ui/vendor/"""
    vendor_dir = UI_DIR / "vendor"
    assert vendor_dir.exists(), "vendor directory not found"

    # Check highlight.min.js
    hljs_path = vendor_dir / "highlight.min.js"
    assert hljs_path.exists(), "highlight.min.js not found in vendor/"
    assert hljs_path.stat().st_size > 50000, "highlight.min.js file too small (possibly empty)"

    # Verify it's valid JavaScript
    hljs_content = hljs_path.read_text()
    assert hljs_content.startswith("/*") or hljs_content.startswith("!"), \
        "highlight.min.js doesn't look like valid minified JS"
    assert "hljs" in hljs_content, "highlight.min.js missing 'hljs' identifier"


def test_highlightjs_themes_exist_locally():
    """Verify both light and dark themes are bundled locally"""
    vendor_dir = UI_DIR / "vendor"

    # Check GitHub light theme
    light_theme = vendor_dir / "github.min.css"
    assert light_theme.exists(), "github.min.css (light theme) not found"
    assert light_theme.stat().st_size > 500, "github.min.css too small"

    light_content = light_theme.read_text()
    assert ".hljs" in light_content or "highlight" in light_content, \
        "github.min.css doesn't look like highlight.js theme"

    # Check GitHub dark theme
    dark_theme = vendor_dir / "github-dark.min.css"
    assert dark_theme.exists(), "github-dark.min.css (dark theme) not found"
    assert dark_theme.stat().st_size > 500, "github-dark.min.css too small"

    dark_content = dark_theme.read_text()
    assert ".hljs" in dark_content or "highlight" in dark_content, \
        "github-dark.min.css doesn't look like highlight.js theme"


def test_index_html_includes_highlightjs():
    """Verify index.html includes highlight.js script"""
    index_path = UI_DIR / "index.html"
    assert index_path.exists(), "index.html not found"

    content = index_path.read_text()

    # Check for highlight.js local path
    assert "highlight" in content.lower(), "highlight.js not referenced in index.html"
    assert "/static/vendor/highlight.min.js" in content, \
        "highlight.js local path missing (should use /static/vendor/highlight.min.js)"


def test_index_html_includes_both_themes():
    """Verify index.html includes both light and dark theme stylesheets"""
    index_path = UI_DIR / "index.html"
    content = index_path.read_text()

    # Check for light theme
    assert "github.min.css" in content, "github.min.css (light theme) not included"
    assert "/static/vendor/github.min.css" in content, "Light theme not using local path"

    # Check for dark theme
    assert "github-dark.min.css" in content, "github-dark.min.css (dark theme) not included"
    assert "/static/vendor/github-dark.min.css" in content, "Dark theme not using local path"


def test_no_cdn_dependencies():
    """Verify no external CDN links for highlight.js (local-first promise)"""
    index_path = UI_DIR / "index.html"
    content = index_path.read_text()

    # Should not have any CDN links to highlight.js
    assert "cdnjs.cloudflare.com/ajax/libs/highlight.js" not in content, \
        "Found CDN link to highlight.js - should use local vendor files"


def test_app_js_uses_highlightjs_with_marked():
    """Verify app.js integrates highlight.js with marked.js via highlight option"""
    app_js_path = UI_DIR / "app.js"
    assert app_js_path.exists(), "app.js not found"

    content = app_js_path.read_text()

    # Check for marked.setOptions with highlight function
    assert "marked.setOptions" in content, "marked.setOptions() not found"

    # Find marked.setOptions sections
    marked_sections = re.findall(
        r'marked\.setOptions\s*\(\s*\{[^}]+highlight[^}]*\}\s*\)',
        content,
        re.DOTALL
    )

    assert len(marked_sections) > 0, "No marked.setOptions with highlight option found"

    # Check that highlight function uses hljs
    for section in marked_sections:
        assert "hljs" in section, "highlight function doesn't use hljs"
        assert "hljs.highlight" in section or "hljs.highlightAuto" in section, \
            "highlight function doesn't call hljs.highlight or hljs.highlightAuto"


def test_app_js_has_copy_button_function():
    """Verify app.js has addCopyButtonsToCodeBlocks function"""
    app_js_path = UI_DIR / "app.js"
    content = app_js_path.read_text()

    # Check for the function
    assert "addCopyButtonsToCodeBlocks" in content, \
        "addCopyButtonsToCodeBlocks function not found"

    # Check that it's called after markdown rendering
    assert content.count("addCopyButtonsToCodeBlocks") >= 2, \
        "addCopyButtonsToCodeBlocks should be called at least twice (regular + streaming)"


def test_app_js_copy_button_uses_clipboard_api():
    """Verify copy button uses navigator.clipboard API"""
    app_js_path = UI_DIR / "app.js"
    content = app_js_path.read_text()

    # Find addCopyButtonsToCodeBlocks function
    func_match = re.search(
        r'function addCopyButtonsToCodeBlocks\([^)]*\)\s*\{.*?\n\}',
        content,
        re.DOTALL
    )
    assert func_match, "addCopyButtonsToCodeBlocks function not found"

    func_body = func_match.group()

    # Should use navigator.clipboard
    assert "navigator.clipboard" in func_body, \
        "Copy button doesn't use navigator.clipboard API"
    assert "writeText" in func_body, "Copy button doesn't use writeText method"


def test_app_js_has_theme_switcher_for_highlightjs():
    """Verify app.js has updateHighlightTheme function"""
    app_js_path = UI_DIR / "app.js"
    content = app_js_path.read_text()

    # Check for theme update function
    assert "updateHighlightTheme" in content, "updateHighlightTheme function not found"

    # Find the function
    func_match = re.search(
        r'function updateHighlightTheme\([^)]*\)\s*\{.*?\n\}',
        content,
        re.DOTALL
    )
    assert func_match, "updateHighlightTheme function body not found"

    func_body = func_match.group()

    # Should toggle between light and dark themes
    assert "github.min.css" in func_body or "github-dark.min.css" in func_body, \
        "updateHighlightTheme doesn't reference theme files"
    assert "disabled" in func_body, \
        "updateHighlightTheme doesn't toggle theme disabled state"


def test_app_js_calls_update_highlight_theme():
    """Verify updateHighlightTheme is called when theme changes"""
    app_js_path = UI_DIR / "app.js"
    content = app_js_path.read_text()

    # Should be called on DOMContentLoaded
    dom_ready_section = content.split("DOMContentLoaded")[1].split("});")[0]
    assert "updateHighlightTheme" in dom_ready_section, \
        "updateHighlightTheme not called on page load"

    # Should be called in toggleTheme
    toggle_theme_match = re.search(
        r'function toggleTheme\([^)]*\)\s*\{.*?\n\}',
        content,
        re.DOTALL
    )
    assert toggle_theme_match, "toggleTheme function not found"

    toggle_body = toggle_theme_match.group()
    assert "updateHighlightTheme" in toggle_body, \
        "updateHighlightTheme not called when theme toggles"


def test_style_css_has_copy_button_styles():
    """Verify style.css includes styles for copy button"""
    style_path = UI_DIR / "style.css"
    assert style_path.exists(), "style.css not found"

    content = style_path.read_text()

    # Check for copy button styles
    assert ".code-copy-btn" in content, "Copy button styles not found"

    # Find copy button section
    copy_btn_section = re.search(
        r'\.code-copy-btn\s*\{[^}]+\}',
        content,
        re.DOTALL
    )
    assert copy_btn_section, "Copy button style block not found"

    btn_styles = copy_btn_section.group()
    assert "position" in btn_styles, "Copy button missing positioning"
    assert "cursor: pointer" in btn_styles, "Copy button not clickable"
    assert "opacity" in btn_styles, "Copy button missing opacity (for hover effect)"


def test_style_css_copy_button_hover_states():
    """Verify copy button has hover and copied states"""
    style_path = UI_DIR / "style.css"
    content = style_path.read_text()

    # Check for hover state
    assert ".code-copy-btn:hover" in content, "Copy button hover state not found"

    # Check for copied state
    assert ".code-copy-btn.copied" in content, "Copy button copied state not found"


def test_style_css_copy_button_visible_on_hover():
    """Verify copy button shows on hover (desktop) and always (mobile)"""
    style_path = UI_DIR / "style.css"
    content = style_path.read_text()

    # Check for hover visibility rule
    hover_rule = re.search(
        r'\.message\.assistant\s+pre:hover\s+\.code-copy-btn\s*\{[^}]+\}',
        content,
        re.DOTALL
    )
    assert hover_rule, "Copy button hover visibility rule not found"

    hover_styles = hover_rule.group()
    assert "opacity" in hover_styles, "Copy button doesn't change opacity on hover"


def test_style_css_mobile_copy_button_always_visible():
    """Verify copy button is always visible on mobile"""
    style_path = UI_DIR / "style.css"
    content = style_path.read_text()

    # Find mobile media query section
    mobile_section = re.search(
        r'@media\s+\(max-width:\s*900px\)\s*\{.*?\}(?=\s*@media|\s*$)',
        content,
        re.DOTALL
    )
    assert mobile_section, "Mobile media query not found"

    mobile_styles = mobile_section.group()

    # Check if copy button is addressed in mobile styles
    # It should either override opacity or mention code-copy-btn
    assert ".code-copy-btn" in mobile_styles, \
        "Copy button not styled for mobile (should always be visible)"


def test_style_css_code_block_wrapper():
    """Verify code block wrapper has room for copy button"""
    style_path = UI_DIR / "style.css"
    content = style_path.read_text()

    # Check for code-block-wrapper class
    wrapper_section = re.search(
        r'\.message\.assistant\s+pre\.code-block-wrapper\s*\{[^}]+\}',
        content,
        re.DOTALL
    )
    assert wrapper_section, "code-block-wrapper styles not found"

    wrapper_styles = wrapper_section.group()
    assert "padding-top" in wrapper_styles, \
        "code-block-wrapper doesn't add top padding for copy button"


def test_highlight_function_has_language_support():
    """Verify highlight function checks for language and uses hljs.highlight"""
    app_js_path = UI_DIR / "app.js"
    content = app_js_path.read_text()

    # Find marked.setOptions sections
    marked_sections = re.findall(
        r'marked\.setOptions\s*\(\s*\{.*?highlight:\s*function[^}]+\}.*?\}\s*\)',
        content,
        re.DOTALL
    )

    assert len(marked_sections) > 0, "No marked.setOptions with highlight function found"

    for section in marked_sections:
        # Should check if language is specified
        assert "lang" in section, "highlight function doesn't check for language parameter"

        # Should use hljs.highlight for specific languages
        assert "hljs.highlight" in section, "highlight function doesn't use hljs.highlight"

        # Should use hljs.highlightAuto for auto-detection
        assert "hljs.highlightAuto" in section, \
            "highlight function doesn't use hljs.highlightAuto for fallback"


def test_highlight_function_has_error_handling():
    """Verify highlight function has try-catch for error handling"""
    app_js_path = UI_DIR / "app.js"
    content = app_js_path.read_text()

    # Count occurrences of highlight: function
    highlight_count = content.count("highlight: function")
    assert highlight_count >= 2, \
        f"Expected at least 2 highlight functions (regular + streaming), found {highlight_count}"

    # Find sections with highlight functions and verify they have error handling
    # Split content by "highlight: function" and check each section
    sections = content.split("highlight: function")

    # Check each highlight function section (skip first split which is before any function)
    for i, section in enumerate(sections[1:], 1):
        # Take enough characters to include the function body
        func_section = section[:1000]

        # Should have try-catch blocks for error handling
        assert "try" in func_section and "catch" in func_section, \
            f"Highlight function #{i} missing error handling (try-catch)"

        # Should catch errors with console.error
        assert "console.error" in func_section, \
            f"Highlight function #{i} doesn't log errors with console.error"


def test_streaming_uses_syntax_highlighting():
    """Verify streaming responses also use syntax highlighting"""
    app_js_path = UI_DIR / "app.js"
    content = app_js_path.read_text()

    # Find streaming finalization section
    finalize_match = re.search(
        r'// Convert accumulated plain text to markdown.*?addCopyButtonsToCodeBlocks',
        content,
        re.DOTALL
    )
    assert finalize_match, "Streaming markdown conversion section not found"

    finalize_section = finalize_match.group()

    # Should configure marked with highlight
    assert "marked.setOptions" in finalize_section, \
        "Streaming doesn't configure marked for highlighting"
    assert "highlight:" in finalize_section, \
        "Streaming doesn't set highlight function"

    # Should add copy buttons after streaming completes
    assert "addCopyButtonsToCodeBlocks" in finalize_section, \
        "Streaming doesn't add copy buttons to code blocks"


def test_copy_button_has_safe_dom_manipulation():
    """Verify copy button creation uses safe DOM methods"""
    app_js_path = UI_DIR / "app.js"
    content = app_js_path.read_text()

    # Find addCopyButtonsToCodeBlocks function
    func_match = re.search(
        r'function addCopyButtonsToCodeBlocks\([^)]*\)\s*\{.*?\n\}',
        content,
        re.DOTALL
    )
    assert func_match, "addCopyButtonsToCodeBlocks function not found"

    func_body = func_match.group()

    # Should use createElement for button creation
    assert "createElement" in func_body, \
        "Copy button not created with createElement (XSS risk)"

    # Should use textContent for button text
    assert "textContent" in func_body, \
        "Copy button text not set with textContent (should avoid innerHTML)"

    # Should NOT use innerHTML for copy button
    assert "innerHTML" not in func_body or func_body.count("innerHTML") == 0, \
        "Copy button function uses innerHTML (XSS risk)"


def test_highlightjs_loads_before_app_js():
    """Verify highlight.js loads before app.js"""
    index_path = UI_DIR / "index.html"
    content = index_path.read_text()

    # Find script tag positions
    hljs_pos = content.find("highlight.min.js")
    app_js_pos = content.find("/static/app.js")

    assert hljs_pos > 0, "highlight.js not found in index.html"
    assert app_js_pos > 0, "app.js not found in index.html"

    # highlight.js must load before app.js
    assert hljs_pos < app_js_pos, "highlight.js loaded after app.js (will cause errors)"


def test_themes_load_before_highlightjs():
    """Verify theme CSS files load before highlight.js script"""
    index_path = UI_DIR / "index.html"
    content = index_path.read_text()

    light_theme_pos = content.find("github.min.css")
    dark_theme_pos = content.find("github-dark.min.css")
    hljs_pos = content.find("highlight.min.js")

    assert light_theme_pos > 0, "Light theme not found"
    assert dark_theme_pos > 0, "Dark theme not found"
    assert hljs_pos > 0, "highlight.js not found"

    # Themes should load before script
    assert light_theme_pos < hljs_pos, "Light theme loaded after highlight.js"
    assert dark_theme_pos < hljs_pos, "Dark theme loaded after highlight.js"
