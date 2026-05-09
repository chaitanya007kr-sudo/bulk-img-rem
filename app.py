import os, time, zipfile, io, uuid, threading, requests, replicate
from flask import Flask, render_template_string, request, send_file, url_for

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'processed_zips'
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.environ["REPLICATE_API_TOKEN"] = os.getenv("REPLICATE_API_TOKEN")
# Simple HTML Interface
HTML_TEMPLATE = '''
<!doctype html>
<html>
<head><title>Team BG Remover</title></head>
<body>
    <h1>Team Bulk Background Remover</h1>
    <p>Select images and click upload. Wait for the success message.</p>
    <form method="post" enctype="multipart/form-data">
      <input type="file" name="file" multiple>
      <input type="submit" value="Start Processing">
    </form>
    <hr>
    {% if job_id %}
      <p style="color: blue;">Processing Job: {{ job_id }}. Your download will start shortly...</p>
      <script>
        // Check every 5 seconds if the file is ready
        setInterval(function() {
            window.location.href = "/download/{{ job_id }}";
        }, 5000);
      </script>
    {% endif %}
</body>
</html>
'''

def background_worker(files_data, job_id):
    zip_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{job_id}.zip")
    with zipfile.ZipFile(zip_path, 'w') as zip_file:
        for index, (filename, content) in enumerate(files_data):
            try:
                output = replicate.run(
                    "851-labs/background-remover:a029dff38972b5fda4ec5d75d7d1cd25aeff621d2cf4946a41055d7db66b80bc",
                    input={"image": io.BytesIO(content), "format": "png", "background_type": "white"}
                )
                img_url = output if isinstance(output, str) else output[0]
                zip_file.writestr(f"white_bg_{filename}", requests.get(img_url).content)
                
                # Stay safe under the $5 rate limit
                if index < len(files_data) - 1:
                    time.sleep(11)
            except Exception as e:
                print(f"Error: {e}")

@app.route('/', methods=['GET', 'POST'])
def index():
    job_id = None
    if request.method == 'POST':
        files = request.files.getlist("file")
        if files and files[0].filename != '':
            job_id = str(uuid.uuid4())[:8]
            # Read files into memory to pass to thread
            files_data = [(f.filename, f.read()) for f in files]
            threading.Thread(target=background_worker, args=(files_data, job_id)).start()
    return render_template_string(HTML_TEMPLATE, job_id=job_id)

@app.route('/download/<job_id>')
def download(job_id):
    path = os.path.join(app.config['UPLOAD_FOLDER'], f"{job_id}.zip")
    if os.path.exists(path):
        return send_file(path, as_attachment=True)
    return "Processing...", 202

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))