from flask import Flask, render_template, request, jsonify, session
import requests
import os
import json

app = Flask(__name__)
app.secret_key = 'seth2113'  # Replace with a secure key
API_URL = 'http://192.168.1.82:11434/api/chat'
CHAT_HISTORY_FILE = 'chat_history.json'

def load_chat_history():
    if not os.path.exists(CHAT_HISTORY_FILE) or os.path.getsize(CHAT_HISTORY_FILE) == 0:
        return []
    with open(CHAT_HISTORY_FILE, 'r') as file:
        return json.load(file)

def save_chat_history(history):
    with open(CHAT_HISTORY_FILE, 'w') as file:
        json.dump(history, file)

@app.route('/')
def index():
    return render_template('chat.html')

@app.route('/send_message', methods=['POST'])
def send_message():
    try:
        user_input = request.json['message']
        chat_history = session.get('chat_history', load_chat_history())

        # Check for the /system command
        if user_input.strip().lower().startswith('/system '):
            system_prompt = user_input[len('/system '):].strip()
            print(f"Setting system prompt to: {system_prompt}")
            # Replace any existing system prompt or add if none exists
            if chat_history and chat_history[0].get('role') == 'system':
                chat_history[0]['content'] = system_prompt
            else:
                chat_history.insert(0, {'role': 'system', 'content': system_prompt})
            session['chat_history'] = chat_history
            save_chat_history(chat_history)
            return jsonify(f'System prompt set to: "{system_prompt}"')

        # Append the user's message to the chat history
        chat_history.append({'role': 'user', 'content': user_input})

        # Prepare the history for the API, ensuring the system prompt is included if set
        formatted_history = [{'role': msg['role'], 'content': msg['content']} for msg in chat_history]
        
        data = {
            'model': 'llama3:8b-instruct-q6_K',
            'messages': formatted_history,  # Include the formatted chat history
            'stream': False
        }
        
        response = requests.post(API_URL, json=data)
        
        if response.status_code == 200:
            ai_response = response.json()['message']['content']
            # Append the AI's response to the chat history with the correct role
            chat_history.append({'role': 'assistant', 'content': ai_response})
            session['chat_history'] = chat_history
            save_chat_history(chat_history)
            return jsonify(ai_response)
        else:
            print(f"Error: Received status code {response.status_code}")
            print(f"Response: {response.text}")
            return jsonify({'error': 'Failed to connect to model server'}), 500
    except Exception as e:
        print(f"Exception: {e}")
        return jsonify({'error': 'An error occurred on the server.'}), 500

@app.route('/get_history', methods=['GET'])
def get_history():
    chat_history = session.get('chat_history', load_chat_history())
    return jsonify(chat_history)

if __name__ == '__main__':
    app.run(host='0.0.0.0', debug=True)
