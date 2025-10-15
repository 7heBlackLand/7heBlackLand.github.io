from flask import Flask, request, jsonify, render_template_string
from flask_cors import CORS
import sqlite3

app = Flask(__name__)
CORS(app)

# ডাটাবেজ ইনিশিয়ালাইজেশন
def init_db():
    conn = sqlite3.connect('library.db')
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS books (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# হোম পেজে HTML সরবরাহ করা হচ্ছে
@app.route('/')
def home():
    html = '''
    <!DOCTYPE html>
    <html lang="bn">
    <head>
      <meta charset="UTF-8" />
      <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
      <title>বইয়ের লাইব্রেরি</title>
      <style>
        .card {
          border: 1px solid #aaa;
          padding: 16px;
          margin: 10px;
          border-radius: 8px;
          width: 300px;
          font-family: Arial, sans-serif;
        }
        textarea {
          width: 100%;
          font-family: inherit;
        }
        button {
          cursor: pointer;
          padding: 8px 16px;
          font-size: 1rem;
        }
      </style>
    </head>
    <body>

      <div class="card">
        <h3>বই যোগ করুন</h3>
        <textarea id="bookInput" rows="3" placeholder="বইয়ের শিরোনাম লিখুন..."></textarea>
        <br><br>
        <button onclick="addBook()">বই সংরক্ষণ করুন</button>
      </div>

      <div class="card">
        <h3>বইয়ের লাইব্রেরি</h3>
        <ul id="bookList"></ul>
      </div>

      <script>
        async function addBook() {
          const title = document.getElementById('bookInput').value;
          if (!title.trim()) return alert("অনুগ্রহ করে বইয়ের শিরোনাম লিখুন!");

          const response = await fetch('/add_book', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ title })
          });

          if (response.ok) {
            document.getElementById('bookInput').value = '';
            loadBooks();
          } else {
            alert("বই যোগ করতে সমস্যা হয়েছে");
          }
        }

        async function loadBooks() {
          const res = await fetch('/books');
          const books = await res.json();
          const list = document.getElementById('bookList');
          list.innerHTML = '';
          books.forEach(book => {
            const li = document.createElement('li');
            li.innerText = book.title;
            list.appendChild(li);
          });
        }

        window.onload = loadBooks;
      </script>

    </body>
    </html>
    '''
    return render_template_string(html)

@app.route('/add_book', methods=['POST'])
def add_book():
    data = request.get_json()
    title = data.get('title')
    if not title:
        return jsonify({'error': 'শিরোনাম প্রদান করা হয়নি'}), 400

    conn = sqlite3.connect('library.db')
    c = conn.cursor()
    c.execute('INSERT INTO books (title) VALUES (?)', (title,))
    conn.commit()
    conn.close()
    return jsonify({'message': 'বই সফলভাবে যোগ করা হয়েছে'}), 201

@app.route('/books', methods=['GET'])
def get_books():
    conn = sqlite3.connect('library.db')
    c = conn.cursor()
    c.execute('SELECT id, title FROM books')
    books = [{'id': row[0], 'title': row[1]} for row in c.fetchall()]
    conn.close()
    return jsonify(books)

if __name__ == '__main__':
    app.run(port=80)
