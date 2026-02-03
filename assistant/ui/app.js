/**
 * AI Assistant - Frontend Logic
 */

// State
let currentConversationId = null;
let pendingFiles = []; // Files waiting to be sent with next message

// DOM Elements
const messagesContainer = document.getElementById('messages');
const messageInput = document.getElementById('message-input');
const sendBtn = document.getElementById('send-btn');
const attachBtn = document.getElementById('attach-btn');
const fileInput = document.getElementById('file-input');
const filePreview = document.getElementById('file-preview');
const currentFocusEl = document.getElementById('current-focus');
const lastRunEl = document.getElementById('last-run');
const conversationsList = document.getElementById('conversations-list');
const newConversationBtn = document.getElementById('new-conversation-btn');
const refreshMetricsBtn = document.getElementById('refresh-metrics-btn');

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    loadStatus();
    loadConversations();
    loadMetrics();
    setupEventListeners();

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

        if (data.claude_code_focus) {
            currentFocusEl.textContent = data.claude_code_focus;
        } else {
            currentFocusEl.textContent = 'Not available';
        }

        if (data.last_run) {
            lastRunEl.textContent = `${data.last_run.file}: ${data.last_run.result || 'Unknown'}`;
        } else {
            lastRunEl.textContent = 'No recent runs';
        }
    } catch (error) {
        currentFocusEl.textContent = 'Error loading status';
        lastRunEl.textContent = 'Error loading status';
    }
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

        // Success rate
        if (totalRequests > 0) {
            const successCount = data.requests?.success || 0;
            const successRate = ((successCount / totalRequests) * 100).toFixed(1);
            successRateEl.textContent = `${successRate}%`;
            successRateEl.className = 'metric-value ' + (parseFloat(successRate) >= 90 ? 'metric-good' : 'metric-warn');
        } else {
            successRateEl.textContent = '-';
            successRateEl.className = 'metric-value';
        }

        // Average latency
        const avgLatency = data.latency_ms?.average;
        if (avgLatency !== undefined && avgLatency !== null) {
            latencyEl.textContent = `${Math.round(avgLatency)}ms`;
            latencyEl.className = 'metric-value ' + (avgLatency < 2000 ? 'metric-good' : 'metric-warn');
        } else {
            latencyEl.textContent = '-';
            latencyEl.className = 'metric-value';
        }

        // Total messages
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
