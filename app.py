import os, time, zipfile, io, uuid, threading, requests, replicate
from flask import Flask, render_template_string, request, send_file, jsonify

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'processed_zips'
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Pull the token safely from Render Environment Variables
os.environ["REPLICATE_API_TOKEN"] = os.getenv("REPLICATE_API_TOKEN")

# Dictionary to track progress for each job
progress_tracker = {}

HTML_TEMPLATE = '''
<!doctype html>
<html>
<head>
    <title>Team BG Remover</title>
    <style>
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; padding: 40px; background-color: #f4f7f6; color: #333; text-align: center; }
        .container { max-width: 600px; margin: auto; background: white; padding: 30px; border-radius: 12px; box-shadow: 0 4px 15px rgba(0,0,0,0.1); }
        h1 { color: #2c3e50; }
        input[type="file"] { margin: 20px 0; }
        button { background-color: #27ae60; color: white; border: none; padding: 12px 24px; border-radius: 6px; cursor: pointer; font-size: 16px; transition: background 0.3s; }
        button:hover { background-color: #219150; }
        #progress-container { display: none; margin-top: 30px; }
        .progress-bg { width: 100%; background: #dfe6e9; border-radius: 20px; height: 25px; margin: 15px 0; overflow: hidden; }
        #bar { width: 0%; height: 100%; background: #2980b9; transition: width 0.5s ease; }
        #download-btn { display: none; margin-top: 20px; display: inline-block; padding: 12px 24px; background: #2980b9; color: white; text-decoration: none; border-radius: 6px; font-weight: bold; }
        #download-btn:hover { background: #3498db; }
    </style>
</head>
<body>
    <div class="container">
        <h1>Bulk BG Remover</h1>
        <p>Select images for your catalog and click Generate.</p>
        
        <form id="upload-form">
            <input type="file" id="file-input" multiple required>
            <br>
            <button type="submit" id="gen-btn">Generate</button>
        </form>

        <div id="progress-container">
            <p>Processing: <span id="percent">0</span>%</p>
            <div class="progress-bg"><div id="bar"></div></div>
            <p id="status-text">Removing backgrounds...</p>
            <a id="download-btn">Download ZIP</a>
        </div>
    </div>

    <script>
        const form = document.getElementById('upload-form');
        const genBtn = document.getElementById('gen-btn');

        form.onsubmit = async (e) => {
            e.preventDefault();
            genBtn.disabled = true;
            genBtn.innerText = "Uploading...";
            
            const files = document.getElementById('file-input').files;
            const formData = new FormData();
            for (let f of files) { formData.append('file', f); }

            // Start Job
            const res = await fetch('/', { method: 'POST', body: formData });
            const { job_id } = await res.json();

            document.getElementById('progress-container').style.display = 'block';
            document.getElementById('download-btn').style.display = 'none';
            
            // Poll Status
            const interval = setInterval(async () => {
                const sRes = await fetch('/status/' + job_id);
                const data = await sRes.json();
                const progress = data.progress;
                
                document.getElementById('percent').innerText = progress;
                document.getElementById('bar').style.width = progress + '%';

                if (progress === 100) {
                    clearInterval(interval);
                    document.getElementById('status-text').innerText = "Complete!";
                    const btn = document.getElementById('download-btn');
                    btn.href = '/download/' + job_id;
                    btn.style.display = 'inline-block';
                    genBtn.disabled = false;
                    genBtn.innerText = "Generate";
                }
                if (progress === -1) {
                    clearInterval(interval);
                    alert("An error occurred during processing.");
                }
            }, 5000);
        };
    </script>
</body>
</html>
'''

def background_worker(files_data, job_id):
    final_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{job_id}.zip")
    temp_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{job_id}.tmp")
    total_files = len(files_data)
    
    try:
        with zipfile.ZipFile(temp_path, 'w') as zip_file:
            for index, (filename, content) in enumerate(files_data):
                # Update progress tracker
                progress_tracker[job_id] = int((index / total_files) * 100)
                
                try:
                    output = replicate.run(
                        "851-labs/background-remover:a029dff38972b5fda4ec5d75d7d1cd25aeff621d2cf4946a41055d7db66b80bc",
                        input={"image": io.BytesIO(content), "format": "png", "background_type": "white"}
                    )
                    img_url = output if isinstance(output, str) else output[0]
                    zip_file.writestr(f"white_bg_{filename}", requests.get(img_url).content)
                    
                    if index < total_files - 1:
                        time.sleep(11) # Maintain for credit safety
                except Exception as e:
                    print(f"Error on {filename}: {e}")
        
        # Atomically rename to .zip so the download link works
        os.rename(temp_path, final_path)
        progress_tracker[job_id] = 100
    except Exception as e:
        print(f"Worker Error: {e}")
        progress_tracker[job_id] = -1

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        files = request.files.getlist("file")
        if files and files[0].filename != '':
            job_id = str(uuid.uuid4())[:8]
            files_data = [(f.filename, f.read()) for f in files]
            progress_tracker[job_id] = 0
            threading.Thread(target=background_worker, args=(files_data, job_id)).start()
            return jsonify({"job_id": job_id})
    return render_template_string(HTML_TEMPLATE)

@app.route('/status/<job_id>')
def status(job_id):
    return jsonify({"progress": progress_tracker.get(job_id, 0)})

@app.route('/download/<job_id>')
def download(job_id):
    path = os.path.join(app.config['UPLOAD_FOLDER'], f"{job_id}.zip")
    if os.path.exists(path):
        return send_file(path, as_attachment=True)
    return "File not ready", 404

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))