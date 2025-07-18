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
# Linux dumper
DUMPER_PATH = os.path.join(BASE_DIR, 'jsonDumper', 'net9.0', 'linux-x64', 'PkhexDump')
CACHE_PATH = os.path.join(BASE_DIR, 'pokeapi_cache.json')
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
app.config['SESSION_PERMANENT'] = True
app.permanent_session_lifetime = timedelta(days=3650)

# Helpers
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() == 'sav'

def run_dump(save_path, dump_path):
    """Run dumper on save_path, write JSON to dump_path."""
    subprocess.run([DUMPER_PATH, save_path], check=True)
    if os.path.exists(dump_path):
        os.remove(dump_path)
    os.replace(os.path.join(BASE_DIR, 'all_pokemon.json'), dump_path)

# Templates
INDEX_HTML = '''
<!doctype html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Upload Your Pokémon Save</title>
  <link rel="stylesheet" href="{{ url_for('static', filename='style.css') }}">
</head>
<body>
  <div class="container">
    <h1>Upload Your .sav File</h1>
    {% with msgs = get_flashed_messages() %}
      {% if msgs %}
        {% for m in msgs %}
          <div class="flash">{{ m }}</div>
        {% endfor %}
      {% endif %}
    {% endwith %}
    <form method="post" enctype="multipart/form-data">
      <input type="file" name="savefile">
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
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Your Encounter Tracker</title>
  <link rel="stylesheet" href="{{ url_for('static', filename='style.css') }}">
</head>
<body>
  <div class="container">
    <header>
      <h1>Your Encounter Tracker</h1>
    </header>
    {% for p in pokemon_list %}
      <div class="entry">
        <strong>{{ p.MetLocation }}</strong><br>
        {% if p.has_pokemon %}
          {% if p.image_url %}
            <img src="{{ p.image_url }}" alt="{{ p.Nickname }}"><br>
          {% endif %}
          Nickname: {{ p.Nickname }}<br>
          Level: {{ p.Level }}<br>
          {% if p.dead %}
            <button onclick="toggleDead('{{ p.key }}', false)">Revive</button>
          {% else %}
            <button onclick="toggleDead('{{ p.key }}', true)">&#9760;</button>
          {% endif %}
        {% else %}
          <em>(no encounters here)</em>
        {% endif %}
      </div>
    {% endfor %}
    <p><a href="{{ url_for('upload_file') }}">Upload Another File</a></p>
  </div>
  <script>
    function toggleDead(key, is_dead) {
      fetch('{{ url_for("mark_dead") }}', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({key: key, dead: is_dead})
      }).then(()=>location.reload());
    }
  </script>
</body>
</html>
'''

@app.route('/', methods=['GET', 'POST'])
def upload_file():
    session.permanent = True
    if request.method == 'GET' and session.get('dump_file'):
        return redirect(url_for('show_results'))

    if request.method == 'POST':
        file = request.files.get('savefile')
        if not file or not allowed_file(file.filename):
            flash('Invalid .sav file')
            return redirect(request.url)

        fid = str(uuid.uuid4())
        save_path = os.path.join(UPLOAD_FOLDER, f"{fid}.sav")
        file.save(save_path)

        dump_path = os.path.join(UPLOAD_FOLDER, f"{fid}.json")
        session['dead_map'] = {}
        session['dump_file'] = dump_path

        run_dump(save_path, dump_path)
        return redirect(url_for('show_results'))

    return render_template_string(INDEX_HTML)

@app.route('/reset')
def reset():
    session.pop('dump_file', None)
    session.pop('dead_map', None)
    return redirect(url_for('upload_file'))

@app.route('/results')
def show_results():
    dump_file = session.get('dump_file')
    if not dump_file or not os.path.isfile(dump_file):
        return redirect(url_for('upload_file'))

    data = json.load(open(dump_file))
    dead_map = session.get('dead_map', {})

    raw_results = []
    for e in data:
        key = f"{e.get('Name','').lower()}_{e.get('Nickname','')}_{e.get('MetLocation','')}"
        name_key = e.get('Name','').lower()
        img = POKEAPI_CACHE.get(name_key) or ''
        if not img:
            try:
                r = requests.get(f'https://pokeapi.co/api/v2/pokemon/{name_key}')
                r.raise_for_status()
                img = r.json().get('sprites', {}).get('other', {}).get('showdown', {}).get('front_default','')
            except:
                img = ''
            POKEAPI_CACHE[name_key] = img
            json.dump(POKEAPI_CACHE, open(CACHE_PATH, 'w'))

        loc_name = LOCATION_MAP.get(str(e.get('MetLocation','')), 'Unknown')
        dead_flag = dead_map.get(key, False)
        raw_results.append({
            'key': key,
            'MetLocation': loc_name,
            'Nickname': e.get('Nickname'),
            'Level': e.get('Level'),
            'image_url': img,
            'dead': dead_flag,
            'has_pokemon': True
        })

    display_list = []
    for code in sorted(LOCATION_MAP.keys(), key=lambda x: int(x)):
        loc_name = LOCATION_MAP[code]
        pokes = [r for r in raw_results if r['MetLocation'] == loc_name]
        if pokes:
            display_list.extend(pokes)
        else:
            display_list.append({
                'key': f"empty_{code}",
                'MetLocation': loc_name,
                'Nickname': '',
                'Level': '',
                'image_url': '',
                'dead': False,
                'has_pokemon': False
            })

    return render_template_string(RESULTS_HTML, pokemon_list=display_list)

@app.route('/mark_dead', methods=['POST'])
def mark_dead():
    data = request.get_json()
    key = data.get('key')
    is_dead = data.get('dead', False)
    dm = session.get('dead_map', {})
    dm[key] = is_dead
    session['dead_map'] = dm
    return ('', 204)

if __name__ == '__main__':
    app.run(debug=True)
