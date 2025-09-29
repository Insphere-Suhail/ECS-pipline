import os
import io
import zipfile
import jinja2
import boto3
import threading
import time
from flask import Flask, render_template, request, redirect, url_for, session, send_file, jsonify
from dotenv import load_dotenv
from botocore.exceptions import ClientError

# Import services
from services.aws_auth import AWSAuth
from services.vpc_service import VPCService
from services.sg_service import SecurityGroupService
from services.alb_service import ALBService
from services.ecr_service import ECRService
from services.ecs_service import ECSService
from services.iam_service import IAMService
from services.ec2_service import EC2Service

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'dev-secret-key')

# Configuration
TEMPLATE_FOLDER = 'ci-cd'
OUTPUT_FOLDER = 'generated_projects'
AWS_REGIONS = [
    'us-east-1', 'us-east-2', 'us-west-1', 'us-west-2',
    'ap-south-1', 'ap-northeast-1', 'ap-northeast-2',
    'ap-southeast-1', 'ap-southeast-2', 'eu-central-1',
    'eu-west-1', 'eu-west-2', 'sa-east-1'
]

# Store ongoing operations
infra_operations = {}

# Helper functions
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

def setup_vpc_infrastructure(vpc_service, data, infra_name):
    """Setup VPC infrastructure based on user choice"""
    if data.get('create_new_vpc'):
        vpc_id, public_subnets, private_subnets = vpc_service.create_vpc(
            infra_name, 
            data.get('vpc_name', f'{infra_name}-vpc'),
            int(data.get('public_subnets', 2)),
            int(data.get('private_subnets', 2))
        )
    else:
        vpc_id = data.get('existing_vpc')
        if not vpc_id:
            raise Exception("No VPC selected for existing VPC option")
        
        public_subnets = vpc_service.get_public_subnets(vpc_id)
        private_subnets = vpc_service.get_private_subnets(vpc_id)
    
    return vpc_id, public_subnets, private_subnets

def create_security_groups(sg_service, data, infra_name, vpc_id):
    """Create security groups based on user selection"""
    sg_config = {}
    sg_types = data.get('sg_types', [])
    
    print(f"🛡️ Selected security groups: {sg_types}")
    
    # Get existing SG IDs from the form data
    existing_sg_alb = data.get('existing_sg_alb')
    existing_sg_server = data.get('existing_sg_server') 
    existing_sg_rds = data.get('existing_sg_rds')
    existing_sg_vpn = data.get('existing_sg_vpn')
    
    # Create ALB Security Group
    if 'alb_sg' in sg_types:
        sg_config['alb_sg'] = sg_service.create_alb_sg(
            infra_name, vpc_id, existing_sg_alb
        )
        print(f"✅ ALB Security Group: {sg_config['alb_sg']}")
    else:
        print("ℹ️  ALB Security Group not selected")
    
    # Create VPN Security Group if selected (create before Server SG for SSH access)
    if 'vpn_sg' in sg_types:
        sg_config['vpn_sg'] = sg_service.create_vpn_sg(
            infra_name, vpc_id, existing_sg_vpn
        )
        print(f"✅ VPN Security Group: {sg_config['vpn_sg']}")
    else:
        print("ℹ️  VPN Security Group not selected")
    
    # Create Server Security Group
    if 'server_sg' in sg_types:
        sg_config['server_sg'] = sg_service.create_server_sg(
            infra_name, vpc_id, 
            sg_config.get('alb_sg'), 
            sg_config.get('vpn_sg'),  # Pass VPN SG for SSH access
            existing_sg_server
        )
        print(f"✅ Server Security Group: {sg_config['server_sg']}")
    else:
        print("ℹ️  Server Security Group not selected")
    
    # Create RDS Security Group if selected
    if 'rds_sg' in sg_types:
        sg_config['rds_sg'] = sg_service.create_rds_sg(
            infra_name, vpc_id,
            sg_config.get('server_sg'),  # Allow access from server SG
            sg_config.get('vpn_sg'),     # Allow access from VPN SG
            existing_sg_rds
        )
        print(f"✅ RDS Security Group: {sg_config['rds_sg']}")
    else:
        print("ℹ️  RDS Security Group not selected")
    
    return sg_config




def final_instance_check(ecs_service, cluster_name):
    """Final check for instance registration"""
    try:
        print("🔍 Performing final instance registration check...")
        response = ecs_service.ecs.list_container_instances(cluster=cluster_name)
        if response['containerInstanceArns']:
            instance_count = len(response['containerInstanceArns'])
            print(f"🎉 SUCCESS: {instance_count} instance(s) registered with ECS cluster!")
            
            # Get detailed instance info
            instances_response = ecs_service.ecs.describe_container_instances(
                cluster=cluster_name,
                containerInstances=response['containerInstanceArns']
            )
            
            for instance in instances_response['containerInstances']:
                print(f"   - Instance {instance['ec2InstanceId']}: {instance['status']}")
        else:
            print("⚠️  No instances registered yet. This is common and they should register automatically.")
            print("💡 Common reasons and solutions:")
            print("   1. ECS agent startup time: Can take 5-10 minutes")
            print("   2. Check EC2 instance system logs for ECS agent errors")
            print("   3. Verify IAM role has proper ECS permissions")
            print("   4. Ensure security groups allow outbound traffic")
            print("   5. Check if instances are in private subnets without NAT gateway")
            
    except Exception as e:
        print(f"⚠️  Could not check final instance status: {str(e)}")

def update_operation(operation_id, message):
    """Update operation status"""
    if operation_id in infra_operations:
        infra_operations[operation_id]['message'] = message
        print(f"📢 {message}")

# Routes
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

# Infrastructure Creation Routes
@app.route('/infra_credentials', methods=['GET', 'POST'])
def infra_credentials():
    if request.method == 'POST':
        access_key = request.form.get('access_key')
        secret_key = request.form.get('secret_key')
        
        # Validate credentials by testing ECR access (since that's what fails)
        auth = AWSAuth(access_key, secret_key)
        is_valid, account_info = auth.validate_credentials()
        
        if is_valid:
            session['aws_access_key'] = access_key
            session['aws_secret_key'] = secret_key
            session['aws_region'] = 'ap-south-1'
            session['account_info'] = account_info
            
            # Test ECR access specifically
            try:
                ecr_service = ECRService(access_key, secret_key, 'ap-south-1')
                # Just test if we can call ECR API
                ecr_service.ecr.describe_repositories(maxResults=1)
            except ClientError as e:
                return render_template('infra_credentials.html', 
                                     error=f"Credentials valid but ECR access denied: {str(e)}")
            
            return redirect(url_for('infra_form'))
        else:
            return render_template('infra_credentials.html', 
                                 error=account_info.get('error', 'Invalid credentials'))
    
    return render_template('infra_credentials.html')

@app.route('/infra_form')
def infra_form():
    if 'aws_access_key' not in session:
        return redirect(url_for('infra_credentials'))
    
    return render_template('infra_form.html', 
                         account_info=session.get('account_info'),
                         regions=AWS_REGIONS)

@app.route('/get_vpcs')
def get_vpcs():
    if 'aws_access_key' not in session:
        return jsonify({'error': 'Credentials not found'}), 401
    
    region = request.args.get('region', 'ap-south-1')
    vpc_service = VPCService(session['aws_access_key'], session['aws_secret_key'], region)
    vpcs = vpc_service.list_vpcs()
    return jsonify(vpcs)

@app.route('/get_security_groups')
def get_security_groups():
    if 'aws_access_key' not in session:
        return jsonify({'error': 'Credentials not found'}), 401
    
    region = request.args.get('region', 'ap-south-1')
    vpc_id = request.args.get('vpc_id')
    sg_service = SecurityGroupService(session['aws_access_key'], session['aws_secret_key'], region)
    sgs = sg_service.list_security_groups(vpc_id)
    return jsonify(sgs)

@app.route('/get_key_pairs')
def get_key_pairs():
    if 'aws_access_key' not in session:
        return jsonify({'error': 'Credentials not found'}), 401
    
    region = request.args.get('region', 'ap-south-1')
    sg_service = SecurityGroupService(session['aws_access_key'], session['aws_secret_key'], region)
    key_pairs = sg_service.list_key_pairs()
    return jsonify(key_pairs)

@app.route('/create_infra', methods=['POST'])
def create_infra():
    try:
        if 'aws_access_key' not in session:
            return jsonify({'success': False, 'error': 'Credentials not found'}), 401
        
        data = request.json
        print("📥 Received infra creation request:", data)
        
        operation_id = f"infra_{int(time.time())}"
        
        # Start infrastructure creation in background thread
        thread = threading.Thread(target=create_infra_background, 
                                args=(operation_id, data, session.copy()))
        thread.daemon = True
        thread.start()
        
        print(f"✅ Started infrastructure creation with operation ID: {operation_id}")
        
        return jsonify({
            'success': True, 
            'operation_id': operation_id, 
            'message': 'Infrastructure creation started successfully'
        })
        
    except Exception as e:
        print(f"❌ Error in create_infra: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/key-pairs')
def api_key_pairs():
    try:
        region = request.args.get('region', 'ap-south-1')
        ec2_service = EC2Service(session['aws_access_key'], session['aws_secret_key'], region)
        key_pairs = ec2_service.list_key_pairs()
        return jsonify({'key_pairs': key_pairs})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/create-key-pair', methods=['POST'])
def api_create_key_pair():
    try:
        data = request.json
        key_name = data.get('key_name')
        region = data.get('region', 'ap-south-1')
        
        ec2_service = EC2Service(session['aws_access_key'], session['aws_secret_key'], region)
        result = ec2_service.create_key_pair(key_name)
        
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/instance-types')
def api_instance_types():
    try:
        region = request.args.get('region', 'ap-south-1')
        ec2_service = EC2Service(session['aws_access_key'], session['aws_secret_key'], region)
        instance_types = ec2_service.get_arm64_instance_types()
        return jsonify({'instance_types': instance_types})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

def create_infra_background(operation_id, data, session_data):
    try:
        access_key = session_data['aws_access_key']
        secret_key = session_data['aws_secret_key']
        region = data.get('region', 'ap-south-1')
        
        infra_operations[operation_id] = {
            'status': 'in_progress',
            'message': 'Starting infrastructure creation...',
            'details': []
        }
        
        # Initialize services
        iam_service = IAMService(access_key, secret_key, region)
        vpc_service = VPCService(access_key, secret_key, region)
        sg_service = SecurityGroupService(access_key, secret_key, region)
        alb_service = ALBService(access_key, secret_key, region)
        ecr_service = ECRService(access_key, secret_key, region)
        ecs_service = ECSService(access_key, secret_key, region)
        
        infra_name = data['infra_name']
        
        # Step 1: Create IAM roles
        update_operation(operation_id, 'Creating IAM roles...')
        task_role_arn = iam_service.create_task_role(infra_name)
        execution_role_arn = iam_service.create_execution_role(infra_name)
        instance_role_name = iam_service.create_instance_role(infra_name)
        
        # Wait for IAM propagation
        print("⏳ Waiting for IAM roles to propagate...")
        time.sleep(45)
        
        # Step 2: Create ECR Repository and push image
        update_operation(operation_id, 'Creating ECR Repository and building Docker image...')
        ecr_repo_uri = ecr_service.create_repository(infra_name)
        ecr_service.build_and_push_image(infra_name, ecr_repo_uri)
        
        # Step 3: Handle VPC
        update_operation(operation_id, 'Setting up VPC and subnets...')
        vpc_id, public_subnets, private_subnets = setup_vpc_infrastructure(
            vpc_service, data, infra_name
        )
        
        print(f"✅ VPC: {vpc_id}")
        print(f"✅ Public subnets: {public_subnets}")
        print(f"✅ Private subnets: {private_subnets}")
        
        # Validate we have subnets
        if not public_subnets:
            raise Exception("No public subnets available for ALB")
        if not private_subnets:
            raise Exception("No private subnets available for EC2 instances")
        
        # Step 4: Create Security Groups
        update_operation(operation_id, 'Creating Security Groups...')
        sg_config = create_security_groups(
            sg_service, data, infra_name, vpc_id
        )
        print(f"✅ Security Groups created: {sg_config}")
        
        # Step 5: Create ALB
        update_operation(operation_id, 'Creating Application Load Balancer...')
        alb_arn, target_group_arn = alb_service.create_alb(
            infra_name, vpc_id, public_subnets, sg_config.get('alb_sg')
        )
        alb_dns = alb_service.get_alb_dns(infra_name)
        print(f"✅ ALB created: {alb_arn}")
        print(f"✅ ALB DNS: {alb_dns}")
        
        # Step 6: Create ECS Task Definition
        update_operation(operation_id, 'Creating ECS Task Definition...')
        task_def_arn = ecs_service.create_task_definition(
            infra_name, ecr_repo_uri, task_role_arn, execution_role_arn
        )
        print(f"✅ Task Definition created: {task_def_arn}")
        
        # Step 7: Create ECS Cluster with EXACT console configuration
        update_operation(operation_id, 'Creating ECS Cluster (console configuration)...')
        
        # Get instance type from form data with default fallback
        instance_type = data.get('instance_type', 't4g.micro')
        print(f"🔄 Using instance type: {instance_type}")
        
        # Handle key pair selection
        key_pair_name = None
        if data.get('key_pair_option') == 'existing':
            key_pair_name = data.get('existing_key_pair')
        elif data.get('key_pair_option') == 'new':
            key_pair_name = data.get('new_key_name')
        
        print(f"🔄 Using key pair: {key_pair_name}")
        
        cluster_arn = ecs_service.create_cluster(
            infra_name, vpc_id, private_subnets, sg_config.get('server_sg'), 
            instance_role_name, key_pair_name, instance_type
        )
        print(f"✅ ECS Cluster created: {cluster_arn}")
        
        # Step 8: Create ECS Service
        update_operation(operation_id, 'Creating ECS Service...')
        service_arn = ecs_service.create_service(
            infra_name, cluster_arn, task_def_arn, 
            private_subnets, sg_config.get('server_sg'),
            alb_arn, target_group_arn
        )
        print(f"✅ ECS Service created: {service_arn}")
        
        # Final check
        final_instance_check(ecs_service, infra_name)
        
        infra_operations[operation_id] = {
            'status': 'completed',
            'message': 'Infrastructure created successfully with console configuration!',
            'details': [
                {'service': 'VPC', 'id': vpc_id},
                {'service': 'ECR Repository', 'uri': ecr_repo_uri},
                {'service': 'ECS Cluster', 'name': infra_name},
                {'service': 'Capacity Provider', 'name': f'{infra_name}-cp'},
                {'service': 'Auto Scaling Group', 'name': f'{infra_name}-asg'},
                {'service': 'ECS Service', 'name': f'{infra_name}-service'},
                {'service': 'ALB DNS', 'url': f'http://{alb_dns}'},
                {'service': 'Instance Type', 'info': f'{instance_type}'},
                {'service': 'Configuration', 'info': 'Uses exact same setup as AWS Console'}
            ]
        }
        
    except Exception as e:
        error_msg = f'Error: {str(e)}'
        print(f"❌ Infrastructure creation failed: {error_msg}")
        import traceback
        traceback.print_exc()
        
        infra_operations[operation_id] = {
            'status': 'failed',
            'message': error_msg,
            'details': []
        }

@app.route('/infra_status/<operation_id>')
def infra_status(operation_id):
    """Show infrastructure creation status page"""
    return render_template('infra_status.html', operation_id=operation_id)

@app.route('/get_operation_status/<operation_id>')
def get_operation_status(operation_id):
    """Get the current status of an infrastructure creation operation"""
    operation = infra_operations.get(operation_id, {
        'status': 'unknown',
        'message': 'Operation not found',
        'details': []
    })
    return jsonify(operation)

@app.route('/infra_success/<operation_id>')
def infra_success(operation_id):
    operation = infra_operations.get(operation_id)
    if not operation or operation['status'] != 'completed':
        return redirect(url_for('index'))
    return render_template('infra_success.html', operation=operation)

# Keep your old infra_form route but redirect to new flow
@app.route('/infra', methods=['GET'])
def old_infra_form():
    return redirect(url_for('infra_credentials'))

if __name__ == '__main__':
    os.makedirs(OUTPUT_FOLDER, exist_ok=True)
    app.run(debug=True)