function sendMessage() {
    var input = document.getElementById('user_input');
    var message = input.value;
    input.value = '';
    updateChatbox(message, 'user');

    // Use EventSource for streaming responses
    var eventSource = new EventSource('/send_message');
    
    eventSource.onmessage = function(event) {
        updateChatbox(event.data, 'ai');
    };

    eventSource.onerror = function(event) {
        updateChatbox('Error connecting to server.', 'ai');
        eventSource.close();
    };
}

function updateChatbox(msg, type) {
    var chatbox = document.getElementById('chatbox');
    var messageElement = document.createElement('div');

    var parsedContent = DOMPurify.sanitize(marked.parse(msg));

    messageElement.innerHTML = parsedContent;
    if (type === 'ai') {
        messageElement.classList.add('ai-message');
    } else {
        messageElement.classList.add('user-message');
    }
    chatbox.appendChild(messageElement);

    chatbox.scrollTop = chatbox.scrollHeight;
}