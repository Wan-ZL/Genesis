/**
 * Genesis AI Assistant - Frontend Logic
 */

// State
let pendingFiles = []; // Files waiting to be sent with next message
let isRecording = false;
let speechRecognition = null;
let useStreaming = true; // Enable streaming by default
let activeStreamController = null; // Track active stream for cancellation
let currentConversationId = 'main'; // Currently active conversation
let sidebarCollapsed = false; // Sidebar visibility state
let conversations = []; // Cached conversation list
let personas = []; // Cached persona list
let currentPersonaId = null; // Current persona for active conversation

// DOM Elements
const messagesContainer = document.getElementById('messages');
const messageInput = document.getElementById('message-input');
const sendBtn = document.getElementById('send-btn');
const attachBtn = document.getElementById('attach-btn');
const voiceBtn = document.getElementById('voice-btn');
const fileInput = document.getElementById('file-input');
const filePreview = document.getElementById('file-preview');
const currentFocusEl = document.getElementById('current-focus');
const lastRunEl = document.getElementById('last-run');
const refreshMetricsBtn = document.getElementById('refresh-metrics-btn');
const toggleStatusBtn = document.getElementById('toggle-status-btn');
const statusPanel = document.querySelector('.status-panel');
const sidebar = document.getElementById('conversation-sidebar');
const sidebarToggleBtn = document.getElementById('sidebar-toggle-btn');
const sidebarOverlay = document.getElementById('sidebar-overlay');
const newConversationBtn = document.getElementById('new-conversation-btn');
const conversationListEl = document.getElementById('conversation-list');

// Theme toggle
const themeToggleBtn = document.getElementById('theme-toggle-btn');

// Settings elements
const settingsBtn = document.getElementById('settings-btn');
const settingsModal = document.getElementById('settings-modal');
const settingsCloseBtn = document.getElementById('settings-close-btn');
const settingsSaveBtn = document.getElementById('settings-save-btn');
const settingsCancelBtn = document.getElementById('settings-cancel-btn');
const openaiKeyInput = document.getElementById('openai-key-input');
const anthropicKeyInput = document.getElementById('anthropic-key-input');
const openaiKeyStatus = document.getElementById('openai-key-status');
const anthropicKeyStatus = document.getElementById('anthropic-key-status');
const modelSelect = document.getElementById('model-select');
const permissionSelect = document.getElementById('permission-select');

// Persona elements
const personaSelectorBtn = document.getElementById('persona-selector-btn');
const createPersonaBtn = document.getElementById('create-persona-btn');
const personaDropdown = document.getElementById('persona-dropdown');
const personaList = document.getElementById('persona-list');
const currentPersonaName = document.getElementById('current-persona-name');
const personaModal = document.getElementById('persona-modal');
const personaModalTitle = document.getElementById('persona-modal-title');
const personaModalId = document.getElementById('persona-modal-id');
const personaNameInput = document.getElementById('persona-name-input');
const personaDescInput = document.getElementById('persona-description-input');
const personaPromptInput = document.getElementById('persona-prompt-input');
const personaPromptChars = document.getElementById('persona-prompt-chars');
const personaSaveBtn = document.getElementById('persona-save-btn');
const personaCancelBtn = document.getElementById('persona-cancel-btn');
const personaModalClose = document.getElementById('persona-modal-close');

// ============================================================================
// Theme (Dark Mode) Management
// ============================================================================

/**
 * Initialize theme based on: localStorage > system preference > light default
 */
function initTheme() {
    const savedTheme = localStorage.getItem('theme');

    if (savedTheme) {
        // User has explicitly chosen a theme
        setTheme(savedTheme);
    } else {
        // Detect system preference
        const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
        setTheme(prefersDark ? 'dark' : 'light');
    }

    // Listen for system preference changes (only when user has not set a preference)
    window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', (e) => {
        if (!localStorage.getItem('theme')) {
            setTheme(e.matches ? 'dark' : 'light');
        }
    });
}

/**
 * Set the theme on the document
 */
function setTheme(theme) {
    document.documentElement.setAttribute('data-theme', theme);
}

/**
 * Toggle between light and dark themes
 */
function toggleTheme() {
    const currentTheme = document.documentElement.getAttribute('data-theme') || 'light';
    const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
    setTheme(newTheme);
    localStorage.setItem('theme', newTheme);
}

/**
 * Get the current theme name
 */
function getCurrentTheme() {
    return document.documentElement.getAttribute('data-theme') || 'light';
}

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    // Apply theme immediately to prevent flash
    initTheme();

    loadStatus();
    loadConversations(true); // Load sidebar and current conversation
    loadMetrics();
    loadPersonas(); // Load persona list
    setupEventListeners();
    initVoiceInput();

    // Refresh metrics every 30 seconds
    setInterval(loadMetrics, 30000);

    // Check sidebar state from localStorage
    const savedSidebarState = localStorage.getItem('sidebarCollapsed');
    if (savedSidebarState === 'true') {
        sidebarCollapsed = true;
        sidebar.classList.add('collapsed');
    }

    // Check last active conversation from localStorage
    const lastConv = localStorage.getItem('currentConversationId');
    if (lastConv) {
        currentConversationId = lastConv;
    }
});

function setupEventListeners() {
    // Send message on button click
    sendBtn.addEventListener('click', sendMessage);

    // Send message on Enter (Shift+Enter for newline)
    messageInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    });

    // Auto-resize textarea
    messageInput.addEventListener('input', () => {
        messageInput.style.height = 'auto';
        messageInput.style.height = Math.min(messageInput.scrollHeight, 150) + 'px';
    });

    // Refresh metrics
    refreshMetricsBtn.addEventListener('click', loadMetrics);

    // File upload
    attachBtn.addEventListener('click', () => fileInput.click());
    fileInput.addEventListener('change', handleFileSelect);

    // Mobile status panel toggle
    if (toggleStatusBtn) {
        toggleStatusBtn.addEventListener('click', toggleStatusPanel);
    }

    // Voice input
    if (voiceBtn) {
        voiceBtn.addEventListener('click', toggleVoiceInput);
    }

    // Theme toggle
    if (themeToggleBtn) {
        themeToggleBtn.addEventListener('click', toggleTheme);
    }

    // Settings
    if (settingsBtn) {
        settingsBtn.addEventListener('click', openSettings);
    }
    if (settingsCloseBtn) {
        settingsCloseBtn.addEventListener('click', closeSettings);
    }
    if (settingsSaveBtn) {
        settingsSaveBtn.addEventListener('click', saveSettings);
    }
    if (settingsCancelBtn) {
        settingsCancelBtn.addEventListener('click', closeSettings);
    }
    // Close modal on backdrop click
    if (settingsModal) {
        settingsModal.querySelector('.modal-backdrop').addEventListener('click', closeSettings);
    }

    // Sidebar toggle
    if (sidebarToggleBtn) {
        sidebarToggleBtn.addEventListener('click', toggleSidebar);
    }

    // Sidebar overlay (close on mobile)
    if (sidebarOverlay) {
        sidebarOverlay.addEventListener('click', closeSidebar);
    }

    // New conversation button
    if (newConversationBtn) {
        newConversationBtn.addEventListener('click', createNewConversation);
    }

    // Persona switcher
    if (personaSelectorBtn) {
        personaSelectorBtn.addEventListener('click', togglePersonaDropdown);
    }
    if (createPersonaBtn) {
        createPersonaBtn.addEventListener('click', openCreatePersonaModal);
    }
    if (personaModalClose) {
        personaModalClose.addEventListener('click', closePersonaModal);
    }
    if (personaCancelBtn) {
        personaCancelBtn.addEventListener('click', closePersonaModal);
    }
    if (personaSaveBtn) {
        personaSaveBtn.addEventListener('click', savePersona);
    }
    if (personaModal) {
        personaModal.querySelector('.modal-backdrop').addEventListener('click', closePersonaModal);
    }
    if (personaPromptInput) {
        personaPromptInput.addEventListener('input', updatePersonaCharCount);
    }

    // Close persona dropdown when clicking outside
    document.addEventListener('click', (e) => {
        if (personaDropdown && !personaDropdown.classList.contains('hidden')) {
            if (!personaSelectorBtn.contains(e.target) && !personaDropdown.contains(e.target)) {
                closePersonaDropdown();
            }
        }
    });
}

function toggleStatusPanel() {
    statusPanel.classList.toggle('show');
    toggleStatusBtn.textContent = statusPanel.classList.contains('show') ? 'Close' : 'Menu';
}

// ============================================================================
// Conversation Sidebar
// ============================================================================

function toggleSidebar() {
    sidebarCollapsed = !sidebarCollapsed;
    sidebar.classList.toggle('collapsed', sidebarCollapsed);
    localStorage.setItem('sidebarCollapsed', sidebarCollapsed);

    // On mobile/tablet, show overlay when sidebar is open
    if (!sidebarCollapsed && window.innerWidth <= 900) {
        sidebarOverlay.classList.add('active');
    } else {
        sidebarOverlay.classList.remove('active');
    }
}

function closeSidebar() {
    sidebarCollapsed = true;
    sidebar.classList.add('collapsed');
    sidebarOverlay.classList.remove('active');
    localStorage.setItem('sidebarCollapsed', 'true');
}

async function loadConversations(loadMessages = true) {
    try {
        const response = await fetch('/api/conversations');
        const data = await response.json();

        if (response.ok) {
            conversations = data.conversations || [];
            renderConversationList();

            if (loadMessages) {
                // Load the current conversation
                if (conversations.length > 0) {
                    // Check if saved conversation still exists
                    const savedConv = conversations.find(c => c.id === currentConversationId);
                    if (!savedConv) {
                        currentConversationId = conversations[0].id;
                    }
                }

                await loadConversationMessages(currentConversationId);
            }
        }
    } catch (error) {
        console.error('Failed to load conversations:', error);
        // Fallback to loading single conversation
        if (loadMessages) {
            await loadSingleConversation();
        }
    }
}

function renderConversationList() {
    conversationListEl.innerHTML = '';

    conversations.forEach(conv => {
        const item = document.createElement('div');
        item.className = 'conversation-item' + (conv.id === currentConversationId ? ' active' : '');
        item.dataset.id = conv.id;

        const content = document.createElement('div');
        content.className = 'conversation-item-content';

        const title = document.createElement('div');
        title.className = 'conversation-item-title';
        title.textContent = conv.title || 'Untitled';
        content.appendChild(title);

        if (conv.preview) {
            const preview = document.createElement('div');
            preview.className = 'conversation-item-preview';
            preview.textContent = conv.preview;
            content.appendChild(preview);
        }

        const meta = document.createElement('div');
        meta.className = 'conversation-item-meta';

        const date = document.createElement('span');
        date.className = 'conversation-item-date';
        date.textContent = formatConversationDate(conv.updated_at || conv.created_at);
        meta.appendChild(date);

        // Delete button (not for default conversation)
        if (conv.id !== 'main') {
            const deleteBtn = document.createElement('button');
            deleteBtn.className = 'conversation-item-delete';
            deleteBtn.textContent = 'Delete';
            deleteBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                confirmDeleteConversation(conv.id, conv.title);
            });
            meta.appendChild(deleteBtn);
        }

        content.appendChild(meta);
        item.appendChild(content);

        // Click to switch conversation
        item.addEventListener('click', () => {
            switchConversation(conv.id);
        });

        conversationListEl.appendChild(item);
    });
}

function formatConversationDate(isoDate) {
    if (!isoDate) return '';
    try {
        const date = new Date(isoDate);
        const now = new Date();
        const diffMs = now - date;
        const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));

        if (diffDays === 0) {
            return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
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

async function switchConversation(conversationId) {
    if (conversationId === currentConversationId) return;

    currentConversationId = conversationId;
    localStorage.setItem('currentConversationId', conversationId);

    // Update active state in sidebar
    document.querySelectorAll('.conversation-item').forEach(item => {
        item.classList.toggle('active', item.dataset.id === conversationId);
    });

    // Load messages
    await loadConversationMessages(conversationId);

    // Load persona for this conversation
    await loadConversationPersona();

    // Close sidebar on mobile
    if (window.innerWidth <= 900) {
        closeSidebar();
    }
}

async function loadConversationMessages(conversationId) {
    try {
        const url = conversationId === 'main'
            ? '/api/conversation'
            : `/api/conversations/${conversationId}`;

        const response = await fetch(url);
        const data = await response.json();

        if (response.ok) {
            messagesContainer.innerHTML = '';
            (data.messages || []).forEach(msg => {
                addMessageToUI(msg.role, msg.content);
            });
        }
    } catch (error) {
        console.error('Failed to load conversation messages:', error);
    }
}

async function createNewConversation() {
    try {
        const response = await fetch('/api/conversations', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ title: null })
        });

        if (response.ok) {
            const newConv = await response.json();
            currentConversationId = newConv.id;
            localStorage.setItem('currentConversationId', newConv.id);

            // Reload sidebar and switch to new conversation
            await loadConversations();

            // Focus input
            messageInput.focus();

            // Close sidebar on mobile
            if (window.innerWidth <= 900) {
                closeSidebar();
            }
        } else {
            const error = await response.json();
            console.error('Failed to create conversation:', error);
        }
    } catch (error) {
        console.error('Failed to create conversation:', error);
    }
}

function confirmDeleteConversation(conversationId, title) {
    // Create confirmation dialog
    const dialog = document.createElement('div');
    dialog.className = 'delete-confirm-dialog';
    dialog.innerHTML = `
        <div class="delete-confirm-backdrop"></div>
        <div class="delete-confirm-content">
            <h3>Delete Conversation?</h3>
            <p>Are you sure you want to delete "${title || 'Untitled'}"? This action cannot be undone.</p>
            <div class="delete-confirm-buttons">
                <button class="btn-danger" id="confirm-delete-yes">Delete</button>
                <button class="btn-secondary" id="confirm-delete-no">Cancel</button>
            </div>
        </div>
    `;

    document.body.appendChild(dialog);

    // Handle confirmation
    document.getElementById('confirm-delete-yes').addEventListener('click', async () => {
        await deleteConversation(conversationId);
        dialog.remove();
    });

    document.getElementById('confirm-delete-no').addEventListener('click', () => {
        dialog.remove();
    });

    dialog.querySelector('.delete-confirm-backdrop').addEventListener('click', () => {
        dialog.remove();
    });
}

async function deleteConversation(conversationId) {
    try {
        const response = await fetch(`/api/conversations/${conversationId}`, {
            method: 'DELETE'
        });

        if (response.ok) {
            // If we deleted the current conversation, switch to main
            if (conversationId === currentConversationId) {
                currentConversationId = 'main';
                localStorage.setItem('currentConversationId', 'main');
            }

            // Reload sidebar
            await loadConversations();
        } else {
            const error = await response.json();
            console.error('Failed to delete conversation:', error);
        }
    } catch (error) {
        console.error('Failed to delete conversation:', error);
    }
}

// Voice input using Web Speech API
function initVoiceInput() {
    // Check for browser support
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;

    if (!SpeechRecognition) {
        // Hide voice button if not supported
        if (voiceBtn) {
            voiceBtn.style.display = 'none';
            console.log('Speech recognition not supported in this browser');
        }
        return;
    }

    speechRecognition = new SpeechRecognition();
    speechRecognition.continuous = true;
    speechRecognition.interimResults = true;
    speechRecognition.lang = 'en-US'; // Default language

    // Handle results
    speechRecognition.onresult = (event) => {
        let finalTranscript = '';
        let interimTranscript = '';

        for (let i = event.resultIndex; i < event.results.length; i++) {
            const transcript = event.results[i][0].transcript;
            if (event.results[i].isFinal) {
                finalTranscript += transcript;
            } else {
                interimTranscript += transcript;
            }
        }

        // Append final transcript to input
        if (finalTranscript) {
            const currentValue = messageInput.value;
            const separator = currentValue && !currentValue.endsWith(' ') ? ' ' : '';
            messageInput.value = currentValue + separator + finalTranscript;
            // Trigger auto-resize
            messageInput.dispatchEvent(new Event('input'));
        }
    };

    // Handle errors
    speechRecognition.onerror = (event) => {
        console.error('Speech recognition error:', event.error);
        stopVoiceInput();

        if (event.error === 'not-allowed') {
            alert('Microphone access denied. Please allow microphone access in your browser settings.');
        } else if (event.error === 'no-speech') {
            // Silently restart if no speech detected
        }
    };

    // Handle end
    speechRecognition.onend = () => {
        if (isRecording) {
            // Restart if still recording (continuous mode)
            speechRecognition.start();
        }
    };
}

function toggleVoiceInput() {
    if (isRecording) {
        stopVoiceInput();
    } else {
        startVoiceInput();
    }
}

function startVoiceInput() {
    if (!speechRecognition) {
        alert('Voice input is not supported in this browser. Try Chrome or Safari.');
        return;
    }

    try {
        speechRecognition.start();
        isRecording = true;
        voiceBtn.classList.add('recording');
        voiceBtn.title = 'Stop recording';
        messageInput.placeholder = 'Listening...';
    } catch (error) {
        console.error('Failed to start speech recognition:', error);
    }
}

function stopVoiceInput() {
    if (speechRecognition) {
        speechRecognition.stop();
    }
    isRecording = false;
    if (voiceBtn) {
        voiceBtn.classList.remove('recording');
        voiceBtn.title = 'Voice input';
    }
    messageInput.placeholder = 'Type your message...';
}

// File handling
async function handleFileSelect(e) {
    const files = Array.from(e.target.files);
    for (const file of files) {
        await uploadAndPreviewFile(file);
    }
    fileInput.value = ''; // Reset input
}

async function uploadAndPreviewFile(file) {
    const formData = new FormData();
    formData.append('file', file);

    try {
        const response = await fetch('/api/upload', {
            method: 'POST',
            body: formData
        });

        if (response.ok) {
            const data = await response.json();
            pendingFiles.push({
                file_id: data.file_id,
                filename: data.filename,
                content_type: data.content_type
            });
            updateFilePreview();
        } else {
            const error = await response.json();
            alert(`Upload failed: ${error.detail || 'Unknown error'}`);
        }
    } catch (error) {
        alert(`Upload failed: ${error.message}`);
    }
}

function updateFilePreview() {
    filePreview.innerHTML = '';
    pendingFiles.forEach((file, index) => {
        const item = document.createElement('div');
        item.className = 'file-preview-item';

        if (file.content_type.startsWith('image/')) {
            const img = document.createElement('img');
            img.src = `/api/file/${file.file_id}/content`;
            img.alt = file.filename;
            // Use a data URL approach for preview
            fetch(`/api/file/${file.file_id}/content`)
                .then(r => r.json())
                .then(data => {
                    img.src = `data:${data.content_type};base64,${data.data}`;
                });
            item.appendChild(img);
        } else {
            const icon = document.createElement('span');
            icon.className = 'file-icon';
            icon.textContent = '📄';
            item.appendChild(icon);
        }

        const name = document.createElement('span');
        name.textContent = file.filename.length > 20
            ? file.filename.substring(0, 17) + '...'
            : file.filename;
        item.appendChild(name);

        const removeBtn = document.createElement('span');
        removeBtn.className = 'remove-file';
        removeBtn.textContent = '×';
        removeBtn.onclick = () => {
            pendingFiles.splice(index, 1);
            updateFilePreview();
        };
        item.appendChild(removeBtn);

        filePreview.appendChild(item);
    });
}

function clearPendingFiles() {
    pendingFiles = [];
    updateFilePreview();
}

// API calls
async function sendMessage() {
    const message = messageInput.value.trim();
    if (!message && pendingFiles.length === 0) return;

    // Clear input and disable button
    messageInput.value = '';
    messageInput.style.height = 'auto';
    sendBtn.disabled = true;

    // Build display message
    let displayMessage = message;
    if (pendingFiles.length > 0) {
        const fileNames = pendingFiles.map(f => f.filename).join(', ');
        displayMessage = message + (message ? '\n' : '') + `[Attached: ${fileNames}]`;
    }

    // Add user message to UI
    addMessageToUI('user', displayMessage);

    // Prepare file IDs
    const fileIds = pendingFiles.map(f => f.file_id);
    clearPendingFiles();

    // Use streaming or regular endpoint based on setting
    if (useStreaming) {
        await sendMessageStreaming(message, fileIds);
    } else {
        await sendMessageRegular(message, fileIds);
    }

    // Refresh sidebar to update conversation titles and order (without reloading messages)
    loadConversations(false).catch(console.error);

    sendBtn.disabled = false;
    messageInput.focus();
}

async function sendMessageStreaming(message, fileIds) {
    // Create message element for streaming response
    const messageEl = document.createElement('div');
    messageEl.className = 'message assistant streaming';

    // Create content span for text
    const contentSpan = document.createElement('span');
    contentSpan.className = 'message-content';
    messageEl.appendChild(contentSpan);

    // Create progress indicator
    const progressEl = document.createElement('span');
    progressEl.className = 'streaming-indicator';
    progressEl.innerHTML = '<span class="dot"></span><span class="dot"></span><span class="dot"></span>';
    messageEl.appendChild(progressEl);

    messagesContainer.appendChild(messageEl);
    messagesContainer.scrollTop = messagesContainer.scrollHeight;

    let accumulatedText = '';
    let modelUsed = null;

    try {
        const response = await fetch('/api/chat/stream', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                message: message || 'Please analyze the attached file(s).',
                conversation_id: currentConversationId,
                file_ids: fileIds.length > 0 ? fileIds : null
            })
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Stream request failed');
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

        while (true) {
            const { done, value } = await reader.read();

            if (done) break;

            buffer += decoder.decode(value, { stream: true });

            // Process complete SSE events in buffer
            const events = buffer.split('\n\n');
            buffer = events.pop(); // Keep incomplete event in buffer

            for (const eventBlock of events) {
                if (!eventBlock.trim()) continue;

                const lines = eventBlock.split('\n');
                let eventType = null;
                let eventData = null;

                for (const line of lines) {
                    if (line.startsWith('event: ')) {
                        eventType = line.slice(7);
                    } else if (line.startsWith('data: ')) {
                        try {
                            eventData = JSON.parse(line.slice(6));
                        } catch (e) {
                            console.error('Failed to parse SSE data:', line);
                        }
                    }
                }

                if (eventType && eventData) {
                    handleStreamEvent(eventType, eventData, contentSpan, messageEl, (text) => {
                        accumulatedText += text;
                    }, (model) => {
                        modelUsed = model;
                    });
                }
            }

            // Auto-scroll while streaming
            messagesContainer.scrollTop = messagesContainer.scrollHeight;
        }

    } catch (error) {
        console.error('Streaming error:', error);
        contentSpan.textContent = `Error: ${error.message}`;
        messageEl.classList.add('error');
        messageEl.classList.remove('streaming');
    }

    // Finalize the message
    messageEl.classList.remove('streaming');
    progressEl.remove();

    // Convert accumulated plain text to markdown
    if (accumulatedText && typeof marked !== 'undefined' && typeof DOMPurify !== 'undefined') {
        marked.setOptions({
            breaks: true,
            gfm: true,
        });
        const rawHtml = marked.parse(accumulatedText);
        const cleanHtml = DOMPurify.sanitize(rawHtml);
        contentSpan.innerHTML = cleanHtml;
    }

    // Add model badge if we know the model
    if (modelUsed) {
        const modelBadge = document.createElement('span');
        modelBadge.className = 'model-badge';
        modelBadge.textContent = modelUsed.includes('claude') ? 'Claude' : 'GPT-4o';
        messageEl.appendChild(modelBadge);
    }
}

function handleStreamEvent(eventType, data, contentSpan, messageEl, addText, setModel) {
    switch (eventType) {
        case 'start':
            setModel(data.model);
            break;

        case 'token':
            if (data.text) {
                contentSpan.textContent += data.text;
                addText(data.text);
            }
            break;

        case 'tool_call':
            // Show tool call indicator
            const toolIndicator = document.createElement('div');
            toolIndicator.className = 'tool-indicator';
            toolIndicator.textContent = `🔧 Using tool: ${data.name}...`;
            messageEl.insertBefore(toolIndicator, messageEl.querySelector('.streaming-indicator'));
            break;

        case 'tool_result':
            // Update or remove tool indicator
            const indicators = messageEl.querySelectorAll('.tool-indicator');
            const lastIndicator = indicators[indicators.length - 1];
            if (lastIndicator) {
                if (data.success) {
                    lastIndicator.textContent = `✓ ${data.name} completed`;
                    lastIndicator.classList.add('tool-success');
                } else if (data.permission_escalation) {
                    lastIndicator.textContent = `⚠️ ${data.name} requires permission`;
                    lastIndicator.classList.add('tool-permission');
                } else {
                    lastIndicator.textContent = `✗ ${data.name} failed`;
                    lastIndicator.classList.add('tool-error');
                }
            }
            break;

        case 'done':
            if (data.model) {
                setModel(data.model);
            }
            break;

        case 'error':
            contentSpan.textContent = `Error: ${data.message}`;
            messageEl.classList.add('error');
            break;
    }
}

async function sendMessageRegular(message, fileIds) {
    // Add loading indicator
    const loadingEl = addMessageToUI('loading', 'Thinking...');

    try {
        const response = await fetch('/api/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                message: message || 'Please analyze the attached file(s).',
                conversation_id: currentConversationId,
                file_ids: fileIds.length > 0 ? fileIds : null
            })
        });

        const data = await response.json();

        // Remove loading indicator
        loadingEl.remove();

        if (response.ok) {
            // Add assistant response with model info
            addMessageToUI('assistant', data.response, data.model);
        } else {
            addMessageToUI('error', `Error: ${data.detail || 'Unknown error'}`);
        }
    } catch (error) {
        loadingEl.remove();
        addMessageToUI('error', `Error: ${error.message}`);
    }
}

function addMessageToUI(role, content, model = null) {
    const messageEl = document.createElement('div');
    messageEl.className = `message ${role}`;

    // Render markdown for assistant messages, plain text for user messages
    if (role === 'assistant' && typeof marked !== 'undefined' && typeof DOMPurify !== 'undefined') {
        // Configure marked for security and features
        marked.setOptions({
            breaks: true,  // Convert \n to <br>
            gfm: true,     // GitHub Flavored Markdown
        });

        // Parse markdown and sanitize HTML to prevent XSS
        const rawHtml = marked.parse(content);
        const cleanHtml = DOMPurify.sanitize(rawHtml);
        messageEl.innerHTML = cleanHtml;
    } else {
        // Fallback to plain text for user messages or if libraries not loaded
        messageEl.textContent = content;
    }

    // Add model badge for assistant messages
    if (role === 'assistant' && model) {
        const modelBadge = document.createElement('span');
        modelBadge.className = 'model-badge';
        modelBadge.textContent = model.includes('claude') ? 'Claude' : 'GPT-4o';
        messageEl.appendChild(modelBadge);
    }

    messagesContainer.appendChild(messageEl);
    messagesContainer.scrollTop = messagesContainer.scrollHeight;
    return messageEl;
}

// Load the single infinite conversation
async function loadSingleConversation() {
    try {
        const response = await fetch('/api/conversation');
        const data = await response.json();

        if (response.ok) {
            messagesContainer.innerHTML = '';

            // Display messages (most recent at bottom)
            data.messages.forEach(msg => {
                addMessageToUI(msg.role, msg.content);
            });
        }
    } catch (error) {
        console.error('Failed to load conversation:', error);
    }
}

async function loadStatus() {
    try {
        const response = await fetch('/api/status');
        const data = await response.json();

        // Display AI Assistant's own status (not Claude Code status)
        const versionEl = document.getElementById('assistant-version');
        const uptimeEl = document.getElementById('assistant-uptime');
        const msgCountEl = document.getElementById('assistant-msg-count');

        if (versionEl) {
            versionEl.textContent = data.version || 'Unknown';
        }

        if (uptimeEl) {
            const uptime = data.uptime_seconds || 0;
            uptimeEl.textContent = formatUptime(uptime);
        }

        if (msgCountEl) {
            msgCountEl.textContent = data.message_count || 0;
        }

        // Legacy elements - show status info
        if (currentFocusEl) {
            currentFocusEl.textContent = `v${data.version || '?'} - ${data.status || 'unknown'}`;
        }

        if (lastRunEl) {
            lastRunEl.textContent = `Uptime: ${formatUptime(data.uptime_seconds || 0)}`;
        }

        // Load degradation status
        loadDegradationStatus();
    } catch (error) {
        if (currentFocusEl) currentFocusEl.textContent = 'Error loading status';
        if (lastRunEl) lastRunEl.textContent = 'Error loading status';
    }
}

async function loadDegradationStatus() {
    const banner = document.getElementById('degradation-banner');
    const modeEl = document.getElementById('degradation-mode');
    const detailsEl = document.getElementById('degradation-details');

    if (!banner) return;

    try {
        const response = await fetch('/api/degradation');
        const data = await response.json();

        // Remove all mode classes
        banner.classList.remove('mode-offline', 'mode-rate-limited');

        if (!data.is_degraded) {
            // System is normal - hide banner
            banner.classList.add('hidden');
            return;
        }

        // Show banner
        banner.classList.remove('hidden');

        // Set mode-specific styling
        if (data.mode === 'OFFLINE') {
            banner.classList.add('mode-offline');
            modeEl.textContent = 'Offline Mode';
            detailsEl.textContent = 'Network unavailable - using cached responses';
        } else if (data.mode === 'RATE_LIMITED') {
            banner.classList.add('mode-rate-limited');
            modeEl.textContent = 'Rate Limited';
            const waitTime = data.queue_wait_seconds || 0;
            detailsEl.textContent = `Requests queued - resuming in ${waitTime}s`;
        } else if (data.mode === 'CLAUDE_UNAVAILABLE') {
            modeEl.textContent = 'Using OpenAI Fallback';
            detailsEl.textContent = 'Claude API unavailable';
        } else if (data.mode === 'OPENAI_UNAVAILABLE') {
            modeEl.textContent = 'Using Claude Fallback';
            detailsEl.textContent = 'OpenAI API unavailable';
        } else {
            modeEl.textContent = 'Degraded Mode';
            detailsEl.textContent = 'Some services may be impaired';
        }

    } catch (error) {
        // Silently fail - degradation API might not exist yet
        banner.classList.add('hidden');
    }
}

function formatUptime(seconds) {
    if (seconds < 60) return `${seconds}s`;
    if (seconds < 3600) return `${Math.floor(seconds / 60)}m ${seconds % 60}s`;
    const hours = Math.floor(seconds / 3600);
    const mins = Math.floor((seconds % 3600) / 60);
    return `${hours}h ${mins}m`;
}

async function loadMetrics() {
    const requestsEl = document.getElementById('metric-requests');
    const successRateEl = document.getElementById('metric-success-rate');
    const latencyEl = document.getElementById('metric-latency');
    const messagesEl = document.getElementById('metric-messages');

    try {
        const response = await fetch('/api/metrics');
        const data = await response.json();

        // Total requests
        const totalRequests = data.requests?.total || 0;
        requestsEl.textContent = totalRequests.toLocaleString();

        // Success rate: calculated as (total - errors) / total
        if (totalRequests > 0) {
            const totalErrors = data.errors?.total || 0;
            const successCount = totalRequests - totalErrors;
            const successRate = ((successCount / totalRequests) * 100).toFixed(1);
            successRateEl.textContent = `${successRate}%`;
            successRateEl.className = 'metric-value ' + (parseFloat(successRate) >= 90 ? 'metric-good' : 'metric-warn');
        } else {
            successRateEl.textContent = '-';
            successRateEl.className = 'metric-value';
        }

        // Average latency: from data.latency.overall.avg
        const avgLatency = data.latency?.overall?.avg;
        if (avgLatency !== undefined && avgLatency !== null) {
            latencyEl.textContent = `${Math.round(avgLatency)}ms`;
            latencyEl.className = 'metric-value ' + (avgLatency < 2000 ? 'metric-good' : 'metric-warn');
        } else {
            latencyEl.textContent = '-';
            latencyEl.className = 'metric-value';
        }

        // Total messages (all conversations)
        const totalMessages = data.conversations?.total_messages || 0;
        messagesEl.textContent = totalMessages.toLocaleString();

    } catch (error) {
        console.error('Failed to load metrics:', error);
        requestsEl.textContent = 'Error';
        successRateEl.textContent = '-';
        latencyEl.textContent = '-';
        messagesEl.textContent = '-';
    }
}

// ============================================================================
// Persona Switcher Functions
// ============================================================================

async function loadPersonas() {
    try {
        const response = await fetch('/api/personas');
        const data = await response.json();

        if (response.ok) {
            personas = data.personas || [];
            renderPersonaList();
            await loadConversationPersona();
        }
    } catch (error) {
        console.error('Failed to load personas:', error);
    }
}

async function loadConversationPersona() {
    try {
        const response = await fetch(`/api/conversations/${currentConversationId}/persona`);
        const data = await response.json();

        if (response.ok) {
            currentPersonaId = data.persona_id || 'default';
            updateCurrentPersonaDisplay();
        }
    } catch (error) {
        console.error('Failed to load conversation persona:', error);
        currentPersonaId = 'default';
        updateCurrentPersonaDisplay();
    }
}

function updateCurrentPersonaDisplay() {
    const persona = personas.find(p => p.id === currentPersonaId);
    if (persona && currentPersonaName) {
        currentPersonaName.textContent = persona.name;
    } else if (currentPersonaName) {
        currentPersonaName.textContent = 'Default Assistant';
    }
}

function renderPersonaList() {
    if (!personaList) return;
    while (personaList.firstChild) {
        personaList.removeChild(personaList.firstChild);
    }

    personas.forEach(persona => {
        const item = document.createElement('div');
        item.className = 'persona-item' + (persona.id === currentPersonaId ? ' active' : '');
        item.dataset.id = persona.id;

        const content = document.createElement('div');
        content.className = 'persona-item-content';

        const name = document.createElement('div');
        name.className = 'persona-item-name';
        name.textContent = persona.name;
        content.appendChild(name);

        if (persona.description) {
            const desc = document.createElement('div');
            desc.className = 'persona-item-description';
            desc.textContent = persona.description;
            content.appendChild(desc);
        }

        if (persona.is_builtin) {
            const builtin = document.createElement('div');
            builtin.className = 'persona-item-builtin';
            builtin.textContent = 'Built-in';
            content.appendChild(builtin);
        }

        item.appendChild(content);

        if (!persona.is_builtin) {
            const actions = document.createElement('div');
            actions.className = 'persona-item-actions';

            const editBtn = document.createElement('button');
            editBtn.className = 'persona-item-action-btn edit';
            editBtn.textContent = 'Edit';
            editBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                openEditPersonaModal(persona);
            });
            actions.appendChild(editBtn);

            const deleteBtn = document.createElement('button');
            deleteBtn.className = 'persona-item-action-btn delete';
            deleteBtn.textContent = 'Delete';
            deleteBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                confirmDeletePersona(persona);
            });
            actions.appendChild(deleteBtn);

            item.appendChild(actions);
        }

        item.addEventListener('click', () => {
            switchPersona(persona.id);
        });

        personaList.appendChild(item);
    });
}

function togglePersonaDropdown() {
    const isHidden = personaDropdown.classList.contains('hidden');

    if (isHidden) {
        const rect = personaSelectorBtn.getBoundingClientRect();
        personaDropdown.style.position = 'fixed';
        personaDropdown.style.top = (rect.bottom + 4) + 'px';
        personaDropdown.style.left = rect.left + 'px';
        personaDropdown.style.width = Math.max(rect.width, 300) + 'px';

        personaDropdown.classList.remove('hidden');
        personaSelectorBtn.classList.add('active');
    } else {
        closePersonaDropdown();
    }
}

function closePersonaDropdown() {
    personaDropdown.classList.add('hidden');
    personaSelectorBtn.classList.remove('active');
}

async function switchPersona(personaId) {
    try {
        const response = await fetch(`/api/conversations/${currentConversationId}/persona`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ persona_id: personaId })
        });

        if (response.ok) {
            currentPersonaId = personaId;
            updateCurrentPersonaDisplay();
            renderPersonaList();
            closePersonaDropdown();
        } else {
            const error = await response.json();
            console.error('Failed to switch persona:', error);
        }
    } catch (error) {
        console.error('Failed to switch persona:', error);
    }
}

function openCreatePersonaModal() {
    personaModalTitle.textContent = 'Create Custom Persona';
    personaModalId.value = '';
    personaNameInput.value = '';
    personaDescInput.value = '';
    personaPromptInput.value = '';
    updatePersonaCharCount();
    personaModal.classList.remove('hidden');
    personaNameInput.focus();
}

function openEditPersonaModal(persona) {
    personaModalTitle.textContent = 'Edit Custom Persona';
    personaModalId.value = persona.id;
    personaNameInput.value = persona.name;
    personaDescInput.value = persona.description || '';
    personaPromptInput.value = persona.system_prompt;
    updatePersonaCharCount();
    personaModal.classList.remove('hidden');
    personaNameInput.focus();
}

function closePersonaModal() {
    personaModal.classList.add('hidden');
}

function updatePersonaCharCount() {
    const length = personaPromptInput.value.length;
    personaPromptChars.textContent = length;

    if (length > 4000) {
        personaPromptChars.style.color = 'var(--color-btn-danger-bg)';
    } else if (length > 3500) {
        personaPromptChars.style.color = 'var(--color-warning)';
    } else {
        personaPromptChars.style.color = '';
    }
}

async function savePersona() {
    const name = personaNameInput.value.trim();
    const description = personaDescInput.value.trim();
    const systemPrompt = personaPromptInput.value.trim();
    const personaId = personaModalId.value;

    if (!name) {
        alert('Name is required');
        return;
    }

    if (!systemPrompt) {
        alert('System prompt is required');
        return;
    }

    if (systemPrompt.length > 4000) {
        alert('System prompt must be 4000 characters or less');
        return;
    }

    try {
        personaSaveBtn.disabled = true;
        personaSaveBtn.textContent = 'Saving...';

        const isEdit = !!personaId;
        const url = isEdit ? `/api/personas/${personaId}` : '/api/personas';
        const method = isEdit ? 'PUT' : 'POST';

        const payload = { name, description, system_prompt: systemPrompt };

        const response = await fetch(url, {
            method,
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        if (response.ok) {
            await loadPersonas();
            closePersonaModal();
        } else {
            const error = await response.json();
            alert(`Failed to save persona: ${error.detail || 'Unknown error'}`);
        }
    } catch (error) {
        console.error('Failed to save persona:', error);
        alert(`Error: ${error.message}`);
    } finally {
        personaSaveBtn.disabled = false;
        personaSaveBtn.textContent = 'Save Persona';
    }
}

function confirmDeletePersona(persona) {
    const dialog = document.createElement('div');
    dialog.className = 'delete-confirm-dialog';

    const backdrop = document.createElement('div');
    backdrop.className = 'delete-confirm-backdrop';
    dialog.appendChild(backdrop);

    const content = document.createElement('div');
    content.className = 'delete-confirm-content';

    const title = document.createElement('h3');
    title.textContent = 'Delete Persona?';
    content.appendChild(title);

    const message = document.createElement('p');
    message.textContent = 'Are you sure you want to delete "' + persona.name + '"? This action cannot be undone.';
    content.appendChild(message);

    const buttons = document.createElement('div');
    buttons.className = 'delete-confirm-buttons';

    const deleteBtn = document.createElement('button');
    deleteBtn.className = 'btn-danger';
    deleteBtn.textContent = 'Delete';
    deleteBtn.addEventListener('click', async () => {
        await deletePersona(persona.id);
        dialog.remove();
    });
    buttons.appendChild(deleteBtn);

    const cancelBtn = document.createElement('button');
    cancelBtn.className = 'btn-secondary';
    cancelBtn.textContent = 'Cancel';
    cancelBtn.addEventListener('click', () => {
        dialog.remove();
    });
    buttons.appendChild(cancelBtn);

    content.appendChild(buttons);
    dialog.appendChild(content);

    backdrop.addEventListener('click', () => {
        dialog.remove();
    });

    document.body.appendChild(dialog);
}

async function deletePersona(personaId) {
    try {
        const response = await fetch(`/api/personas/${personaId}`, {
            method: 'DELETE'
        });

        if (response.ok) {
            if (personaId === currentPersonaId) {
                await switchPersona('default');
            }
            await loadPersonas();
        } else {
            const error = await response.json();
            console.error('Failed to delete persona:', error);
            alert(`Failed to delete: ${error.detail || 'Unknown error'}`);
        }
    } catch (error) {
        console.error('Failed to delete persona:', error);
        alert(`Error: ${error.message}`);
    }
}

// Settings functions
async function openSettings() {
    settingsModal.classList.remove('hidden');
    await loadSettings();
}

function closeSettings() {
    settingsModal.classList.add('hidden');
    // Clear password inputs on close
    openaiKeyInput.value = '';
    anthropicKeyInput.value = '';
}

async function loadSettings() {
    try {
        const response = await fetch('/api/settings');
        const data = await response.json();

        // Update key status indicators
        updateKeyStatus('openai', data.openai_api_key_set, data.openai_api_key_masked);
        updateKeyStatus('anthropic', data.anthropic_api_key_set, data.anthropic_api_key_masked);

        // Populate model dropdown
        modelSelect.innerHTML = '';
        data.available_models.forEach(model => {
            const option = document.createElement('option');
            option.value = model.id;
            option.textContent = model.name;
            if (model.id === data.model) {
                option.selected = true;
            }
            modelSelect.appendChild(option);
        });

        // Set permission level
        permissionSelect.value = data.permission_level;

    } catch (error) {
        console.error('Failed to load settings:', error);
    }
}

function updateKeyStatus(provider, isSet, maskedKey) {
    const statusEl = provider === 'openai' ? openaiKeyStatus : anthropicKeyStatus;
    const inputEl = provider === 'openai' ? openaiKeyInput : anthropicKeyInput;

    if (isSet) {
        statusEl.textContent = maskedKey;
        statusEl.className = 'key-status key-set';
        inputEl.placeholder = 'Enter new key to replace';
    } else {
        statusEl.textContent = 'Not set';
        statusEl.className = 'key-status key-not-set';
        inputEl.placeholder = provider === 'openai' ? 'sk-...' : 'sk-ant-...';
    }
}

async function saveSettings() {
    const updates = {};

    // Only include API keys if user entered new ones
    if (openaiKeyInput.value.trim()) {
        updates.openai_api_key = openaiKeyInput.value.trim();
    }
    if (anthropicKeyInput.value.trim()) {
        updates.anthropic_api_key = anthropicKeyInput.value.trim();
    }

    // Always include model and permission
    updates.model = modelSelect.value;
    updates.permission_level = parseInt(permissionSelect.value);

    try {
        settingsSaveBtn.disabled = true;
        settingsSaveBtn.textContent = 'Saving...';

        const response = await fetch('/api/settings', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(updates)
        });

        if (response.ok) {
            const data = await response.json();
            // Reload settings to show updated status
            await loadSettings();
            // Clear password fields
            openaiKeyInput.value = '';
            anthropicKeyInput.value = '';
            // Show success briefly
            settingsSaveBtn.textContent = 'Saved!';
            setTimeout(() => {
                settingsSaveBtn.textContent = 'Save Settings';
                settingsSaveBtn.disabled = false;
            }, 1500);
        } else {
            const error = await response.json();
            alert(`Failed to save: ${error.detail || 'Unknown error'}`);
            settingsSaveBtn.textContent = 'Save Settings';
            settingsSaveBtn.disabled = false;
        }
    } catch (error) {
        console.error('Failed to save settings:', error);
        alert(`Error: ${error.message}`);
        settingsSaveBtn.textContent = 'Save Settings';
        settingsSaveBtn.disabled = false;
    }
}
