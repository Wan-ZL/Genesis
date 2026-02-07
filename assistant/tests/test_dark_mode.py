"""Tests for Dark Mode and UI Visual Refresh (Issue #33)"""
import re
from pathlib import Path

# Get project root
ASSISTANT_DIR = Path(__file__).parent.parent
UI_DIR = ASSISTANT_DIR / "ui"


# ============================================================================
# CSS Custom Properties Tests
# ============================================================================

def test_css_has_root_variables():
    """Verify style.css defines CSS custom properties in :root"""
    style_path = UI_DIR / "style.css"
    assert style_path.exists(), "style.css not found"

    content = style_path.read_text()

    # Check for :root block with custom properties
    assert ":root" in content, ":root block not found"

    # Check essential light mode variables
    required_vars = [
        "--color-bg-primary",
        "--color-bg-secondary",
        "--color-text-primary",
        "--color-text-secondary",
        "--color-accent-primary",
        "--color-border-primary",
        "--color-msg-user-bg",
        "--color-msg-assistant-bg",
        "--color-code-bg",
        "--color-code-inline-bg",
    ]

    for var in required_vars:
        assert var in content, f"CSS variable '{var}' not found in :root"


def test_css_has_dark_theme_variables():
    """Verify style.css defines dark theme via [data-theme='dark']"""
    style_path = UI_DIR / "style.css"
    content = style_path.read_text()

    # Check for dark theme selector
    assert '[data-theme="dark"]' in content, "Dark theme selector not found"

    # Find the dark theme block
    dark_block_match = re.search(
        r'\[data-theme="dark"\]\s*\{([^}]+(?:\{[^}]*\}[^}]*)*)\}',
        content,
        re.DOTALL
    )
    assert dark_block_match, "Dark theme block not found"

    dark_block = dark_block_match.group(1)

    # Check that dark theme overrides key variables
    dark_vars = [
        "--color-bg-primary",
        "--color-bg-secondary",
        "--color-text-primary",
        "--color-accent-primary",
        "--color-msg-user-bg",
        "--color-msg-assistant-bg",
        "--color-code-bg",
    ]

    for var in dark_vars:
        assert var in dark_block, f"Dark theme doesn't override '{var}'"


def test_dark_mode_uses_navy_charcoal_not_pure_black():
    """Verify dark mode background is navy/charcoal, not pure black"""
    style_path = UI_DIR / "style.css"
    content = style_path.read_text()

    # Extract the dark theme block
    dark_block_match = re.search(
        r'\[data-theme="dark"\]\s*\{(.*?)\n\}',
        content,
        re.DOTALL
    )
    assert dark_block_match, "Dark theme block not found"

    dark_block = dark_block_match.group(1)

    # Pure black #000000 or #000 should NOT be the primary background
    # Find --color-bg-primary in dark block
    bg_match = re.search(r'--color-bg-primary:\s*(#[0-9a-fA-F]+)', dark_block)
    assert bg_match, "--color-bg-primary not found in dark theme"

    bg_color = bg_match.group(1).lower()
    assert bg_color != "#000000" and bg_color != "#000", \
        f"Dark mode uses pure black ({bg_color}), should use navy/charcoal"


def test_no_hardcoded_colors_in_main_styles():
    """Verify main CSS rules use variables, not hardcoded hex colors.

    Only checks key selectors that should use variables. Allows hardcoded
    white (#fff/#ffffff) for text on colored backgrounds (buttons).
    """
    style_path = UI_DIR / "style.css"
    content = style_path.read_text()

    # Remove :root and [data-theme] blocks (they define variables with hex values)
    cleaned = re.sub(r':root\s*\{[^}]+(?:\{[^}]*\}[^}]*)*\}', '', content, flags=re.DOTALL)
    cleaned = re.sub(r'\[data-theme="dark"\]\s*\{[^}]+(?:\{[^}]*\}[^}]*)*\}', '', cleaned, flags=re.DOTALL)

    # Remove comments
    cleaned = re.sub(r'/\*.*?\*/', '', cleaned, flags=re.DOTALL)

    # Find all property declarations with hex colors (but not in variable definitions)
    hex_pattern = re.compile(r'(?<!-)#[0-9a-fA-F]{3,8}(?!\w)')
    matches = hex_pattern.findall(cleaned)

    # Filter: Allow #ffffff and #fff (white for button text) - these are constant
    non_white = [m for m in matches if m.lower() not in ('#ffffff', '#fff')]

    # Should have zero non-white hardcoded hex colors
    assert len(non_white) == 0, \
        f"Found {len(non_white)} hardcoded hex color(s) outside variables: {non_white[:10]}"


def test_css_uses_var_references():
    """Verify CSS rules use var() references for colors"""
    style_path = UI_DIR / "style.css"
    content = style_path.read_text()

    # Count var() usages (should be many)
    var_count = content.count("var(--color-")
    assert var_count >= 50, \
        f"Only {var_count} var(--color-) usages found, expected >= 50"


# ============================================================================
# Theme Toggle Tests
# ============================================================================

def test_html_has_theme_toggle_button():
    """Verify index.html contains a dark mode toggle button"""
    index_path = UI_DIR / "index.html"
    assert index_path.exists(), "index.html not found"

    content = index_path.read_text()

    # Check for theme toggle button
    assert "theme-toggle" in content, "Theme toggle button not found"
    assert "id=\"theme-toggle-btn\"" in content, "Theme toggle button ID not found"


def test_html_has_sun_and_moon_icons():
    """Verify toggle button has both sun and moon SVG icons"""
    index_path = UI_DIR / "index.html"
    content = index_path.read_text()

    # Check for sun icon
    assert "icon-sun" in content, "Sun icon not found"

    # Check for moon icon
    assert "icon-moon" in content, "Moon icon not found"

    # Check for SVG elements
    assert "<svg" in content, "SVG elements not found"


def test_html_has_inline_theme_script():
    """Verify index.html has inline script to prevent flash of wrong theme"""
    index_path = UI_DIR / "index.html"
    content = index_path.read_text()

    # Should have an inline script in <head> that sets data-theme
    head_section = content.split("</head>")[0]
    assert "data-theme" in head_section, \
        "No inline theme initialization script in <head>"
    assert "localStorage" in head_section, \
        "Inline theme script doesn't check localStorage"
    assert "prefers-color-scheme" in head_section, \
        "Inline theme script doesn't detect system preference"


# ============================================================================
# JavaScript Dark Mode Logic Tests
# ============================================================================

def test_app_js_has_theme_functions():
    """Verify app.js has theme management functions"""
    app_js_path = UI_DIR / "app.js"
    assert app_js_path.exists(), "app.js not found"

    content = app_js_path.read_text()

    # Check for key theme functions
    assert "function initTheme" in content, "initTheme() function not found"
    assert "function setTheme" in content, "setTheme() function not found"
    assert "function toggleTheme" in content, "toggleTheme() function not found"


def test_app_js_persists_theme_to_localstorage():
    """Verify theme toggle saves to localStorage"""
    app_js_path = UI_DIR / "app.js"
    content = app_js_path.read_text()

    # toggleTheme should save to localStorage
    toggle_func = re.search(
        r'function toggleTheme\(\)\s*\{.*?\n\}',
        content,
        re.DOTALL
    )
    assert toggle_func, "toggleTheme function not found"

    func_body = toggle_func.group()
    assert "localStorage.setItem" in func_body, \
        "toggleTheme doesn't persist to localStorage"
    assert "'theme'" in func_body or '"theme"' in func_body, \
        "localStorage key should be 'theme'"


def test_app_js_detects_system_preference():
    """Verify app.js detects prefers-color-scheme media query"""
    app_js_path = UI_DIR / "app.js"
    content = app_js_path.read_text()

    # Check for media query detection
    assert "prefers-color-scheme" in content, \
        "System preference detection not found"
    assert "matchMedia" in content, \
        "matchMedia not used for system preference"


def test_app_js_sets_data_theme_attribute():
    """Verify app.js sets data-theme attribute on document"""
    app_js_path = UI_DIR / "app.js"
    content = app_js_path.read_text()

    # Check for data-theme attribute manipulation
    assert "data-theme" in content, "data-theme attribute not found in app.js"
    assert "setAttribute" in content or "dataset.theme" in content, \
        "No DOM attribute setting for theme"


def test_app_js_has_theme_toggle_event_listener():
    """Verify theme toggle button has click event listener"""
    app_js_path = UI_DIR / "app.js"
    content = app_js_path.read_text()

    # Check that toggle button has event listener
    assert "themeToggleBtn" in content, "Theme toggle button DOM reference not found"
    assert "toggleTheme" in content, "toggleTheme handler not connected"


def test_app_js_listens_for_system_preference_changes():
    """Verify app.js listens for runtime system preference changes"""
    app_js_path = UI_DIR / "app.js"
    content = app_js_path.read_text()

    # Should add an event listener for 'change' on the matchMedia query
    assert "addEventListener" in content and "prefers-color-scheme" in content, \
        "Not listening for system preference changes"


# ============================================================================
# CSS Theme Transition Tests
# ============================================================================

def test_css_has_smooth_theme_transitions():
    """Verify CSS includes transition properties for smooth theme switching"""
    style_path = UI_DIR / "style.css"
    content = style_path.read_text()

    # Check for transition-theme variable
    assert "--transition-theme" in content, \
        "No --transition-theme variable defined"

    # Check body has theme transition
    body_match = re.search(r'body\s*\{[^}]+\}', content, re.DOTALL)
    assert body_match, "body {} block not found"

    body_styles = body_match.group()
    assert "transition" in body_styles, \
        "body element doesn't have theme transition"


def test_css_theme_toggle_shows_correct_icon():
    """Verify CSS shows moon icon in light mode, sun icon in dark mode"""
    style_path = UI_DIR / "style.css"
    content = style_path.read_text()

    # Light mode: moon visible, sun hidden
    assert ".theme-toggle .icon-sun" in content, "Sun icon style rule missing"
    assert ".theme-toggle .icon-moon" in content, "Moon icon style rule missing"

    # Dark mode: sun visible, moon hidden
    assert '[data-theme="dark"] .theme-toggle .icon-sun' in content, \
        "Dark mode sun icon rule missing"
    assert '[data-theme="dark"] .theme-toggle .icon-moon' in content, \
        "Dark mode moon icon rule missing"


# ============================================================================
# Code Block Theme Compatibility Tests
# ============================================================================

def test_css_code_blocks_themed():
    """Verify code blocks use theme variables"""
    style_path = UI_DIR / "style.css"
    content = style_path.read_text()

    # Code blocks should use variables
    code_section = re.search(
        r'\.message\.assistant\s+code\s*\{[^}]+\}',
        content,
        re.DOTALL
    )
    assert code_section, "Code block styling not found"

    code_styles = code_section.group()
    assert "var(--color-code-inline-bg)" in code_styles, \
        "Inline code doesn't use theme variable for background"
    assert "var(--color-code-inline-text)" in code_styles, \
        "Inline code doesn't use theme variable for text"

    # Pre blocks should use variables
    pre_section = re.search(
        r'\.message\.assistant\s+pre\s*\{[^}]+\}',
        content,
        re.DOTALL
    )
    assert pre_section, "Pre block styling not found"

    pre_styles = pre_section.group()
    assert "var(--color-code-bg)" in pre_styles, \
        "Pre block doesn't use theme variable for background"


# ============================================================================
# Genesis Branding Tests
# ============================================================================

def test_html_has_genesis_branding():
    """Verify index.html displays 'Genesis' as the title"""
    index_path = UI_DIR / "index.html"
    content = index_path.read_text()

    # Check page title
    assert "<title>Genesis</title>" in content, \
        "Page title should be 'Genesis'"

    # Check header text
    assert "Genesis" in content, "Genesis branding not found in header"
    assert "genesis-mark" in content, "Genesis brand mark styling not found"


def test_html_no_generic_ai_assistant_title():
    """Verify 'AI Assistant' is no longer the main title"""
    index_path = UI_DIR / "index.html"
    content = index_path.read_text()

    # The <h1> should not say "AI Assistant"
    h1_match = re.search(r'<h1[^>]*>(.*?)</h1>', content, re.DOTALL)
    assert h1_match, "<h1> tag not found"

    h1_text = h1_match.group(1)
    # Allow "AI Assistant" to appear elsewhere, just not as the main heading text
    assert "AI Assistant" not in h1_text, \
        f"Header still shows 'AI Assistant': {h1_text}"


def test_css_has_genesis_mark_style():
    """Verify CSS has .genesis-mark styling for branding"""
    style_path = UI_DIR / "style.css"
    content = style_path.read_text()

    assert ".genesis-mark" in content, \
        ".genesis-mark CSS class not found"


# ============================================================================
# Typography Tests
# ============================================================================

def test_css_has_typography_variables():
    """Verify CSS defines typography-related variables"""
    style_path = UI_DIR / "style.css"
    content = style_path.read_text()

    required_vars = [
        "--font-family",
        "--font-family-mono",
        "--font-size-base",
        "--font-size-md",
        "--font-size-lg",
        "--line-height-normal",
        "--line-height-relaxed",
    ]

    for var in required_vars:
        assert var in content, f"Typography variable '{var}' not found"


def test_css_message_font_size_adequate():
    """Verify message text uses at least the base font size variable"""
    style_path = UI_DIR / "style.css"
    content = style_path.read_text()

    # .message should use font-size variable
    message_match = re.search(
        r'\.message\s*\{[^}]+\}',
        content,
        re.DOTALL
    )
    assert message_match, ".message {} block not found"

    message_styles = message_match.group()
    assert "font-size" in message_styles, ".message missing font-size"
    assert "var(--font-size" in message_styles, \
        ".message font-size should use a CSS variable"


def test_css_message_line_height():
    """Verify messages have proper line-height for readability"""
    style_path = UI_DIR / "style.css"
    content = style_path.read_text()

    message_match = re.search(
        r'\.message\s*\{[^}]+\}',
        content,
        re.DOTALL
    )
    assert message_match, ".message {} block not found"

    message_styles = message_match.group()
    assert "line-height" in message_styles, ".message missing line-height"
    assert "var(--line-height" in message_styles, \
        ".message line-height should use a CSS variable"


# ============================================================================
# Component Theme Coverage Tests
# ============================================================================

def test_all_panels_use_theme_variables():
    """Verify all major panels reference theme variables"""
    style_path = UI_DIR / "style.css"
    content = style_path.read_text()

    # Check key component selectors use var()
    components = [
        ".chat-container",
        ".status-panel",
        ".conversation-sidebar",
        ".modal-content",
        ".input-area",
        "#message-input",
    ]

    for comp in components:
        # Find the component block
        pattern = re.escape(comp) + r'\s*\{[^}]+\}'
        match = re.search(pattern, content, re.DOTALL)
        assert match, f"Component '{comp}' CSS block not found"

        styles = match.group()
        assert "var(--" in styles, \
            f"Component '{comp}' doesn't use CSS variables for theming"


def test_dark_theme_defines_all_major_color_groups():
    """Verify dark theme covers all major color groups"""
    style_path = UI_DIR / "style.css"
    content = style_path.read_text()

    dark_block_match = re.search(
        r'\[data-theme="dark"\]\s*\{(.*?)\n\}',
        content,
        re.DOTALL
    )
    assert dark_block_match, "Dark theme block not found"

    dark_block = dark_block_match.group(1)

    color_groups = [
        "--color-bg-",        # Background colors
        "--color-text-",      # Text colors
        "--color-accent-",    # Accent colors
        "--color-border-",    # Border colors
        "--color-msg-",       # Message colors
        "--color-code-",      # Code block colors
        "--color-btn-",       # Button colors
        "--color-key-",       # Key status colors
    ]

    for group in color_groups:
        assert group in dark_block, \
            f"Dark theme missing color group '{group}'"
