from flask import Flask, request, jsonify, render_template_string
from flask_cors import CORS
import sqlite3
import os

app = Flask(__name__)
CORS(app)

# ✅ ডাটাবেজ ইনিশিয়ালাইজেশন ও কলাম চেক করে যোগ করা
def init_db():
    conn = sqlite3.connect('library.db')
    c = conn.cursor()

    # টেবিল না থাকলে তৈরি করুন
    c.execute('''
        CREATE TABLE IF NOT EXISTS books (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL
        )
    ''')

    # কলামগুলো যোগ করুন (যদি না থাকে)
    try: c.execute("ALTER TABLE books ADD COLUMN writer TEXT")
    except sqlite3.OperationalError: pass
    try: c.execute("ALTER TABLE books ADD COLUMN subject TEXT")
    except sqlite3.OperationalError: pass
    try: c.execute("ALTER TABLE books ADD COLUMN section TEXT")
    except sqlite3.OperationalError: pass

    conn.commit()
    conn.close()

init_db()

# ✅ HTML UI
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
          width: 320px;
          font-family: Arial, sans-serif;
        }
        input, textarea {
          width: 100%;
          margin-top: 6px;
          margin-bottom: 12px;
          padding: 8px;
          font-family: inherit;
          box-sizing: border-box;
        }
        button {
          cursor: pointer;
          padding: 10px 20px;
          font-size: 1rem;
        }
        ul {
          padding-left: 20px;
        }
        li {
          margin-bottom: 8px;
        }
      </style>
    </head>
    <body>

      <div class="card">
        <h3>বই যোগ করুন</h3>
        <label>বইয়ের নাম:</label>
        <input type="text" id="bookTitle" placeholder="বইয়ের নাম লিখুন..." />
        
        <label>লেখকের নাম:</label>
        <input type="text" id="bookWriter" placeholder="লেখকের নাম লিখুন..." />
        
        <label>বিষয়:</label>
        <input type="text" id="bookSubject" placeholder="বিষয় লিখুন..." />
        
        <label>সেকশন:</label>
        <input type="text" id="bookSection" placeholder="সেকশন লিখুন..." />
        
        <button onclick="addBook()">বই সংরক্ষণ করুন</button>
      </div>

      <div class="card">
        <h3>বইয়ের লাইব্রেরি</h3>
        <ul id="bookList"></ul>
      </div>

      <script>
        async function addBook() {
          const title = document.getElementById('bookTitle').value.trim();
          const writer = document.getElementById('bookWriter').value.trim();
          const subject = document.getElementById('bookSubject').value.trim();
          const section = document.getElementById('bookSection').value.trim();

          if (!title || !writer || !subject || !section) {
            alert("অনুগ্রহ করে সব তথ্য পূরণ করুন!");
            return;
          }

          const response = await fetch('/add_book', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ title, writer, subject, section })
          });

          if (response.ok) {
            document.getElementById('bookTitle').value = '';
            document.getElementById('bookWriter').value = '';
            document.getElementById('bookSubject').value = '';
            document.getElementById('bookSection').value = '';
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
            li.innerHTML = `<strong>${book.title}</strong><br>লেখক: ${book.writer} | বিষয়: ${book.subject} | সেকশন: ${book.section}`;
            list.appendChild(li);
          });
        }

        window.onload = loadBooks;
      </script>

    </body>
    </html>
    '''
    return render_template_string(html)

# ✅ API: বই যোগ করা
@app.route('/add_book', methods=['POST'])
def add_book():
    data = request.get_json()
    title = data.get('title')
    writer = data.get('writer')
    subject = data.get('subject')
    section = data.get('section')

    if not all([title, writer, subject, section]):
        return jsonify({'error': 'সব তথ্য প্রদান করুন'}), 400

    conn = sqlite3.connect('library.db')
    c = conn.cursor()
    c.execute('INSERT INTO books (title, writer, subject, section) VALUES (?, ?, ?, ?)', (title, writer, subject, section))
    conn.commit()
    conn.close()
    return jsonify({'message': 'বই সফলভাবে যোগ করা হয়েছে'}), 201

# ✅ API: সব বই পড়া
@app.route('/books', methods=['GET'])
def get_books():
    conn = sqlite3.connect('library.db')
    c = conn.cursor()
    c.execute('SELECT id, title, writer, subject, section FROM books')
    books = [{'id': row[0], 'title': row[1], 'writer': row[2], 'subject': row[3], 'section': row[4]} for row in c.fetchall()]
    conn.close()
    return jsonify(books)

# ✅ অ্যাপ চালানো — port 80 ও public IP access
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=80)
