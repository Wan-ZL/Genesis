"""
Tests for keyboard shortcuts UI functionality.

Validates that keyboard shortcuts are properly implemented in the frontend.
"""

import pytest
from pathlib import Path


@pytest.fixture
def ui_files():
    """Return paths to UI files."""
    ui_dir = Path(__file__).parent.parent / "ui"
    return {
        "html": ui_dir / "index.html",
        "js": ui_dir / "shortcuts.js",
        "css": ui_dir / "style.css",
    }


def test_shortcuts_js_exists(ui_files):
    """Test that shortcuts.js file exists."""
    assert ui_files["js"].exists(), "shortcuts.js file should exist"


def test_shortcuts_js_included_in_html(ui_files):
    """Test that shortcuts.js is included in index.html."""
    html_content = ui_files["html"].read_text()
    assert 'src="/static/shortcuts.js"' in html_content, "shortcuts.js should be included in HTML"


def test_quick_switcher_html_exists(ui_files):
    """Test that quick switcher HTML structure exists."""
    html_content = ui_files["html"].read_text()

    assert 'id="quick-switcher"' in html_content, "Quick switcher modal should exist"
    assert 'id="quick-switcher-search"' in html_content, "Quick switcher search input should exist"
    assert 'id="quick-switcher-list"' in html_content, "Quick switcher list container should exist"


def test_shortcut_help_html_exists(ui_files):
    """Test that shortcut help modal HTML structure exists."""
    html_content = ui_files["html"].read_text()

    assert 'id="shortcut-help"' in html_content, "Shortcut help modal should exist"
    assert 'Keyboard Shortcuts' in html_content, "Shortcut help title should exist"
    assert 'kbd' in html_content, "Keyboard shortcut elements should exist"


def test_all_shortcuts_documented_in_help(ui_files):
    """Test that all major shortcuts are documented in help modal."""
    html_content = ui_files["html"].read_text()

    # Check for documented shortcuts
    shortcuts = [
        'Cmd/Ctrl + N',  # New Conversation
        'Cmd/Ctrl + K',  # Quick Switcher
        'Cmd/Ctrl + ,',  # Settings
        'Cmd/Ctrl + Shift + D',  # Dark Mode
        'Escape',  # Close Modal
        'Cmd/Ctrl + /',  # Show Shortcuts
    ]

    for shortcut in shortcuts:
        assert shortcut in html_content, f"Shortcut '{shortcut}' should be documented in help modal"


def test_shortcut_registry_structure(ui_files):
    """Test that shortcuts.js has proper shortcut registry."""
    js_content = ui_files["js"].read_text()

    # Check for shortcut registry
    assert 'const shortcuts = {' in js_content, "Shortcut registry should exist"

    # Check for all registered shortcuts
    shortcut_keys = [
        "'mod+n':",  # New Conversation
        "'mod+k':",  # Quick Switcher
        "'mod+,':",  # Settings
        "'mod+shift+d':",  # Dark Mode
        "'escape':",  # Close Modal
        "'mod+/':",  # Show Shortcuts
    ]

    for key in shortcut_keys:
        assert key in js_content, f"Shortcut key {key} should be registered"


def test_keyboard_event_handler_exists(ui_files):
    """Test that global keyboard event handler exists."""
    js_content = ui_files["js"].read_text()

    assert 'function handleKeydown(event)' in js_content, "Keyboard event handler should exist"
    assert 'document.addEventListener(\'keydown\', handleKeydown)' in js_content, \
        "Keyboard handler should be registered"


def test_typing_detection_logic(ui_files):
    """Test that shortcuts don't fire when typing in inputs."""
    js_content = ui_files["js"].read_text()

    assert 'function isTyping(event)' in js_content, "Typing detection function should exist"
    assert 'if (event.key !== \'Escape\' && isTyping(event))' in js_content, \
        "Should skip shortcuts when typing (except Escape)"
    assert 'tagName === \'input\'' in js_content, "Should detect input fields"
    assert 'tagName === \'textarea\'' in js_content, "Should detect textarea fields"


def test_cross_platform_modifier_key(ui_files):
    """Test that shortcuts use cross-platform modifier key detection."""
    js_content = ui_files["js"].read_text()

    assert 'metaKey' in js_content, "Should check for Cmd key (Mac)"
    assert 'ctrlKey' in js_content, "Should check for Ctrl key (Windows/Linux)"
    assert 'function isModifierPressed(event)' in js_content, \
        "Should have modifier detection function"


def test_quick_switcher_functions(ui_files):
    """Test that quick switcher functions are implemented."""
    js_content = ui_files["js"].read_text()

    functions = [
        'function toggleQuickSwitcher()',
        'function openQuickSwitcher()',
        'function closeQuickSwitcher()',
        'function renderQuickSwitcherList',
        'function handleQuickSwitcherSearch',
        'function handleQuickSwitcherKeydown',
    ]

    for func in functions:
        assert func in js_content, f"Function '{func}' should be implemented"


def test_shortcut_help_functions(ui_files):
    """Test that shortcut help modal functions are implemented."""
    js_content = ui_files["js"].read_text()

    functions = [
        'function toggleShortcutHelp()',
        'function openShortcutHelp()',
        'function closeShortcutHelp()',
    ]

    for func in functions:
        assert func in js_content, f"Function '{func}' should be implemented"


def test_close_any_modal_function(ui_files):
    """Test that Escape key closes modals properly."""
    js_content = ui_files["js"].read_text()

    assert 'function closeAnyOpenModal()' in js_content, \
        "Close any modal function should exist"
    assert 'quickSwitcherOpen' in js_content, "Should check quick switcher state"
    assert 'shortcutHelpOpen' in js_content, "Should check shortcut help state"
    assert 'settingsModal' in js_content, "Should check settings modal state"


def test_quick_switcher_styles_exist(ui_files):
    """Test that quick switcher CSS styles exist."""
    css_content = ui_files["css"].read_text()

    styles = [
        '.quick-switcher-content',
        '.quick-switcher-search',
        '.quick-switcher-list',
        '.quick-switcher-item',
        '.quick-switcher-item-title',
        '.quick-switcher-item-preview',
    ]

    for style in styles:
        assert style in css_content, f"CSS class '{style}' should be defined"


def test_shortcut_help_styles_exist(ui_files):
    """Test that shortcut help CSS styles exist."""
    css_content = ui_files["css"].read_text()

    styles = [
        '.shortcut-grid',
        '.shortcut-item',
        '.shortcut-key',
        '.shortcut-desc',
    ]

    for style in styles:
        assert style in css_content, f"CSS class '{style}' should be defined"


def test_keyboard_kbd_styling(ui_files):
    """Test that keyboard key elements have proper styling."""
    css_content = ui_files["css"].read_text()

    # kbd elements should have monospace font and button-like appearance
    assert '.shortcut-key' in css_content, "Keyboard key style should exist"
    assert 'font-family: var(--font-family-mono)' in css_content, \
        "Keyboard keys should use monospace font"


def test_tooltips_added_to_buttons(ui_files):
    """Test that relevant buttons have shortcut hints in tooltips."""
    html_content = ui_files["html"].read_text()

    # Check for shortcut hints in tooltips
    tooltip_hints = [
        'Cmd/Ctrl+N',  # New Conversation button
        'Cmd/Ctrl+,',  # Settings button
        'Cmd/Ctrl+Shift+D',  # Dark mode button
    ]

    for hint in tooltip_hints:
        assert hint in html_content, f"Tooltip hint '{hint}' should be in HTML"


def test_arrow_navigation_in_quick_switcher(ui_files):
    """Test that arrow keys navigate in quick switcher."""
    js_content = ui_files["js"].read_text()

    assert 'ArrowDown' in js_content, "Arrow down should be handled"
    assert 'ArrowUp' in js_content, "Arrow up should be handled"
    assert 'scrollIntoView' in js_content, "Should scroll active item into view"
    assert '.active' in js_content, "Should track active item"


def test_enter_key_activates_selection(ui_files):
    """Test that Enter key activates the selected item."""
    js_content = ui_files["js"].read_text()

    assert "event.key === 'Enter'" in js_content, "Enter key should be handled"
    assert 'click()' in js_content, "Enter should trigger click on active item"


def test_no_xss_vulnerability(ui_files):
    """Test that shortcuts.js doesn't use unsafe innerHTML."""
    js_content = ui_files["js"].read_text()

    # Should use safe DOM methods instead of innerHTML
    assert 'textContent' in js_content, "Should use textContent for text"
    assert 'createElement' in js_content, "Should use createElement for DOM manipulation"

    # innerHTML should not be used for user-generated content
    # (It's OK if innerHTML is not present at all)
    if 'innerHTML' in js_content:
        # If innerHTML is used, it should only be for static content
        assert 'innerHTML = \'\'' not in js_content or 'removeChild' in js_content, \
            "Should prefer safe DOM methods over innerHTML"


def test_escape_prevents_default(ui_files):
    """Test that Escape key prevents default browser behavior."""
    js_content = ui_files["js"].read_text()

    # Escape should call preventDefault to avoid browser's default behavior
    assert 'event.preventDefault()' in js_content, \
        "Should prevent default behavior for shortcuts"


def test_shortcuts_script_loaded_before_app(ui_files):
    """Test that shortcuts.js is loaded before app.js."""
    html_content = ui_files["html"].read_text()

    # Find positions of script tags
    shortcuts_pos = html_content.find('src="/static/shortcuts.js"')
    app_pos = html_content.find('src="/static/app.js"')

    assert shortcuts_pos < app_pos, \
        "shortcuts.js should be loaded before app.js to ensure functions are available"


def test_responsive_styles_for_shortcuts(ui_files):
    """Test that shortcut modal is mobile-friendly."""
    css_content = ui_files["css"].read_text()

    # Check for mobile media query
    assert '@media (max-width: 600px)' in css_content, \
        "Should have mobile-specific styles"

    # Check for responsive quick switcher
    mobile_section = css_content[css_content.find('@media (max-width: 600px)'):]
    assert '.quick-switcher-content' in mobile_section or \
           '.shortcut-grid' in mobile_section, \
        "Shortcut UI should have mobile-specific styles"
