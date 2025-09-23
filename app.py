import os
import io
import zipfile
import jinja2
from flask import Flask, render_template, request, redirect, url_for, session, send_file
from dotenv import load_dotenv
import shutil

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'dev-secret-key')

# Configuration
TEMPLATE_FOLDER = 'ci-cd'
OUTPUT_FOLDER = 'generated_projects'

def render_templates(variables):
    """Render all .j2 templates with provided variables and copy non-.j2 files"""
    rendered_files = {}
    env = jinja2.Environment(loader=jinja2.FileSystemLoader(TEMPLATE_FOLDER))
    
    for root, dirs, files in os.walk(TEMPLATE_FOLDER):
        for file in files:
            file_path = os.path.join(root, file)
            
            if file.endswith('.j2'):
                # Process .j2 templates
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                except UnicodeDecodeError:
                    try:
                        with open(file_path, 'r', encoding='latin-1') as f:
                            content = f.read()
                    except Exception as e:
                        print(f"Failed to read {file_path}: {str(e)}")
                        continue
                
                try:
                    template = env.from_string(content)
                    rendered = template.render(**variables)
                    output_path = os.path.join(root, file[:-3])  # Remove .j2 extension
                    rendered_files[output_path] = rendered
                except Exception as e:
                    print(f"Failed to render {file_path}: {str(e)}")
                    continue
            else:
                # Copy non-.j2 files directly (like www.conf)
                try:
                    with open(file_path, 'rb') as f:
                        content = f.read()
                    rendered_files[file_path] = content
                except Exception as e:
                    print(f"Failed to read {file_path}: {str(e)}")
                    continue
    
    return rendered_files

def create_project_zip(rendered_files, project_name):
    """Create zip file of rendered project files"""
    zip_buffer = io.BytesIO()
    
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        for file_path, content in rendered_files.items():
            # Preserve directory structure in zip
            zip_path = os.path.join(project_name, file_path[len(TEMPLATE_FOLDER)+1:])
            
            # Write content to zip (handle both text and binary content)
            if isinstance(content, str):
                zip_file.writestr(zip_path, content)
            else:
                zip_file.writestr(zip_path, content)
        
        # Add checklist file
        checklist = generate_checklist(session)
        zip_file.writestr(f"{project_name}/CHECKLIST.md", checklist)
    
    zip_buffer.seek(0)
    return zip_buffer

def generate_checklist(session_data):
    """Generate checklist markdown file"""
    return f"""########################## ✅ Deployment Checklist  ##########################
  ## Bitbucket Repository Variables ##
- AWS_ACCESS_KEY_ID = [your_access_key]
- AWS_SECRET_ACCESS_KEY = [your_secret_key]
- AWS_DEFAULT_REGION = {session_data.get('aws_region', 'ap-south-1')}
- AWS_ACCOUNT_ID = {session_data.get('aws_account_id', '')}
- ECR_REPOSITORY = {session_data.get('ecr_repo', '') or f"{session_data.get('project_name', '')}-repo"}
- ECS_CLUSTER = {session_data.get('ecs_cluster', '') or f"{session_data.get('project_name', '')}-cluster"}
- ECS_SERVICE = {session_data.get('ecs_service', '') or f"{session_data.get('project_name', '')}-service"}
 ## Deployment Steps ##
1. Set all variables in Bitbucket repository settings
2. Configure pipeline permissions
3. Verify S3 bucket access
4. Configure ECR repository permissions
5. Set up ECS cluster and service"""

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/code', methods=['GET', 'POST'])
def code_form():
    if request.method == 'POST':
        # Store form data in session
        session.update({
            'project_name': request.form['project_name'],
            's3_bucket': request.form['s3_bucket'],
            's3_bucket_sync': request.form['s3_bucket_sync'],
            'branch': request.form['branch'],
            'frontend_domain': request.form['frontend_domain'],
            'api_domain': request.form['api_domain'],
            'aws_region': request.form.get('aws_region', 'ap-south-1'),
            'aws_account_id': request.form.get('aws_account_id', ''),
            'ecr_repo': request.form.get('ecr_repo', ''),
            'ecs_cluster': request.form.get('ecs_cluster', ''),
            'ecs_service': request.form.get('ecs_service', '')
        })
        
        # Render templates and create zip
        rendered_files = render_templates(session)
        zip_buffer = create_project_zip(rendered_files, session['project_name'])
        
        # Save zip to output folder
        os.makedirs(OUTPUT_FOLDER, exist_ok=True)
        zip_path = os.path.join(OUTPUT_FOLDER, f"{session['project_name']}.zip")
        with open(zip_path, 'wb') as f:
            f.write(zip_buffer.getvalue())
        
        session['zip_path'] = zip_path
        return redirect(url_for('success'))
    
    return render_template('code_form.html')

@app.route('/infra', methods=['GET', 'POST'])
def infra_form():
    if request.method == 'POST':
        session.update({
            'aws_access_key': request.form['aws_access_key'],
            'aws_secret_key': request.form['aws_secret_key'],
            'aws_region': request.form['aws_region'],
            'account_name': request.form['account_name'],
            'project_name': request.form['project_name'],
            'vpc_id': request.form.get('vpc_id', ''),
            'create_new_vpc': request.form.get('create_new_vpc', 'false') == 'true'
        })
        return redirect(url_for('success'))
    
    return render_template('infra_form.html')

@app.route('/success')
def success():
    checklist = generate_checklist(session).split('\n')
    return render_template('success.html', checklist=checklist)

@app.route('/download')
def download():
    if 'zip_path' in session and os.path.exists(session['zip_path']):
        return send_file(
            session['zip_path'],
            as_attachment=True,
            download_name=f"{session['project_name']}.zip"
        )
    return redirect(url_for('index'))

if __name__ == '__main__':
    os.makedirs(OUTPUT_FOLDER, exist_ok=True)
    app.run(debug=True)