/**
 * Keyboard Shortcuts for Genesis AI Assistant
 *
 * Global keyboard shortcuts for power users.
 * Cross-platform: uses Cmd on Mac, Ctrl on Windows/Linux.
 */

// Shortcut registry
const shortcuts = {
    'mod+n': {
        name: 'New Conversation',
        action: () => {
            if (typeof createNewConversation === 'function') {
                createNewConversation();
            }
        }
    },
    'mod+k': {
        name: 'Quick Switcher',
        action: () => {
            toggleQuickSwitcher();
        }
    },
    'mod+,': {
        name: 'Open Settings',
        action: () => {
            if (typeof openSettings === 'function') {
                openSettings();
            }
        }
    },
    'mod+shift+d': {
        name: 'Toggle Dark Mode',
        action: () => {
            if (typeof toggleTheme === 'function') {
                toggleTheme();
            }
        }
    },
    'escape': {
        name: 'Close Modal/Overlay',
        action: () => {
            closeAnyOpenModal();
        }
    },
    'mod+/': {
        name: 'Show Shortcuts',
        action: () => {
            toggleShortcutHelp();
        }
    }
};

/**
 * Check if user is currently typing in an input field
 */
function isTyping(event) {
    const target = event.target;
    const tagName = target.tagName.toLowerCase();
    const isEditable = target.isContentEditable;

    return (
        tagName === 'input' ||
        tagName === 'textarea' ||
        tagName === 'select' ||
        isEditable
    );
}

/**
 * Check if the modifier key (Cmd/Ctrl) is pressed
 */
function isModifierPressed(event) {
    // metaKey = Cmd on Mac, ctrlKey = Ctrl on Windows/Linux
    return event.metaKey || event.ctrlKey;
}

/**
 * Get the shortcut key from the event
 */
function getShortcutKey(event) {
    const parts = [];

    if (isModifierPressed(event)) {
        parts.push('mod');
    }
    if (event.shiftKey) {
        parts.push('shift');
    }
    if (event.altKey) {
        parts.push('alt');
    }

    // Get the actual key
    const key = event.key.toLowerCase();
    parts.push(key);

    return parts.join('+');
}

/**
 * Handle global keydown events
 */
function handleKeydown(event) {
    // Don't trigger shortcuts when user is typing in an input field
    // Exception: Escape should work everywhere
    if (event.key !== 'Escape' && isTyping(event)) {
        return;
    }

    const shortcutKey = getShortcutKey(event);
    const shortcut = shortcuts[shortcutKey];

    if (shortcut) {
        event.preventDefault();
        shortcut.action();
    }
}

// ============================================================================
// Quick Switcher (Cmd+K)
// ============================================================================

let quickSwitcherOpen = false;

function toggleQuickSwitcher() {
    if (quickSwitcherOpen) {
        closeQuickSwitcher();
    } else {
        openQuickSwitcher();
    }
}

function openQuickSwitcher() {
    const switcher = document.getElementById('quick-switcher');
    const searchInput = document.getElementById('quick-switcher-search');

    if (!switcher) return;

    switcher.classList.remove('hidden');
    quickSwitcherOpen = true;

    // Focus the search input
    if (searchInput) {
        searchInput.value = '';
        searchInput.focus();
        // Populate conversation list
        renderQuickSwitcherList('');
    }
}

function closeQuickSwitcher() {
    const switcher = document.getElementById('quick-switcher');
    if (!switcher) return;

    switcher.classList.add('hidden');
    quickSwitcherOpen = false;
}

async function renderQuickSwitcherList(query) {
    const listEl = document.getElementById('quick-switcher-list');
    if (!listEl) return;

    // Clear list (safe way)
    while (listEl.firstChild) {
        listEl.removeChild(listEl.firstChild);
    }

    if (!query || query.length < 2) {
        // Show recent conversations when no query
        const filtered = (window.conversations || []).filter(conv => {
            const title = (conv.title || 'Untitled').toLowerCase();
            const preview = (conv.preview || '').toLowerCase();
            const q = query.toLowerCase();
            return title.includes(q) || preview.includes(q);
        });

        renderConversationItems(filtered, listEl);
        return;
    }

    // Show loading indicator
    const loading = document.createElement('div');
    loading.className = 'quick-switcher-loading';
    loading.textContent = 'Searching...';
    listEl.appendChild(loading);

    try {
        // Search both conversation titles and message content
        const response = await fetch(`/api/messages/search?q=${encodeURIComponent(query)}&cross_conversation=true&limit=20`);
        const data = await response.json();

        // Remove loading indicator
        loading.remove();

        if (!response.ok) {
            showSearchError(listEl, 'Search failed');
            return;
        }

        const results = data.results || [];

        if (results.length === 0) {
            const empty = document.createElement('div');
            empty.className = 'quick-switcher-empty';
            empty.textContent = 'No messages found';
            listEl.appendChild(empty);
            return;
        }

        // Render message search results
        results.forEach((result, index) => {
            const item = document.createElement('div');
            item.className = 'quick-switcher-item message-result';
            if (index === 0) {
                item.classList.add('active');
            }

            // Conversation title
            const convTitle = document.createElement('div');
            convTitle.className = 'quick-switcher-item-title';
            convTitle.textContent = result.conversation_title || 'Untitled';
            item.appendChild(convTitle);

            // Message snippet with highlighting
            const snippet = document.createElement('div');
            snippet.className = 'quick-switcher-item-preview';
            highlightSearchTermsInElement(snippet, result.snippet, query);
            item.appendChild(snippet);

            // Message metadata
            const meta = document.createElement('div');
            meta.className = 'quick-switcher-item-meta';
            meta.textContent = `${result.role === 'user' ? 'You' : 'Assistant'} • ${formatSearchDate(result.created_at)}`;
            item.appendChild(meta);

            // Click to navigate to conversation
            item.addEventListener('click', () => {
                if (typeof switchConversation === 'function') {
                    switchConversation(result.conversation_id);
                }
                closeQuickSwitcher();
            });

            listEl.appendChild(item);
        });

    } catch (error) {
        console.error('Search error:', error);
        loading.remove();
        showSearchError(listEl, 'Search error: ' + error.message);
    }
}

function renderConversationItems(conversations, listEl) {
    if (conversations.length === 0) {
        const empty = document.createElement('div');
        empty.className = 'quick-switcher-empty';
        empty.textContent = 'No conversations found';
        listEl.appendChild(empty);
        return;
    }

    conversations.forEach((conv, index) => {
        const item = document.createElement('div');
        item.className = 'quick-switcher-item';
        if (index === 0) {
            item.classList.add('active');
        }

        const title = document.createElement('div');
        title.className = 'quick-switcher-item-title';
        title.textContent = conv.title || 'Untitled';
        item.appendChild(title);

        if (conv.preview) {
            const preview = document.createElement('div');
            preview.className = 'quick-switcher-item-preview';
            preview.textContent = conv.preview;
            item.appendChild(preview);
        }

        // Click to switch
        item.addEventListener('click', () => {
            if (typeof switchConversation === 'function') {
                switchConversation(conv.id);
            }
            closeQuickSwitcher();
        });

        listEl.appendChild(item);
    });
}

function showSearchError(listEl, message) {
    const error = document.createElement('div');
    error.className = 'quick-switcher-error';
    error.textContent = message;
    listEl.appendChild(error);
}

function highlightSearchTermsInElement(element, text, query) {
    if (!text || !query) {
        element.textContent = text;
        return;
    }

    // Split text by the search term (case-insensitive)
    const regex = new RegExp(`(${query.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')})`, 'gi');
    const parts = text.split(regex);

    parts.forEach(part => {
        if (part.toLowerCase() === query.toLowerCase()) {
            // Highlight matching part
            const mark = document.createElement('mark');
            mark.textContent = part;
            element.appendChild(mark);
        } else {
            // Regular text
            element.appendChild(document.createTextNode(part));
        }
    });
}

function formatSearchDate(isoDate) {
    if (!isoDate) return '';
    try {
        const date = new Date(isoDate);
        const now = new Date();
        const diffMs = now - date;
        const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));

        if (diffDays === 0) {
            return 'Today';
        } else if (diffDays === 1) {
            return 'Yesterday';
        } else if (diffDays < 7) {
            return date.toLocaleDateString([], { weekday: 'short' });
        } else {
            return date.toLocaleDateString([], { month: 'short', day: 'numeric' });
        }
    } catch {
        return '';
    }
}

function handleQuickSwitcherSearch(event) {
    const query = event.target.value;
    renderQuickSwitcherList(query).catch(err => {
        console.error('Quick switcher search error:', err);
    });
}

function handleQuickSwitcherKeydown(event) {
    const listEl = document.getElementById('quick-switcher-list');
    if (!listEl) return;

    const items = listEl.querySelectorAll('.quick-switcher-item');
    const activeItem = listEl.querySelector('.quick-switcher-item.active');
    let activeIndex = Array.from(items).indexOf(activeItem);

    if (event.key === 'ArrowDown') {
        event.preventDefault();
        if (activeIndex < items.length - 1) {
            items[activeIndex].classList.remove('active');
            items[activeIndex + 1].classList.add('active');
            items[activeIndex + 1].scrollIntoView({ block: 'nearest' });
        }
    } else if (event.key === 'ArrowUp') {
        event.preventDefault();
        if (activeIndex > 0) {
            items[activeIndex].classList.remove('active');
            items[activeIndex - 1].classList.add('active');
            items[activeIndex - 1].scrollIntoView({ block: 'nearest' });
        }
    } else if (event.key === 'Enter') {
        event.preventDefault();
        if (activeItem) {
            activeItem.click();
        }
    } else if (event.key === 'Escape') {
        event.preventDefault();
        closeQuickSwitcher();
    }
}

// ============================================================================
// Shortcut Help Modal (Cmd+/)
// ============================================================================

let shortcutHelpOpen = false;

function toggleShortcutHelp() {
    if (shortcutHelpOpen) {
        closeShortcutHelp();
    } else {
        openShortcutHelp();
    }
}

function openShortcutHelp() {
    const modal = document.getElementById('shortcut-help');
    if (!modal) return;

    modal.classList.remove('hidden');
    shortcutHelpOpen = true;
}

function closeShortcutHelp() {
    const modal = document.getElementById('shortcut-help');
    if (!modal) return;

    modal.classList.add('hidden');
    shortcutHelpOpen = false;
}

// ============================================================================
// Close Any Open Modal (Escape)
// ============================================================================

function closeAnyOpenModal() {
    // Close quick switcher if open
    if (quickSwitcherOpen) {
        closeQuickSwitcher();
        return;
    }

    // Close shortcut help if open
    if (shortcutHelpOpen) {
        closeShortcutHelp();
        return;
    }

    // Close settings modal if open
    const settingsModal = document.getElementById('settings-modal');
    if (settingsModal && !settingsModal.classList.contains('hidden')) {
        if (typeof closeSettings === 'function') {
            closeSettings();
        }
        return;
    }

    // Close delete confirmation dialog if open
    const deleteDialog = document.querySelector('.delete-confirm-dialog');
    if (deleteDialog) {
        deleteDialog.remove();
        return;
    }
}

// ============================================================================
// Initialize Shortcuts
// ============================================================================

document.addEventListener('DOMContentLoaded', () => {
    // Register global keydown handler
    document.addEventListener('keydown', handleKeydown);

    // Setup quick switcher search
    const searchInput = document.getElementById('quick-switcher-search');
    if (searchInput) {
        searchInput.addEventListener('input', handleQuickSwitcherSearch);
        searchInput.addEventListener('keydown', handleQuickSwitcherKeydown);
    }

    // Setup quick switcher backdrop click
    const switcherBackdrop = document.querySelector('#quick-switcher .modal-backdrop');
    if (switcherBackdrop) {
        switcherBackdrop.addEventListener('click', closeQuickSwitcher);
    }

    // Setup shortcut help backdrop click
    const helpBackdrop = document.querySelector('#shortcut-help .modal-backdrop');
    if (helpBackdrop) {
        helpBackdrop.addEventListener('click', closeShortcutHelp);
    }
});
