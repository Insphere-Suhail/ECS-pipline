import boto3
import subprocess
import os
import tempfile
import shutil
import base64
from botocore.exceptions import ClientError

PUBLIC_REPO = "https://github.com/Insphere-Suhail/ECS-ARM-Image.git"

class ECRService:
    def __init__(self, access_key, secret_key, region):
        self.access_key = access_key
        self.secret_key = secret_key
        self.region = region
        self.ecr = boto3.client(
            'ecr',
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=region
        )
    
    def create_repository(self, infra_name):
        try:
            repo_name = f"{infra_name}-repo"
            
            # Check if repository already exists
            try:
                response = self.ecr.describe_repositories(repositoryNames=[repo_name])
                repo_uri = response['repositories'][0]['repositoryUri']
                print(f"✅ ECR Repository already exists: {repo_uri}")
                return repo_uri
            except ClientError as e:
                if e.response['Error']['Code'] != 'RepositoryNotFoundException':
                    raise e
            
            # Create repository
            print(f"🚀 Creating ECR repository: {repo_name}")
            response = self.ecr.create_repository(
                repositoryName=repo_name,
                tags=[
                    {'Key': 'Name', 'Value': repo_name},
                    {'Key': 'Infra', 'Value': infra_name}
                ]
            )
            repo_uri = response['repository']['repositoryUri']
            print(f"✅ ECR Repository created: {repo_uri}")
            return repo_uri
            
        except ClientError as e:
            if e.response['Error']['Code'] == 'RepositoryAlreadyExistsException':
                response = self.ecr.describe_repositories(repositoryNames=[repo_name])
                return response['repositories'][0]['repositoryUri']
            else:
                raise Exception(f"❌ ECR repository creation failed: {str(e)}")
    
    def build_and_push_image(self, infra_name, ecr_repo_uri):
        try:
            print(f"🚀 Starting Docker image build and push for {ecr_repo_uri}")
            
            # Get ECR authorization token using boto3 (same as your reference code)
            print("🔑 Getting ECR authorization token...")
            auth_response = self.ecr.get_authorization_token()
            token = auth_response['authorizationData'][0]['authorizationToken']
            proxy_endpoint = auth_response['authorizationData'][0]['proxyEndpoint']
            
            # Decode the token to get username and password
            user_pass = base64.b64decode(token).decode('utf-8')
            password = user_pass.split(':')[1]
            
            print(f"🔐 Proxy endpoint: {proxy_endpoint}")
            
            # Docker login using the token
            print("🔐 Logging into ECR...")
            login_cmd = ["docker", "login", "-u", "AWS", "-p", password, proxy_endpoint]
            login_result = subprocess.run(login_cmd, capture_output=True, text=True)
            
            if login_result.returncode != 0:
                print(f"❌ Docker login failed: {login_result.stderr}")
                raise Exception(f"❌ Docker login failed: {login_result.stderr}")
            
            print("✅ Logged in to ECR successfully")
            
            # Create temporary directory for cloning
            temp_dir = tempfile.mkdtemp()
            print(f"📁 Created temp directory: {temp_dir}")
            
            try:
                # Clone the repository
                print(f"📥 Cloning repository from {PUBLIC_REPO}")
                clone_result = subprocess.run(
                    ['git', 'clone', '--depth', '1', PUBLIC_REPO, temp_dir],
                    capture_output=True, text=True
                )
                
                if clone_result.returncode != 0:
                    print(f"❌ Git clone failed: {clone_result.stderr}")
                    raise Exception(f"❌ Git clone failed: {clone_result.stderr}")
                
                print("✅ Repository cloned successfully")
                
                # Check repository contents
                print("📋 Repository contents:")
                ls_result = subprocess.run(['ls', '-la', temp_dir], capture_output=True, text=True)
                print(ls_result.stdout)
                
                # Build Docker image for ARM64
                print("🔨 Building Docker image for ARM64...")
                image_tag = f"{ecr_repo_uri}:latest"
                
                # Build with ARM64 platform
                build_cmd = ['docker', 'build', '--platform', 'linux/arm64', '-t', image_tag, temp_dir]
                print(f"💻 Running: {' '.join(build_cmd)}")
                
                build_result = subprocess.run(build_cmd, capture_output=True, text=True)
                
                if build_result.returncode != 0:
                    print(f"❌ Build failed with exit code: {build_result.returncode}")
                    print(f"📤 Build stdout: {build_result.stdout}")
                    print(f"📤 Build stderr: {build_result.stderr}")
                    raise Exception(f"❌ Docker build failed: {build_result.stderr}")
                
                print("✅ Docker image built successfully")
                
                # Push image to ECR
                print("📤 Pushing Docker image to ECR...")
                push_result = subprocess.run(
                    ['docker', 'push', image_tag],
                    capture_output=True, text=True
                )
                
                if push_result.returncode != 0:
                    print(f"❌ Docker push failed: {push_result.stderr}")
                    raise Exception(f"❌ Docker push failed: {push_result.stderr}")
                
                print("✅ Image pushed successfully to ECR!")
                
                # Verify the image exists in ECR
                self._verify_image_exists(ecr_repo_uri)
                
                # Clean up local Docker images to save space
                self._cleanup_local_images(image_tag)
                
                return True
                
            finally:
                # Clean up temp directory
                shutil.rmtree(temp_dir, ignore_errors=True)
                print("✅ Cleaned up temp directory")
                
        except ClientError as e:
            if "UnrecognizedClientException" in str(e):
                # Credentials are invalid
                raise Exception(f"❌ Invalid AWS credentials. Please check your access key and secret key.")
            else:
                raise Exception(f"❌ ECR operation failed: {str(e)}")
        except subprocess.CalledProcessError as e:
            raise Exception(f"❌ Docker operation failed: {e.stderr}")
        except Exception as e:
            raise Exception(f"❌ Image build/push failed: {str(e)}")
    
    def _verify_image_exists(self, ecr_repo_uri):
        """Verify that the image was pushed successfully"""
        try:
            # Extract repo name from URI
            repo_name = ecr_repo_uri.split('/')[-1].split(':')[0]
            
            print(f"🔍 Verifying image in ECR repository: {repo_name}")
            response = self.ecr.describe_images(
                repositoryName=repo_name,
                imageIds=[{'imageTag': 'latest'}]
            )
            
            if response['imageDetails']:
                image_detail = response['imageDetails'][0]
                print(f"✅ Image verified in ECR repository")
                print(f"   - Image Size: {image_detail.get('imageSizeInBytes', 0) / 1024 / 1024:.2f} MB")
                print(f"   - Pushed At: {image_detail.get('imagePushedAt', 'Unknown')}")
                return True
            else:
                raise Exception("❌ Image not found in ECR repository after push")
                
        except ClientError as e:
            raise Exception(f"❌ Error verifying image in ECR: {str(e)}")
    
    def _cleanup_local_images(self, image_tag):
        """Clean up local Docker images to save space"""
        try:
            print("🧹 Cleaning up local Docker images...")
            
            # Remove the specific image
            subprocess.run(['docker', 'rmi', image_tag], capture_output=True)
            print(f"✅ Removed image: {image_tag}")
            
            # Remove dangling images
            subprocess.run(['docker', 'image', 'prune', '-f'], capture_output=True)
            print("✅ Cleaned up dangling images")
            
            # Remove all unused images, containers, and networks
            subprocess.run(['docker', 'system', 'prune', '-a', '-f'], capture_output=True)
            print("✅ Cleaned up all unused Docker resources")
            
        except Exception as e:
            print(f"⚠️  Docker cleanup failed: {str(e)}")