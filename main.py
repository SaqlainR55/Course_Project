# main.py

import os
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, send_from_directory
from werkzeug.utils import secure_filename
import fitz  # PyMuPDF

from google.cloud import speech
from google.cloud import texttospeech
import google.generativeai as genai

# Flask setup
app = Flask(__name__)

# Directories
UPLOAD_FOLDER = 'uploads'
BOOK_FOLDER  = 'book_data'
BOOK_TEXT_FILE = os.path.join(BOOK_FOLDER, 'uploaded_book.txt')

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(BOOK_FOLDER, exist_ok=True)

# Allowed file extensions
ALLOWED_EXTENSIONS = {'wav', 'txt'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

def allowed_file(filename):
    # still allow any .wav/.txt upload, and we don't need 
    # to special-case response.wav here
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_files():
    # return *all* .wav (and if you want txt too, just add .endswith('.txt'))
    files = [fn for fn in os.listdir(UPLOAD_FOLDER) if fn.endswith('.wav')]
    files.sort(reverse=True)
    return files

@app.route('/')
def index():
    files = get_files()
    text_contents = {}
    for fn in files:
        txt_path = os.path.join(UPLOAD_FOLDER, fn + '.txt')
        if os.path.exists(txt_path):
            with open(txt_path, 'r') as f:
                text_contents[fn + '.txt'] = f.read()

    # current book title
    book_title = None
    title_path = os.path.join(BOOK_FOLDER, 'book_title.txt')
    if os.path.exists(title_path):
        with open(title_path) as f:
            book_title = f.read()

    return render_template('index.html',
                           files=files,
                           text_contents=text_contents,
                           book_title=book_title)

@app.route('/upload', methods=['POST'])
def upload_audio():
    # form has hidden audio_data file field
    if 'audio_data' not in request.files:
        return redirect(request.url)
    f = request.files['audio_data']
    if f.filename == '':
        return redirect(request.url)

    if f and allowed_file(f.filename):
        # unique timestamp name
        name = datetime.now().strftime("%Y%m%d-%I%M%S%p") + '.wav'
        save_path = os.path.join(UPLOAD_FOLDER, secure_filename(name))
        f.save(save_path)

        # 1) transcribe
        transcript = transcribe_audio(save_path)

        # 2) load book text
        if os.path.exists(BOOK_TEXT_FILE):
            with open(BOOK_TEXT_FILE, 'r', encoding='utf-8') as bf:
                book = bf.read()
        else:
            book = "No book uploaded."

        # 3) craft prompt + call LLM
        prompt = f"""
You are a helpful assistant. Use the following book text to answer the question below.

Book:
\"\"\"{book[:20000]}\"\"\"

Question:
{transcript}

Answer clearly, referencing the book.
"""
        answer = generate(transcript, prompt)

        # 4) save answer text
        txt_out = save_path + '.txt'
        with open(txt_out, 'w') as tf:
            tf.write(answer)

        # 5) synthesize audio response
        wav_out = save_path.replace('.wav', '_response.wav')
        synthesize_speech(answer, wav_out)

    return redirect(url_for('index'))

def transcribe_audio(path):
    client = speech.SpeechClient()
    with open(path, 'rb') as af:
        audio_bytes = af.read()

    audio = speech.RecognitionAudio(content=audio_bytes)
    cfg   = speech.RecognitionConfig(
        language_code="en-US",
        audio_channel_count=1,
        enable_word_time_offsets=False,
        model="latest_long"
    )

    op = client.long_running_recognize(config=cfg, audio=audio)
    res = op.result(timeout=90)

    text = ""
    for r in res.results:
        text += r.alternatives[0].transcript + "\n"
    return text.strip()

def generate(transcript, prompt):
    genai.configure(api_key=os.environ["GEMINI_API_KEY"])
    model = genai.GenerativeModel("models/gemini-1.5-flash")
    full = f"{prompt}\n\nTranscript:\n{transcript}"
    resp = model.generate_content(full)
    return resp.text

def synthesize_speech(text, out_path):
    client = texttospeech.TextToSpeechClient()
    synthesis_input = texttospeech.SynthesisInput(text=text)
    voice = texttospeech.VoiceSelectionParams(
        language_code="en-US",
        ssml_gender=texttospeech.SsmlVoiceGender.NEUTRAL
    )
    audio_cfg = texttospeech.AudioConfig(
        audio_encoding=texttospeech.AudioEncoding.LINEAR16
    )
    resp = client.synthesize_speech(
        input=synthesis_input, voice=voice, audio_config=audio_cfg
    )
    with open(out_path, 'wb') as o:
        o.write(resp.audio_content)

@app.route('/upload_pdf', methods=['POST'])
def upload_pdf():
    if 'pdf_file' not in request.files:
        return redirect(request.url)
    pdf = request.files['pdf_file']
    if pdf.filename == '':
        return redirect(request.url)

    if pdf.filename.lower().endswith('.pdf'):
        save_path = os.path.join(BOOK_FOLDER, secure_filename(pdf.filename))
        pdf.save(save_path)

        # extract all text
        text = ""
        doc = fitz.open(save_path)
        for page in doc:
            text += page.get_text()

        with open(BOOK_TEXT_FILE, 'w', encoding='utf-8') as bf:
            bf.write(text)
        with open(os.path.join(BOOK_FOLDER, 'book_title.txt'), 'w') as tf:
            tf.write(pdf.filename)

    return redirect(url_for('index'))

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)

if __name__ == '__main__':
    # debug=False in prod
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)), debug=False)
