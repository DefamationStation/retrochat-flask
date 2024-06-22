from flask import Flask, render_template, request, jsonify, session
import requests
import os
import json

app = Flask(__name__)
app.secret_key = 'secretkey'  # Replace with a secure key
API_URL = 'http://192.168.1.82:11434/api/chat'
DEFAULT_CHAT_FILE = 'chat_history.json'

def get_current_chat_file():
    return session.get('chat_file', DEFAULT_CHAT_FILE)

def load_chat_history(chat_file=None):
    if chat_file is None:
        chat_file = get_current_chat_file()
    if not os.path.exists(chat_file) or os.path.getsize(chat_file) == 0:
        return []
    with open(chat_file, 'r') as file:
        return json.load(file)

def save_chat_history(history, chat_file=None):
    if chat_file is None:
        chat_file = get_current_chat_file()
    with open(chat_file, 'w') as file:
        json.dump(history, file)

@app.route('/')
def index():
    return render_template('chat.html')

@app.route('/send_message', methods=['POST'])
def send_message():
    try:
        user_input = request.json['message']
        chat_file = get_current_chat_file()
        chat_history = load_chat_history(chat_file)

        # Check for the /chat reset command
        if user_input.strip().lower() == '/chat reset':
            print("Received /chat reset command. Clearing chat history.")
            # Retain only the system prompt in the chat history
            system_prompt = next((msg for msg in chat_history if msg.get('role') == 'system'), None)
            new_history = [system_prompt] if system_prompt else []
            save_chat_history(new_history, chat_file)
            session['chat_history'] = new_history
            return jsonify('Chat history has been reset, system prompt retained.')

        # Check for the /chat rename command
        if user_input.strip().lower().startswith('/chat rename '):
            new_name = user_input[len('/chat rename '):].strip()
            new_file = f"{new_name}.json"
            if os.path.exists(new_file):
                return jsonify(f"Chat file '{new_file}' already exists.")
            os.rename(chat_file, new_file)
            session['chat_file'] = new_file
            return jsonify(f"Chat renamed to '{new_name}'.")

        # Check for the /chat delete command
        if user_input.strip().lower() == '/chat delete':
            if chat_file != DEFAULT_CHAT_FILE:
                os.remove(chat_file)
                session.pop('chat_file', None)
                # Signal the need to refresh the page
                return jsonify(f"Chat '{chat_file}' deleted. Please refresh the page.", {'refresh': True})
            else:
                return jsonify("Cannot delete the default chat.")

        # Check for the /chat open command
        if user_input.strip().lower().startswith('/chat open '):
            new_chat = user_input[len('/chat open '):].strip()
            new_file = f"{new_chat}.json"
            if not os.path.exists(new_file):
                save_chat_history([], new_file)  # Create the file with an empty history
            session['chat_file'] = new_file
            # Signal the need to refresh the page
            return jsonify(f"Chat '{new_chat}' opened. Please refresh the page.", {'refresh': True})

        # Check for the /chat list command
        if user_input.strip().lower() == '/chat list':
            chat_files = [f for f in os.listdir('.') if f.endswith('.json')]
            chat_names = [os.path.splitext(f)[0] for f in chat_files]
            return jsonify(f"Available chats: {', '.join(chat_names)}")

        # Check for the /system command
        if user_input.strip().lower().startswith('/system '):
            system_prompt = user_input[len('/system '):].strip()
            print(f"Setting system prompt to: {system_prompt}")
            if chat_history and chat_history[0].get('role') == 'system':
                chat_history[0]['content'] = system_prompt
            else:
                chat_history.insert(0, {'role': 'system', 'content': system_prompt})
            session['chat_history'] = chat_history
            save_chat_history(chat_history, chat_file)
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
            save_chat_history(chat_history, chat_file)
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
    chat_file = get_current_chat_file()
    chat_history = load_chat_history(chat_file)
    return jsonify(chat_history)

if __name__ == '__main__':
    app.run(host='0.0.0.0', debug=True)