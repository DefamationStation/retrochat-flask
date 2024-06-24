from flask import Flask, render_template, request, jsonify, session, g, redirect, Response
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
        self._create_tables()

    def get_connection(self):
        if 'conn' not in g:
            g.conn = sqlite3.connect(self.db_file)
        return g.conn

    def _create_tables(self):
        conn = sqlite3.connect(self.db_file)
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
        conn.close()

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
    session.pop('mode', None)
    session.pop('model', None)
    return redirect('/select_mode')

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
        return redirect('/chat')
    models = get_ollama_models()
    return render_template('select_model.html', models=models)

@app.route('/chat')
def chat():
    if 'mode' not in session or 'model' not in session:
        return redirect('/select_mode')
    return render_template('chat.html')

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
    user_input = request.json['message']
    chat_history = history_manager.load_history()

    if user_input.strip().startswith('/'):
        return handle_commands(user_input, chat_history)

    chat_history.append({'role': 'user', 'content': user_input})
    history_manager.save_history(chat_history)

    data = {
        'model': session.get('model', 'default_model'),
        'messages': [{'role': msg['role'], 'content': msg['content']} for msg in chat_history],
        'stream': True
    }

    def generate():
        response = requests.post(API_URL, json=data, stream=True)
        complete_message = ""
        for line in response.iter_lines():
            if line:
                response_json = json.loads(line)
                message_content = response_json.get('message', {}).get('content', '')
                complete_message += message_content
                yield f"data: {json.dumps({'content': message_content})}\n\n"
                if response_json.get('done', False):
                    break
        chat_history.append({'role': 'assistant', 'content': complete_message})
        history_manager.save_history(chat_history)

    return Response(generate(), content_type='text/event-stream')

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