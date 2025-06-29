import os
import subprocess
import json
import uuid
import requests
from datetime import timedelta
from flask import Flask, request, redirect, url_for, render_template_string, flash, session
from werkzeug.utils import secure_filename

# Paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')
# Use Linux dumper binary instead of Windows exe
DUMPER_PATH = os.path.join(BASE_DIR, 'jsonDumper', 'net9.0', 'linux-x64', 'PkhexDump')
CACHE_PATH = os.path.join(BASE_DIR, 'pokeapi_cache.json')
DUMP_JSON_PATH = os.path.join(BASE_DIR, 'all_pokemon.json')
LOCATION_MAP_PATH = os.path.join(BASE_DIR, 'location_map.json')

# Ensure uploads directory exists
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Load location map
with open(LOCATION_MAP_PATH, 'r') as f:
    LOCATION_MAP = json.load(f)

# Load PokeAPI cache
try:
    with open(CACHE_PATH, 'r') as cf:
        POKEAPI_CACHE = json.load(cf)
except Exception:
    POKEAPI_CACHE = {}

# Flask app
app = Flask(__name__)
app.secret_key = 'supersecretkey'
# Use permanent sessions stored in cookies
app.config['SESSION_PERMANENT'] = True
app.permanent_session_lifetime = timedelta(days=3650)

# Helpers
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() == 'sav'

def run_dump(path):
    """Run the external dumper on a saved file path."""
    subprocess.run([DUMPER_PATH, path], check=True)

# HTML Templates with dark mode on upload page
INDEX_HTML = '''
<!doctype html>
<html lang="en" class="dark">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Upload Save</title>
  <link rel="stylesheet" href="{{ url_for('static', filename='css/style.css') }}">
  <style>
    body {
      background-color: #121212;
      color: #e0e0e0;
    }
    header {
      background: none;
      border-bottom: none;
      padding: 1rem 0;
    }
    input[type=file], button {
      background-color: #1e1e1e;
      color: #e0e0e0;
      border: 1px solid #333;
      border-radius: 4px;
      padding: 0.5rem;
    }
    button:hover {
      background-color: #333;
    }
    .container {
      margin: 1rem auto;
      max-width: 90%;
      background-color: #1e1e1e;
      padding: 2rem;
      border-radius: 8px;
    }
  </style>
</head>
<body>
  <header>
    <img src="{{ url_for('static',filename='img/logo.png') }}" alt="Logo" style="height:40vh;display:block;margin:0 auto;">
  </header>
  <div class="container">
    <h1>Upload Your Pokémon Save</h1>
    {% with msgs = get_flashed_messages() %}
      {% if msgs %}
        {% for m in msgs %}
          <div>{{ m }}</div>
        {% endfor %}
      {% endif %}
    {% endwith %}
    <form method="post" enctype="multipart/form-data">
      <input type="file" name="savefile" accept=".sav" required>
      <button type="submit">Upload</button>
    </form>
  </div>
</body>
</html>
'''

RESULTS_HTML = '''
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Your Caught Pokémon</title>
  <link rel="stylesheet" href="{{ url_for('static', filename='css/style.css') }}">
  <style>
    header { background: none; border-bottom: none; }
    .container { margin:1rem auto; max-width:90%; }
    .pokemon-grid { display:grid; grid-template-columns:repeat(3,1fr); gap:20rem; width:100%; max-width:2400px; margin:0 auto; }
    .pokemon-card { position:relative; background:#1e1e1e; border-radius:8px; padding:1rem; text-align:center; transition:background .3s,filter .3s,opacity .3s; }
    .pokemon-card.dead { background:#3a3a3a; filter:grayscale(100%); opacity:.6; }
    .pokemon-card img.sprite { position:absolute; top:-10px; right:-10px; width:120px; height:auto; transition:opacity .3s; }
    .pokemon-card.dead img.sprite { opacity:0; }
    .toggle-dead-btn { margin-top:.5rem; padding:.5rem 1rem; background:#d9534f; color:#fff; border:none; border-radius:4px; cursor:pointer; font-size:1.25rem; }
    .refresh-btn { position:absolute; top:10px; right:10px; width:40px; cursor:pointer; }
    .hidden-file-input { display:none; }
  </style>
</head>
<body>
  <header style="position:relative;">
    <img src="{{ url_for('static',filename='img/logo.png') }}" alt="Logo" style="height:40vh;display:block;margin:0 auto;">
    <!-- Hidden form to re-upload .sav -->
    <form id="refresh-form" method="post" enctype="multipart/form-data" action="{{ url_for('upload_file') }}" style="display:none;">
      <input type="file" id="refresh-input" name="savefile" accept=".sav" class="hidden-file-input" required>
    </form>
    <img class="refresh-btn" src="{{ url_for('static',filename='img/refresh.png') }}" alt="Refresh" onclick="document.getElementById('refresh-input').click()">
  </header>
  <div class="container">
    <h1 style="text-align:center;margin-bottom:3rem;">Your Caught Pokémon</h1>
    <div class="pokemon-grid">
      {% for p in pokemon_list %}
      <div class="pokemon-card {% if p.dead %}dead{% endif %}" id="card-{{ loop.index0 }}">
        <img class="sprite" src="{{ p.image_url }}" alt="sprite">
        <div>{{ p.MetLocation }}</div>
        <div>Nickname: {{ p.Nickname }}</div>
        <div>Level: {{ p.Level }}</div>
        <button class="toggle-dead-btn" data-id="{{ loop.index0 }}">{{ 'Revive' if p.dead else '☠' }}</button>
      </div>
      {% endfor %}
    </div>
    <p><a href="/">Upload Another File</a></p>
  </div>
  <script>
    document.getElementById('refresh-input').addEventListener('change', function() {
      document.getElementById('refresh-form').submit();
    });
    document.querySelectorAll('.toggle-dead-btn').forEach(btn => btn.addEventListener('click', () => {
      const id = btn.dataset.id;
      const card = document.getElementById(`card-${id}`);
      const isDead = !card.classList.contains('dead');
      fetch('/mark_dead', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ id, dead: isDead })
      }).then(() => {
        card.classList.toggle('dead', isDead);
        btn.textContent = isDead ? 'Revive' : '☠';
      });
    }));
  </script>
</body>
</html>
'''

@app.route('/', methods=['GET', 'POST'])
def upload_file():
    session.permanent = True
    # Redirect GET to /results if a save already exists
    if request.method == 'GET' and session.get('save_path'):
        return redirect(url_for('show_results'))
    if request.method == 'POST':
        file = request.files.get('savefile')
        if not file or not allowed_file(file.filename):
            flash('Please upload a valid .sav file')
            return redirect(request.url)
        file_id = f"{uuid.uuid4()}.sav"
        save_path = os.path.join(UPLOAD_FOLDER, secure_filename(file_id))
        file.save(save_path)
        session['save_path'] = save_path
        session['dead_map'] = {}
        try:
            run_dump(save_path)
        except:
            flash('Error processing save')
            return redirect(request.url)
        return redirect(url_for('show_results'))
    return render_template_string(INDEX_HTML)

@app.route('/results')
def show_results():
    try:
        data = json.load(open(DUMP_JSON_PATH))
    except:
        flash('Error reading JSON dump')
        return redirect(url_for('upload_file'))

    dead_map = session.get('dead_map', {})
    results = []
    for idx, entry in enumerate(data):
        name = entry.get('Name', '').lower()
        image_url = POKEAPI_CACHE.get(name, '')
        if not image_url:
            try:
                resp = requests.get(f'https://pokeapi.co/api/v2/pokemon/{name}')
                resp.raise_for_status()
                sprites = resp.json().get('sprites', {}).get('other', {}).get('showdown', {})
                image_url = sprites.get('front_default', '')
            except:
                image_url = ''
            POKEAPI_CACHE[name] = image_url
            json.dump(POKEAPI_CACHE, open(CACHE_PATH, 'w'))
        loc = LOCATION_MAP.get(str(entry.get('MetLocation', '')), f'Unknown ({entry.get("MetLocation")})')
        dead_flag = dead_map.get(str(idx), False)
        results.append({
            'MetLocation': loc,
            'Nickname': entry.get('Nickname'),
            'Level': entry.get('Level'),
            'image_url': image_url,
            'dead': dead_flag
        })
    return render_template_string(RESULTS_HTML, pokemon_list=results)

@app.route('/mark_dead', methods=['POST'])
def mark_dead():
    data = request.get_json()
    idx = str(data.get('id'))
    dead_map = session.get('dead_map', {})
    dead_map[idx] = data.get('dead', False)
    session['dead_map'] = dead_map
    return ('', 204)

if __name__ == '__main__':
    app.run(debug=True)
