"""
Tests for Persona Switcher UI (Issue #38)

Validates that the persona switcher UI is properly implemented in the frontend.
"""

import pytest
from pathlib import Path


@pytest.fixture
def ui_files():
    """Return paths to UI files."""
    ui_dir = Path(__file__).parent.parent / "ui"
    return {
        "html": ui_dir / "index.html",
        "js": ui_dir / "app.js",
        "css": ui_dir / "style.css",
    }


# ============================================================================
# HTML Structure Tests
# ============================================================================

def test_persona_header_exists(ui_files):
    """Test that persona header exists in HTML."""
    html_content = ui_files["html"].read_text()

    assert 'class="persona-header"' in html_content, "Persona header should exist"
    assert 'id="persona-selector-btn"' in html_content, "Persona selector button should exist"
    assert 'id="current-persona-name"' in html_content, "Current persona name display should exist"
    assert 'id="create-persona-btn"' in html_content, "Create persona button should exist"


def test_persona_dropdown_menu_exists(ui_files):
    """Test that persona dropdown menu exists in HTML."""
    html_content = ui_files["html"].read_text()

    assert 'id="persona-dropdown"' in html_content, "Persona dropdown should exist"
    assert 'id="persona-list"' in html_content, "Persona list container should exist"


def test_persona_modal_exists(ui_files):
    """Test that persona modal exists in HTML."""
    html_content = ui_files["html"].read_text()

    assert 'id="persona-modal"' in html_content, "Persona modal should exist"
    assert 'id="persona-modal-title"' in html_content, "Persona modal title should exist"
    assert 'id="persona-name-input"' in html_content, "Persona name input should exist"
    assert 'id="persona-description-input"' in html_content, "Persona description input should exist"
    assert 'id="persona-prompt-input"' in html_content, "Persona prompt input should exist"
    assert 'id="persona-save-btn"' in html_content, "Persona save button should exist"


def test_persona_modal_has_character_counter(ui_files):
    """Test that persona prompt has character counter."""
    html_content = ui_files["html"].read_text()

    assert 'id="persona-prompt-chars"' in html_content, "Character counter should exist"
    assert '/4000 characters' in html_content, "Character limit should be displayed"


def test_persona_modal_has_max_length(ui_files):
    """Test that input fields have maxlength attributes."""
    html_content = ui_files["html"].read_text()

    assert 'maxlength="50"' in html_content, "Name input should have 50 char limit"
    assert 'maxlength="100"' in html_content, "Description should have 100 char limit"
    assert 'maxlength="4000"' in html_content, "System prompt should have 4000 char limit"


# ============================================================================
# CSS Style Tests
# ============================================================================

def test_persona_header_styles_exist(ui_files):
    """Test that persona header CSS styles exist."""
    css_content = ui_files["css"].read_text()

    assert '.persona-header' in css_content, ".persona-header style should exist"
    assert '.persona-selector-btn' in css_content, ".persona-selector-btn style should exist"
    assert '.create-persona-btn' in css_content, ".create-persona-btn style should exist"


def test_persona_dropdown_styles_exist(ui_files):
    """Test that persona dropdown CSS styles exist."""
    css_content = ui_files["css"].read_text()

    assert '.persona-dropdown' in css_content, ".persona-dropdown style should exist"
    assert '.persona-list' in css_content, ".persona-list style should exist"
    assert '.persona-item' in css_content, ".persona-item style should exist"


def test_persona_item_has_hover_state(ui_files):
    """Test that persona items have hover styles."""
    css_content = ui_files["css"].read_text()

    assert '.persona-item:hover' in css_content, "Persona item should have hover state"


def test_persona_styles_use_theme_variables(ui_files):
    """Test that persona styles use CSS custom properties for theming."""
    css_content = ui_files["css"].read_text()

    # Find persona section
    persona_section_start = css_content.find('Persona Switcher')
    persona_section_end = css_content.find('Keyboard Shortcuts')

    if persona_section_start == -1 or persona_section_end == -1:
        pytest.fail("Could not find Persona Switcher section in CSS")

    persona_section = css_content[persona_section_start:persona_section_end]

    # Check that it uses CSS variables
    assert 'var(--color-' in persona_section, "Persona styles should use color variables"
    assert 'var(--font-' in persona_section, "Persona styles should use font variables"
    assert 'var(--radius-' in persona_section, "Persona styles should use radius variables"


def test_persona_dropdown_has_animation(ui_files):
    """Test that persona dropdown has animation."""
    css_content = ui_files["css"].read_text()

    assert '@keyframes dropdown-appear' in css_content, "Dropdown animation should exist"
    assert 'animation: dropdown-appear' in css_content, "Dropdown should use animation"


def test_persona_mobile_responsive_styles_exist(ui_files):
    """Test that mobile-responsive styles exist for persona switcher."""
    css_content = ui_files["css"].read_text()

    # Check for mobile breakpoint (600px)
    mobile_section = css_content[css_content.rfind('@media (max-width: 600px)'):]

    assert '.persona-header' in mobile_section, "Persona header should have mobile styles"
    assert '.persona-selector-btn' in mobile_section, "Persona selector should have mobile styles"
    assert 'min-height: 44px' in mobile_section, "Touch targets should be 44px on mobile"


# ============================================================================
# JavaScript Functionality Tests
# ============================================================================

def test_persona_state_variables_exist(ui_files):
    """Test that persona state variables are defined."""
    js_content = ui_files["js"].read_text()

    assert 'let personas' in js_content, "personas array should be defined"
    assert 'let currentPersonaId' in js_content, "currentPersonaId should be defined"


def test_persona_dom_elements_defined(ui_files):
    """Test that persona DOM elements are referenced in JS."""
    js_content = ui_files["js"].read_text()

    required_elements = [
        'personaSelectorBtn',
        'createPersonaBtn',
        'personaDropdown',
        'personaList',
        'currentPersonaName',
        'personaModal',
        'personaNameInput',
        'personaDescInput',
        'personaPromptInput',
    ]

    for element in required_elements:
        assert element in js_content, f"{element} should be defined in JS"


def test_persona_functions_exist(ui_files):
    """Test that key persona functions exist."""
    js_content = ui_files["js"].read_text()

    required_functions = [
        'async function loadPersonas(',
        'async function loadConversationPersona(',
        'function updateCurrentPersonaDisplay(',
        'function renderPersonaList(',
        'function togglePersonaDropdown(',
        'async function switchPersona(',
        'function openCreatePersonaModal(',
        'function openEditPersonaModal(',
        'async function savePersona(',
        'function confirmDeletePersona(',
        'async function deletePersona(',
    ]

    for func in required_functions:
        assert func in js_content, f"Function '{func}' should exist"


def test_persona_event_listeners_registered(ui_files):
    """Test that persona event listeners are registered."""
    js_content = ui_files["js"].read_text()

    # Check event listener registrations
    assert "personaSelectorBtn.addEventListener('click', togglePersonaDropdown)" in js_content, \
        "Persona selector should have click listener"
    assert "createPersonaBtn.addEventListener('click', openCreatePersonaModal)" in js_content, \
        "Create button should have click listener"
    assert "personaSaveBtn.addEventListener('click', savePersona)" in js_content, \
        "Save button should have click listener"


def test_persona_loads_on_init(ui_files):
    """Test that personas are loaded on page init."""
    js_content = ui_files["js"].read_text()

    # Check that loadPersonas() is called in DOMContentLoaded
    assert 'loadPersonas()' in js_content, "loadPersonas should be called on init"


def test_persona_api_endpoints_used(ui_files):
    """Test that correct API endpoints are used."""
    js_content = ui_files["js"].read_text()

    assert "'/api/personas'" in js_content, "Should call /api/personas endpoint"
    # Template literal uses backticks in JavaScript
    assert "`/api/conversations/${currentConversationId}/persona`" in js_content, \
        "Should call conversation persona endpoint"


def test_persona_uses_fetch_not_xhr(ui_files):
    """Test that persona code uses modern fetch API."""
    js_content = ui_files["js"].read_text()

    # Find persona section
    persona_section_start = js_content.find('// Persona Switcher Functions')
    persona_section_end = js_content.find('// Settings functions')

    if persona_section_start == -1:
        pytest.fail("Could not find Persona Switcher Functions section")

    persona_section = js_content[persona_section_start:persona_section_end]

    assert 'await fetch(' in persona_section, "Should use fetch API"
    assert 'XMLHttpRequest' not in persona_section, "Should not use XMLHttpRequest"


def test_persona_delete_uses_dom_methods_not_innerHTML(ui_files):
    """Test that confirmDeletePersona uses safe DOM methods."""
    js_content = ui_files["js"].read_text()

    # Find confirmDeletePersona function
    confirm_func_start = js_content.find('function confirmDeletePersona(')
    confirm_func_end = js_content.find('\n}\n', confirm_func_start) + 2

    if confirm_func_start == -1:
        pytest.fail("Could not find confirmDeletePersona function")

    confirm_func = js_content[confirm_func_start:confirm_func_end]

    # Should use createElement, not innerHTML
    assert 'document.createElement(' in confirm_func, "Should use createElement"
    assert 'textContent' in confirm_func, "Should use textContent for text"
    assert 'innerHTML' not in confirm_func, "Should not use innerHTML (XSS risk)"


def test_render_persona_list_uses_safe_methods(ui_files):
    """Test that renderPersonaList uses safe DOM manipulation."""
    js_content = ui_files["js"].read_text()

    # Find renderPersonaList function
    render_func_start = js_content.find('function renderPersonaList(')
    render_func_end = js_content.find('\n}\n', render_func_start) + 2

    if render_func_start == -1:
        pytest.fail("Could not find renderPersonaList function")

    render_func = js_content[render_func_start:render_func_end]

    # Should use createElement and textContent
    assert 'document.createElement(' in render_func, "Should use createElement"
    assert 'textContent' in render_func, "Should use textContent"


def test_character_counter_updates_dynamically(ui_files):
    """Test that character counter has input event listener."""
    js_content = ui_files["js"].read_text()

    assert "personaPromptInput.addEventListener('input', updatePersonaCharCount)" in js_content, \
        "Character counter should update on input"
    assert 'function updatePersonaCharCount(' in js_content, \
        "updatePersonaCharCount function should exist"


def test_persona_close_on_outside_click(ui_files):
    """Test that persona dropdown closes when clicking outside."""
    js_content = ui_files["js"].read_text()

    # Should have document click listener for closing dropdown
    assert "document.addEventListener('click', (e) =>" in js_content, \
        "Should listen for document clicks"
    assert "!personaSelectorBtn.contains(e.target) && !personaDropdown.contains(e.target)" in js_content, \
        "Should check if click is outside dropdown"


# ============================================================================
# Integration Tests
# ============================================================================

def test_persona_switcher_appears_before_messages(ui_files):
    """Test that persona header appears before messages in HTML structure."""
    html_content = ui_files["html"].read_text()

    persona_header_pos = html_content.find('class="persona-header"')
    messages_pos = html_content.find('id="messages"')

    assert persona_header_pos > 0, "Persona header should exist"
    assert messages_pos > 0, "Messages container should exist"
    assert persona_header_pos < messages_pos, \
        "Persona header should appear before messages container"


def test_persona_switcher_in_chat_container(ui_files):
    """Test that persona switcher is inside chat-container."""
    html_content = ui_files["html"].read_text()

    chat_container_pos = html_content.find('class="chat-container"')
    persona_header_pos = html_content.find('class="persona-header"')
    messages_pos = html_content.find('id="messages"')

    assert chat_container_pos > 0, "Chat container should exist"
    assert persona_header_pos > 0, "Persona header should exist"
    assert messages_pos > 0, "Messages container should exist"

    # Persona header should be between chat-container and messages
    assert persona_header_pos > chat_container_pos, \
        "Persona header should be after chat-container start"
    assert persona_header_pos < messages_pos, \
        "Persona header should be before messages container"


def test_persona_loads_when_conversation_switches(ui_files):
    """Test that persona reloads when switching conversations."""
    js_content = ui_files["js"].read_text()

    # Find switchConversation function
    switch_func_start = js_content.find('async function switchConversation(')
    switch_func_end = js_content.find('\n}\n', switch_func_start) + 2

    if switch_func_start == -1:
        pytest.fail("Could not find switchConversation function")

    switch_func = js_content[switch_func_start:switch_func_end]

    assert 'await loadConversationPersona()' in switch_func, \
        "Should reload persona when switching conversations"
