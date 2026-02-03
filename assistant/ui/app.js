/**
 * AI Assistant - Frontend Logic
 */

// State
let currentConversationId = null;
let pendingFiles = []; // Files waiting to be sent with next message
let isRecording = false;
let speechRecognition = null;

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
const conversationsList = document.getElementById('conversations-list');
const newConversationBtn = document.getElementById('new-conversation-btn');
const refreshMetricsBtn = document.getElementById('refresh-metrics-btn');
const toggleStatusBtn = document.getElementById('toggle-status-btn');
const statusPanel = document.querySelector('.status-panel');

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

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    loadStatus();
    loadConversations();
    loadMetrics();
    setupEventListeners();
    initVoiceInput();

    // Refresh metrics every 30 seconds
    setInterval(loadMetrics, 30000);
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

    // New conversation
    newConversationBtn.addEventListener('click', startNewConversation);

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
}

function toggleStatusPanel() {
    statusPanel.classList.toggle('show');
    toggleStatusBtn.textContent = statusPanel.classList.contains('show') ? 'Close' : 'Menu';
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

    // Add loading indicator
    const loadingEl = addMessageToUI('loading', 'Thinking...');

    // Prepare file IDs
    const fileIds = pendingFiles.map(f => f.file_id);
    clearPendingFiles();

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
            // Update conversation ID if new
            if (!currentConversationId) {
                currentConversationId = data.conversation_id;
                loadConversations(); // Refresh list
            }

            // Add assistant response with model info
            addMessageToUI('assistant', data.response, data.model);
        } else {
            addMessageToUI('error', `Error: ${data.detail || 'Unknown error'}`);
        }
    } catch (error) {
        loadingEl.remove();
        addMessageToUI('error', `Error: ${error.message}`);
    }

    sendBtn.disabled = false;
    messageInput.focus();
}

function addMessageToUI(role, content, model = null) {
    const messageEl = document.createElement('div');
    messageEl.className = `message ${role}`;
    messageEl.textContent = content;

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

async function loadConversations() {
    try {
        const response = await fetch('/api/conversations');
        const data = await response.json();

        conversationsList.innerHTML = '';
        data.conversations.forEach(conv => {
            const li = document.createElement('li');
            li.textContent = conv.title || `Conversation (${conv.message_count} msgs)`;
            li.dataset.id = conv.id;
            if (conv.id === currentConversationId) {
                li.classList.add('active');
            }
            li.addEventListener('click', () => loadConversation(conv.id));
            conversationsList.appendChild(li);
        });
    } catch (error) {
        console.error('Failed to load conversations:', error);
    }
}

async function loadConversation(conversationId) {
    try {
        const response = await fetch(`/api/conversation/${conversationId}`);
        const data = await response.json();

        if (response.ok) {
            currentConversationId = conversationId;
            messagesContainer.innerHTML = '';

            // Display messages
            data.messages.forEach(msg => {
                addMessageToUI(msg.role, msg.content);
            });

            // Update active state in list
            document.querySelectorAll('#conversations-list li').forEach(li => {
                li.classList.toggle('active', li.dataset.id === conversationId);
            });
        }
    } catch (error) {
        console.error('Failed to load conversation:', error);
    }
}

function startNewConversation() {
    currentConversationId = null;
    messagesContainer.innerHTML = '';

    // Clear active state
    document.querySelectorAll('#conversations-list li').forEach(li => {
        li.classList.remove('active');
    });

    messageInput.focus();
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
    } catch (error) {
        if (currentFocusEl) currentFocusEl.textContent = 'Error loading status';
        if (lastRunEl) lastRunEl.textContent = 'Error loading status';
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
