from flask import Flask, render_template, request, jsonify, session, g, redirect
import requests
import os
import json
import markdown
import sqlite3

app = Flask(__name__)
app.secret_key = 'secretkey'  # Replace with a secure key
API_URL = 'http://192.168.1.82:11434/api/chat'
DB_FILE = 'chat_history.db'

class ChatHistoryManager:
    def __init__(self, db_file: str, chat_name: str = 'default'):
        self.db_file = db_file
        self.chat_name = chat_name

    def get_connection(self):
        if 'conn' not in g:
            g.conn = sqlite3.connect(self.db_file)
            self._create_tables(g.conn)
        return g.conn

    def _create_tables(self, conn):
        with conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS chat_sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_name TEXT NOT NULL UNIQUE,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            conn.execute('''
                CREATE TABLE IF NOT EXISTS chat_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id INTEGER,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(session_id) REFERENCES chat_sessions(id)
                )
            ''')

    def _get_session_id(self, conn, chat_name: str):
        cursor = conn.cursor()
        cursor.execute('SELECT id FROM chat_sessions WHERE chat_name = ?', (chat_name,))
        session = cursor.fetchone()
        if session:
            return session[0]
        else:
            cursor.execute('INSERT INTO chat_sessions (chat_name) VALUES (?)', (chat_name,))
            return cursor.lastrowid

    def set_chat_name(self, chat_name: str):
        self.chat_name = chat_name

    def save_history(self, history):
        conn = self.get_connection()
        session_id = self._get_session_id(conn, self.chat_name)
        with conn:
            conn.execute('DELETE FROM chat_messages WHERE session_id = ?', (session_id,))
            for message in history:
                conn.execute('''
                    INSERT INTO chat_messages (session_id, role, content) VALUES (?, ?, ?)
                ''', (session_id, message['role'], message['content']))

    def load_history(self):
        conn = self.get_connection()
        session_id = self._get_session_id(conn, self.chat_name)
        cursor = conn.cursor()
        cursor.execute('SELECT role, content FROM chat_messages WHERE session_id = ? ORDER BY timestamp', (session_id,))
        messages = cursor.fetchall()
        return [{'role': role, 'content': content} for role, content in messages]

    def clear_history(self):
        conn = self.get_connection()
        session_id = self._get_session_id(conn, self.chat_name)
        with conn:
            conn.execute('DELETE FROM chat_messages WHERE session_id = ?', (session_id,))

    def rename_history(self, new_name):
        conn = self.get_connection()
        session_id = self._get_session_id(conn, self.chat_name)
        with conn:
            conn.execute('UPDATE chat_sessions SET chat_name = ? WHERE id = ?', (new_name, session_id))
        self.set_chat_name(new_name)

    def delete_history(self):
        conn = self.get_connection()
        session_id = self._get_session_id(conn, self.chat_name)
        with conn:
            conn.execute('DELETE FROM chat_messages WHERE session_id = ?', (session_id,))
            conn.execute('DELETE FROM chat_sessions WHERE id = ?', (session_id,))
        self.set_chat_name('default')

    def list_chats(self):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT chat_name FROM chat_sessions')
        return [row[0] for row in cursor.fetchall()]

# Initialize chat history manager
history_manager = ChatHistoryManager(DB_FILE)
history_manager.set_chat_name('default')  # Set default chat name

@app.before_request
def before_request():
    g.conn = sqlite3.connect(DB_FILE)

@app.teardown_request
def teardown_request(exception):
    conn = g.pop('conn', None)
    if conn is not None:
        conn.close()

@app.route('/')
def index():
    if 'mode' not in session or 'model' not in session:
        return redirect('/select_mode')
    return render_template('chat.html')

@app.route('/select_mode', methods=['GET', 'POST'])
def select_mode():
    if request.method == 'POST':
        session['mode'] = request.form['mode']
        return redirect('/select_model')
    return render_template('select_mode.html')

@app.route('/select_model', methods=['GET', 'POST'])
def select_model():
    if request.method == 'POST':
        session['model'] = request.form['model']
        return redirect('/')
    models = get_ollama_models()
    return render_template('select_model.html', models=models)

def get_ollama_models():
    url = "http://192.168.1.82:11434/api/tags"
    response = requests.get(url)
    if response.status_code == 200:
        models_info = response.json()
        if isinstance(models_info, dict) and 'models' in models_info:
            return [model['name'] for model in models_info['models']]
    return []

@app.route('/send_message', methods=['POST'])
def send_message():
    try:
        user_input = request.json['message']
        chat_history = history_manager.load_history()

        # Process commands
        if user_input.strip().startswith('/'):
            return handle_commands(user_input, chat_history)

        # Append user's message to chat history
        chat_history.append({'role': 'user', 'content': user_input})

        # Prepare data for API call based on mode
        data = {
            'messages': [{'role': msg['role'], 'content': msg['content']} for msg in chat_history],
            'stream': False
        }

        if session.get('mode') == 'Ollama':
            data['model'] = session.get('model', 'default_model')
            response = requests.post(API_URL, json=data)
        elif session.get('mode') == 'Anthropic':
            data['model'] = 'claude-3-5-sonnet-20240620'
            response = requests.post('https://api.anthropic.com/v1/messages', json=data, headers={
                "X-API-Key": os.getenv('ANTHROPIC_API_KEY')
            })
        elif session.get('mode') == 'OpenAI':
            data['model'] = 'gpt-4'
            response = requests.post('https://api.openai.com/v1/chat/completions', json=data, headers={
                "Authorization": f"Bearer {os.getenv('OPENAI_API_KEY')}"
            })

        if response.status_code == 200:
            ai_response = response.json()['message']['content']
            chat_history.append({'role': 'assistant', 'content': ai_response})
            history_manager.save_history(chat_history)
            return jsonify({'message': markdown.markdown(ai_response)})
        else:
            return jsonify({'error': 'Failed to connect to model server'}), 500
    except Exception as e:
        print(f"Exception: {e}")
        return jsonify({'error': 'An error occurred on the server.'}), 500

def handle_commands(command, chat_history):
    command = command.strip().lower()

    if command == '/chat reset':
        history_manager.clear_history()
        return jsonify('Chat history has been reset.')

    if command.startswith('/chat rename '):
        new_name = command[len('/chat rename '):].strip()
        history_manager.rename_history(new_name)
        return jsonify(f'Chat renamed to {new_name}.')

    if command == '/chat delete':
        history_manager.delete_history()
        return jsonify('Chat deleted.')

    if command == '/chat list':
        chats = history_manager.list_chats()
        return jsonify(f'Available chats: {", ".join(chats)}')

    if command.startswith('/chat open '):
        new_chat = command[len('/chat open '):].strip()
        history_manager.set_chat_name(new_chat)
        return jsonify(f'Chat {new_chat} opened.')

    return jsonify('Unknown command.')

@app.route('/get_history', methods=['GET'])
def get_history():
    chat_history = history_manager.load_history()
    return jsonify(chat_history)

if __name__ == '__main__':
    app.run(host='0.0.0.0', debug=True)
