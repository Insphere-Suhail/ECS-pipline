# 🚀 ECS Infrastructure Creator

A powerful web-based tool that automates AWS ECS infrastructure
deployment with a fully integrated CI/CD pipeline setup.

```{=html}
<p align="center">
```
`<img src="https://img.shields.io/badge/AWS-ECS-orange?logo=amazonaws" alt="AWS ECS">`{=html}
`<img src="https://img.shields.io/badge/Docker-Enabled-blue?logo=docker" alt="Docker Enabled">`{=html}
`<img src="https://img.shields.io/badge/Python-Flask-green?logo=python" alt="Python Flask">`{=html}
`<img src="https://img.shields.io/badge/License-MIT-lightgrey" alt="MIT License">`{=html}
```{=html}
</p>
```
## ✨ Features

-   🚀 One-Click ECS Setup -- Deploy complete AWS ECS infrastructure
-   🔄 CI/CD Automation -- Automatic Docker builds and deployments
-   🎛️ Web GUI -- Easy-to-use interface for infrastructure configuration
-   🛡️ Security Groups -- Automated security group management
-   📦 Multi-Service Support -- ALB, ECS, RDS, VPN, and more
-   🔗 Bitbucket/GitHub Integration -- Clone repositories and build
    Docker images
-   🐳 Dockerized -- Run anywhere using Docker

## 🚀 Quick Start

### ✅ Prerequisites

Make sure Docker is installed and running:

``` bash
docker --version
docker info
```

### 🔧 Method 1: Using docker run

``` bash
# Build the Docker image
docker build -t ecs-infra-creator .

# Run the container
docker run -d   -p 80:80   -v /var/run/docker.sock:/var/run/docker.sock   -v $(pwd)/generated_projects:/app/generated_projects   -e AWS_ACCESS_KEY_ID=your_access_key   -e AWS_SECRET_ACCESS_KEY=your_secret_key   --name ecs-infra-creator   ecs-infra-creator
```

### 🔧 Method 2: Using Docker Compose

``` bash
# Start the application
docker-compose up -d

# Stop the application
docker-compose down
```

### 🌐 Access the Application

Open your browser and go to:

    http://localhost

## ⚙️ Environment Variables

  ------------------------------------------------------------------------
  Variable                  Description          Default        Required
  ------------------------- -------------------- -------------- ----------
  AWS_ACCESS_KEY_ID         AWS Access Key       \-             ✅ Yes

  AWS_SECRET_ACCESS_KEY     AWS Secret Key       \-             ✅ Yes

  AWS_DEFAULT_REGION        AWS Region           ap-south-1     ❌ No

  FLASK_ENV                 Flask environment    production     ❌ No

  HOST                      Bind host            0.0.0.0        ❌ No

  PORT                      Bind port            80             ❌ No
  ------------------------------------------------------------------------

## 📖 Usage Guide

1.  Access Web Interface: Open `http://localhost`
2.  Configure AWS Credentials: Input your Access Key and Secret Key
3.  Create Infrastructure: Set up VPC, Security Groups, EC2, etc.
4.  Monitor Progress: Real-time logs (10--15 minutes)
5.  Access Deployed App: Use the ALB DNS endpoint after deployment

## 🛡️ Security Group Configuration

  Group       Inbound Rules                       Purpose
  ----------- ----------------------------------- ----------------------
  ALB SG      HTTP/HTTPS from internet            Load Balancer access
  Server SG   HTTP/HTTPS from ALB, SSH from VPN   ECS instances
  RDS SG      MySQL from Server and VPN           Database access
  VPN SG      WireGuard from internet             VPN access

## ☁️ Supported AWS Services

-   🖥️ EC2 -- ARM64 instances (t4g, m6g, c6g)
-   📦 ECS -- Cluster using EC2 launch type
-   🐳 ECR -- Docker image registry
-   ⚖️ ALB -- Application Load Balancer
-   🌐 VPC -- Networking with NAT Gateway
-   🗄️ RDS -- MySQL (optional)
-   🔐 IAM -- Roles and policies
-   🛡️ Security Groups -- Automated configuration

## 🔧 Troubleshooting

``` bash
# Docker socket permission denied
sudo chmod 666 /var/run/docker.sock
```

AWS credentials invalid → Verify Access Key & Secret Key → Check IAM
permissions

``` bash
# Port 80 already in use
docker run -p 8080:80 ...
```

### Logs & Debugging

``` bash
# View logs
docker logs ecs-infra-creator

# Follow logs
docker logs -f ecs-infra-creator

# Access container shell
docker exec -it ecs-infra-creator bash
```

## 🏗️ Project Structure

    ecs-infra-creator/
    ├── app.py                 # Main Flask application
    ├── services/              # AWS service modules
    │   ├── aws_auth.py        # AWS authentication
    │   ├── vpc_service.py     # VPC management
    │   ├── sg_service.py      # Security groups
    │   ├── alb_service.py     # Load balancer
    │   ├── ecr_service.py     # Container registry
    │   ├── ecs_service.py     # ECS cluster & services
    │   ├── iam_service.py     # IAM roles
    │   └── ec2_service.py     # EC2 instances
    ├── templates/             # HTML templates
    ├── static/                # CSS, JS, images
    ├── ci-cd/                 # CI/CD template files
    ├── generated_projects/    # Output directory
    ├── requirements.txt       # Python dependencies
    ├── Dockerfile             # Docker configuration
    └── docker-compose.yml     # Docker Compose config

## 🛠️ Development

``` bash
# Clone the repository
git clone https://github.com/Insphere-Suhail/ECS-pipline.git
cd ECS-pipline

# Build Docker image with custom tag
docker build -t my-ecs-creator .

# Run in development mode
docker run -p 80:80   -v /var/run/docker.sock:/var/run/docker.sock   -v $(pwd):/app my-ecs-creator

# Or use Docker Compose
docker-compose up -d

# Stop the application
docker-compose down
```

## 🤝 Contributing

1.  Fork the repository\
2.  Create a feature branch\
3.  Make changes and test thoroughly\
4.  Submit a pull request

## 📄 License

Licensed under the MIT License. See the LICENSE file for details.

## 💬 Support

-   🐛 Open an issue\
-   🔧 Refer to the Troubleshooting section\
-   ✅ Verify AWS service quotas

## 🗺️ Roadmap

-   🌍 Multi-region deployment\
-   🚀 Fargate launch support\
-   📦 Terraform export option\
-   💰 Cost estimation feature\
-   🔗 Multi-account deployment support

::: {align="center"}
`<br>`{=html} `<strong>`{=html}Built with ❤️ using Python, Flask, and
Docker`</strong>`{=html}
:::
