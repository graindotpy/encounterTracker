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
<html lang="en" class="dark">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Upload Save</title>
  <link rel="stylesheet" href="{{ url_for('static', filename='css/style.css') }}">
  <style>
    body { background-color: #121212; color: #e0e0e0; }
    header { padding: 1rem 0; }
    input[type=file], button { background:#1e1e1e; color:#e0e0e0; border:1px solid #333; border-radius:4px; padding:.5rem; }
    button:hover { background:#333; }
    .container { margin:1rem auto; max-width:90%; background:#1e1e1e; padding:2rem; border-radius:8px; }
  </style>
</head>
<body>
  <header>
    <img src="{{ url_for('static',filename='img/logo.png') }}" alt="Logo" style="height:40vh;display:block;margin:0 auto;">
  </header>
  <div class="container">
    <h1>Upload Your Pokémon Save</h1>
    {% with msgs = get_flashed_messages() %}
      {% if msgs %}{% for m in msgs %}<div>{{ m }}</div>{% endfor %}{% endif %}
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
    header { position:relative; padding:1rem 0; }
    .container { margin:1rem auto; max-width:90%; }
    .pokemon-grid {
      display: grid;
      grid-template-columns: repeat(3, minmax(300px, 1fr));
      gap: 2rem;
      width: 100%;
      max-width: 2400px;
      margin: 0 auto;
    }
    .pokemon-card {
      max-width: 280px;
      margin: 0 auto;
      background: #1e1e1e;
      border-radius: 8px;
      padding: 1rem;
      text-align: center;
      transition: background-color 0.5s ease, filter 0.5s ease, opacity 0.5s ease;
    }
    .pokemon-card.dead {
      background: #3a3a3a;
      filter: grayscale(100%);
      opacity: 0.3;
    }
    .pokemon-card img.sprite {
      position: absolute;
      top: -10px;
      right: -10px;
      width: 120px;
      transition: opacity 0.5s ease;
    }
    .pokemon-card.dead img.sprite { opacity:0; }
    .toggle-dead-btn { margin-top:.5rem; background:#d9534f; color:#fff; padding:.5rem 1rem; border:none; border-radius:4px; cursor:pointer; }
    .refresh-btn { position:absolute; top:10px; right:10px; width:40px; cursor:pointer; }
    .hidden-file-input { display:none; }
  </style>
</head>
<body>
  <header>
    <img src="{{ url_for('static',filename='img/logo.png') }}" alt="Logo" style="height:40vh;display:block;margin:0 auto;">
    <form id="refresh-form" method="post" enctype="multipart/form-data" action="{{ url_for('upload_file') }}" style="display:none;">
      <input type="hidden" name="refresh" value="1">
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
    <p><a href="{{ url_for('reset') }}">Upload Another File</a></p>
  </div>
  <script>
    document.getElementById('refresh-input').addEventListener('change', function(){document.getElementById('refresh-form').submit();});
    document.querySelectorAll('.toggle-dead-btn').forEach(btn=>btn.addEventListener('click',()=>{
      const id=btn.dataset.id,card=document.getElementById(`card-${id}`),isDead=!card.classList.contains('dead');
      fetch('/mark_dead',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id,dead:isDead})})
      .then(()=>{card.classList.toggle('dead',isDead);btn.textContent=isDead?'Revive':'☠';});
    }));
  </script>
</body>
</html>
'''

@app.route('/', methods=['GET', 'POST'])
def upload_file():
    session.permanent=True
    if request.method=='GET' and session.get('dump_file'):
        return redirect(url_for('show_results'))
    if request.method=='POST':
        file=request.files.get('savefile')
        if not file or not allowed_file(file.filename): flash('Invalid .sav');return redirect(request.url)
        fid=str(uuid.uuid4());save_path=os.path.join(UPLOAD_FOLDER,f"{fid}.sav");file.save(save_path)
        dump_path=os.path.join(UPLOAD_FOLDER,f"{fid}.json");is_refresh=request.form.get('refresh')
        if not is_refresh: session['dead_map']={}
        session['dump_file']=dump_path
        run_dump(save_path,dump_path)
        return redirect(url_for('show_results'))
    return render_template_string(INDEX_HTML)

@app.route('/reset')
def reset(): session.pop('dump_file',None);session.pop('dead_map',None);return redirect(url_for('upload_file'))

@app.route('/results')
def show_results():
    df=session.get('dump_file');
    if not df or not os.path.isfile(df): return redirect(url_for('upload_file'))
    data=json.load(open(df));dm=session.get('dead_map',{});res=[]
    for idx,e in enumerate(data):
        nm=e.get('Name','').lower();img=POKEAPI_CACHE.get(nm) or ''
        if not img:
            try:r=requests.get(f'https://pokeapi.co/api/v2/pokemon/{nm}');r.raise_for_status();img=r.json().get('sprites',{}).get('other',{}).get('showdown',{}).get('front_default','')
            except:img=''
            POKEAPI_CACHE[nm]=img;json.dump(POKEAPI_CACHE,open(CACHE_PATH,'w'))
        loc=LOCATION_MAP.get(str(e.get('MetLocation','')),'Unknown');dead=dm.get(str(idx),False)
        res.append({'MetLocation':loc,'Nickname':e.get('Nickname'),'Level':e.get('Level'),'image_url':img,'dead':dead})
    return render_template_string(RESULTS_HTML,pokemon_list=res)

@app.route('/mark_dead', methods=['POST'])
def mark_dead():
    d=request.get_json();i=str(d.get('id'));dm=session.get('dead_map',{});dm[i]=d.get('dead',False);session['dead_map']=dm;return('','204')

if __name__=='__main__':app.run(debug=True)
