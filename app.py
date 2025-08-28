from flask import Flask, render_template_string, request, send_file
import requests
import re
from io import BytesIO
from zipfile import ZipFile, ZIP_DEFLATED

app = Flask(__name__)

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Cambridge Pronunciation Downloader</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap" rel="stylesheet">
<style>
body { font-family: 'Inter', sans-serif; background: linear-gradient(135deg,#6C5B7B,#C06C84,#F67280); min-height:100vh; display:flex; justify-content:center; align-items:center; padding:20px; color:#fff;}
.container { background: rgba(0,0,0,0.6); backdrop-filter: blur(10px); border-radius:20px; padding:40px 50px; width:100%; max-width:600px; text-align:center; box-shadow:0 8px 30px rgba(0,0,0,0.4);}
h2 { font-weight:700; font-size:28px; margin-bottom:15px; text-shadow:1px 1px 4px rgba(0,0,0,0.5);}
.tip { font-size:14px; color:#e0e0e0; margin-bottom:20px; }

/* Input + Add button */
#wordInput { width:70%; padding:12px; border-radius:12px; border:none; outline:none; font-size:16px; }
#addBtn { padding:12px 20px; font-size:16px; border-radius:12px; border:none; cursor:pointer; font-weight:600; color:#fff; background:linear-gradient(45deg,#FFC371,#FF5F6D); transition:all 0.3s; margin-left:10px;}
#addBtn:hover { transform: translateY(-2px); box-shadow:0 6px 15px rgba(0,0,0,0.3); background:linear-gradient(45deg,#FF5F6D,#FFC371);}
#addBtn:active { transform:translateY(0); box-shadow:0 3px 8px rgba(0,0,0,0.3); }

/* Word list styling */
#wordList { list-style:none; padding:0; margin-top:20px; max-height:200px; overflow-y:auto; text-align:left;}
#wordList li { background: rgba(255,255,255,0.1); margin-bottom:10px; padding:10px 15px; border-radius:12px; display:flex; justify-content:space-between; align-items:center; transition: all 0.2s;}
#wordList li:hover { background: rgba(255,255,255,0.2);}
.deleteBtn { cursor:pointer; color:#FF5F6D; font-weight:bold; font-size:16px; transition:color 0.2s;}
.deleteBtn:hover { color:#FFC371; }
button#downloadBtn  { padding:12px 20px; font-size:16px; border-radius:12px; border:none; cursor:pointer; font-weight:600; color:#fff; background:linear-gradient(45deg,#FFC371,#FF5F6D); transition:all 0.3s; }
button#downloadBtn :hover { transform: translateY(-2px); box-shadow:0 6px 15px rgba(0,0,0,0.3); background:linear-gradient(45deg,#FF5F6D,#FFC371);}
# button:active { transform:translateY(0); box-shadow:0 3px 8px rgba(0,0,0,0.3);}
</style>
</head>
<body>
<div class="container">
<h2>Cambridge Pronunciation Downloader</h2>
<p class="tip">Add words one by one. Remove unwanted words using the dustbin icon before downloading.</p>

<form id="wordForm" method="POST">
  <div style="display:flex; gap:10px;">
    <input type="text" id="wordInput" placeholder="Enter a word" />
    <button type="button" id="addBtn">Add</button>
  </div>

  <ul id="wordList"></ul>

  <button type="submit" id="downloadBtn">Download All</button>
</form>
</div>

<script>
const wordInput = document.getElementById('wordInput');
const addBtn = document.getElementById('addBtn');
const wordList = document.getElementById('wordList');
const form = document.getElementById('wordForm');

function createWordItem(word){
  const li = document.createElement('li');
  li.dataset.word = word;  // store the word safely
  li.textContent = word;

  const deleteBtn = document.createElement('span');
  deleteBtn.innerHTML = '🗑';
  deleteBtn.classList.add('deleteBtn');
  deleteBtn.onclick = ()=> li.remove();

  li.appendChild(deleteBtn);
  wordList.appendChild(li);
}


// Add word to list
addBtn.addEventListener('click', ()=>{
  const word = wordInput.value.trim();
  if(word){
    createWordItem(word);
    wordInput.value = '';
  }
});

// Submit form with hidden inputs
form.addEventListener('submit', (e)=>{
  e.preventDefault();  // stop default submit

  // Remove previous hidden inputs
  document.querySelectorAll('input[name="words[]"]').forEach(el => el.remove());

  // Add hidden inputs for each word (use li.dataset.word for safety)
  document.querySelectorAll('#wordList li').forEach(li=>{
    const input = document.createElement('input');
    input.type = 'hidden';
    input.name = 'words[]';
    input.value = li.dataset.word; // store the word in a dataset
    form.appendChild(input);
  });

  form.submit(); // now submit
});
</script>   
</body>
</html>
"""

def slugify(word: str) -> str:
    w = re.sub(r"\s+", "-", word.strip().lower())
    w = re.sub(r"[^a-z0-9\-']", "", w)
    return w

def fetch_us_pronunciation_bytes(word: str):
    headers = {"User-Agent": "Mozilla/5.0"}
    url = f"https://dictionary.cambridge.org/dictionary/english/{slugify(word)}"
    try:
        r = requests.get(url, headers=headers, timeout=15)
        if r.status_code != 200:
            return None
        # regex to find US pronunciation mp3 URL
        match = re.search(r'data-src-mp3="([^"]*us_pron[^"]*)"', r.text)
        if not match:
            match = re.search(r'<source type="audio/mpeg" src="([^"]*us_pron[^"]*)"', r.text)
        if not match:
            return None
        src = match.group(1)
        if src.startswith("//"):
            audio_url = "https:" + src
        elif src.startswith("http"):
            audio_url = src
        else:
            audio_url = "https://dictionary.cambridge.org" + src
        audio = requests.get(audio_url, headers=headers, timeout=15)
        if audio.status_code != 200 or not audio.content:
            return None
        return audio.content
    except:
        return None

@app.route("/", methods=["GET", "POST"])
def index():
    words_text = ""
    if request.method == "POST":
        words = request.form.getlist('words[]')
        words = [w.strip() for w in words if w.strip()]
        if not words:
            return "<h3>Please enter at least one word.</h3>", 400

        zip_buffer = BytesIO()
        with ZipFile(zip_buffer, "w", ZIP_DEFLATED) as zip_file:
            for word in words:
                audio_bytes = fetch_us_pronunciation_bytes(word)
                if audio_bytes:
                    filename = f"{slugify(word)}.mp3"  # no "_us"
                    zip_file.writestr(filename, audio_bytes)
        zip_buffer.seek(0)
        return send_file(zip_buffer, as_attachment=True, download_name="pronunciations.zip", mimetype="application/zip")

    return render_template_string(HTML_TEMPLATE, words_text=words_text)

if __name__ == "__main__":
    app.run(debug=True)
