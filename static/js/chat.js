function sendMessage() {
    var input = document.getElementById('user_input');
    var message = input.value;
    input.value = '';
    updateChatbox(message, 'user');

    fetch('/send_message', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({message: message})
    }).then(response => {
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        
        function readStream() {
            reader.read().then(({ done, value }) => {
                if (done) {
                    return;
                }
                const chunk = decoder.decode(value);
                const lines = chunk.split('\n\n');
                lines.forEach(line => {
                    if (line.startsWith('data: ')) {
                        const data = JSON.parse(line.slice(6));
                        updateChatbox(data.content, 'ai');
                    }
                });
                readStream();
            });
        }
        
        readStream();
    }).catch(error => {
        console.error('Error:', error);
        updateChatbox('Error sending message to server.', 'system');
    });
}

function updateChatbox(msg, type) {
    var chatbox = document.getElementById('chatbox');
    var messageElement = document.createElement('div');

    var parsedContent = DOMPurify.sanitize(marked.parse(msg));

    messageElement.innerHTML = parsedContent;
    messageElement.classList.add(type + '-message');
    chatbox.appendChild(messageElement);

    chatbox.scrollTop = chatbox.scrollHeight;
}

function loadChatHistory() {
    fetch('/get_history')
        .then(response => response.json())
        .then(history => {
            document.getElementById('chatbox').innerHTML = '';
            history.forEach(item => {
                updateChatbox(item.content, item.role);
            });
        })
        .catch(err => console.error('Error loading history:', err));
}

document.addEventListener('DOMContentLoaded', loadChatHistory);