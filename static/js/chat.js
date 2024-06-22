function sendMessage() {
    var input = document.getElementById('user_input');
    var message = input.value;
    input.value = '';
    updateChatbox(message, 'user');

    fetch('/send_message', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({message: message})
    }).then(response => response.json())
    .then(data => {
        if (data[1] && data[1].refresh) {
            location.reload();
        } else if (data === 'Chat history has been reset, system prompt retained.') {
            loadChatHistory();
        } else {
            updateChatbox(data.error || data.message || data, 'ai');
        }
    }).catch(err => console.error('Error:', err));
}

function updateChatbox(msg, type) {
    var chatbox = document.getElementById('chatbox');
    var messageElement = document.createElement('div');
    
    var parsedContent = DOMPurify.sanitize(marked.parse(msg));

    messageElement.innerHTML = parsedContent;
    if (type === 'ai') {
        messageElement.classList.add('ai-message');
    } else if (type === 'system') {
        messageElement.classList.add('system-message');
    } else {
        messageElement.classList.add('user-message');
    }
    chatbox.appendChild(messageElement);
    chatbox.scrollTop = chatbox.scrollHeight;
}

// Load chat history from the server
function loadChatHistory() {
    fetch('/get_history')
        .then(response => response.json())
        .then(history => {
            document.getElementById('chatbox').innerHTML = ''; // Clear the chatbox
            history.forEach(item => {
                const role = item.role === 'user' ? 'user' : (item.role === 'system' ? 'system' : 'ai');
                updateChatbox(item.content, role);
            });
        })
        .catch(err => console.error('Error loading history:', err));
    
    // Remove fetch call for system prompt as it is not needed anymore
    /*
    fetch('/get_system_prompt')
        .then(response => response.json())
        .then(data => {
            document.getElementById('system_prompt').innerText = data.system_prompt;
        })
        .catch(err => console.error('Error loading system prompt:', err));
    */
}

// Remove the updateSystemPrompt function as it's no longer needed
/*
function updateSystemPrompt(newPrompt) {
    document.getElementById('system_prompt').innerText = newPrompt;
}
*/

// Call the function to load chat history on page load
document.addEventListener('DOMContentLoaded', function() {
    loadChatHistory();
});

// Ensure the input box is visible when focused
document.getElementById('user_input').addEventListener('focus', function() {
    adjustChatboxHeight();
    var chatbox = document.getElementById('chatbox');
    setTimeout(() => chatbox.scrollTop = chatbox.scrollHeight, 300); // Delay to allow for any keyboard animations
});

// Adjust the chatbox height dynamically
window.addEventListener('resize', adjustChatboxHeight);

function adjustChatboxHeight() {
    var inputContainer = document.getElementById('user_input_container');
    var chatbox = document.getElementById('chatbox');
    var availableHeight = window.innerHeight - inputContainer.offsetHeight;
    chatbox.style.height = availableHeight + 'px';
}

// Call the function initially to set the correct height
adjustChatboxHeight();

// Ensure the chatbox scrolls to the bottom on load
document.addEventListener('DOMContentLoaded', function() {
    var chatbox = document.getElementById('chatbox');
    chatbox.scrollTop = chatbox.scrollHeight;
});
