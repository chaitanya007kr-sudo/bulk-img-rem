import os, time, zipfile, io, uuid, threading, requests, replicate
from flask import Flask, render_template_string, request, send_file

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'processed_zips'
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Correct way to pull the token from Render's Environment Variables
os.environ["REPLICATE_API_TOKEN"] = os.getenv("REPLICATE_API_TOKEN")

def background_worker(files_data, job_id):
    zip_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{job_id}.zip")
    
    # We open the ZIP once and keep it open until every image is processed
    try:
        with zipfile.ZipFile(zip_path, 'w') as zip_file:
            for index, (filename, content) in enumerate(files_data):
                try:
                    print(f"Starting {filename} for job {job_id}")
                    output = replicate.run(
                        "851-labs/background-remover:a029dff38972b5fda4ec5d75d7d1cd25aeff621d2cf4946a41055d7db66b80bc",
                        input={"image": io.BytesIO(content), "format": "png", "background_type": "white"}
                    )
                    
                    img_url = output if isinstance(output, str) else output[0]
                    img_response = requests.get(img_url)
                    
                    if img_response.status_code == 200:
                        zip_file.writestr(f"white_bg_{filename}", img_response.content)
                        print(f"Successfully added {filename} to ZIP")
                    
                    # Essential for $5 credit accounts
                    if index < len(files_data) - 1:
                        time.sleep(11)
                        
                except Exception as e:
                    print(f"Error processing {filename}: {e}")
        
        # Once the 'with' block ends, the ZIP is safely closed and saved
        print(f"Job {job_id} complete.")

    except Exception as e:
        print(f"Critical Worker Error: {e}")

@app.route('/', methods=['GET', 'POST'])
def index():
    job_id = None
    if request.method == 'POST':
        # Check if files were actually uploaded
        if 'file' not in request.files:
            return "No file part", 400
            
        files = request.files.getlist("file")
        if files and files[0].filename != '':
            job_id = str(uuid.uuid4())[:8]
            # Convert files to bytes immediately so the thread has them
            files_data = [(f.filename, f.read()) for f in files]
            
            # Start the worker
            thread = threading.Thread(target=background_worker, args=(files_data, job_id))
            thread.start()
            
    return render_template_string(HTML_TEMPLATE, job_id=job_id)

# (Keep your download and HTML_TEMPLATE the same as before)