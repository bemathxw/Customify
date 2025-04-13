# Deployment Guide for Customify

This document provides instructions for deploying the Customify application in a production environment.

## Hardware Requirements

### Minimum Requirements
- **Architecture**: x86_64 / AMD64
- **CPU**: 2 cores, 2.0 GHz
- **RAM**: 2 GB
- **Disk Space**: 1 GB for application and dependencies
- **Network**: 100 Mbps connection

### Recommended Requirements
- **CPU**: 4 cores, 2.5 GHz
- **RAM**: 4 GB
- **Disk Space**: 5 GB for application, logs, and future updates

## Software Requirements

- **Operating System**: Ubuntu 20.04 LTS or newer
- **Python**: Version 3.8 or higher
- **Web Server**: Nginx 1.18 or newer
- **WSGI Server**: Gunicorn 20.0 or newer
- **SSL Certificate**: Let's Encrypt or commercial SSL certificate

## Network Configuration

1. **Firewall Settings**:
   - Allow HTTP (port 80)
   - Allow HTTPS (port 443)
   - Allow SSH (port 22) for administration

2. **Domain Configuration**:
   - Configure DNS A record pointing to your server's IP address
   - Set up a domain name for the application (e.g., customify.example.com)

3. **SSL Configuration**:
   - Install and configure SSL certificate for secure HTTPS connections

## Server Configuration

### 1. Install Required Software

```bash
# Update package lists
sudo apt update

# Install Python and dependencies
sudo apt install -y python3 python3-pip python3-venv

# Install Nginx
sudo apt install -y nginx

# Install Certbot for SSL
sudo apt install -y certbot python3-certbot-nginx
```

### 2. Create Application User

```bash
# Create a dedicated user for the application
sudo useradd -m -s /bin/bash customify

# Switch to the application user
sudo su - customify
```

### 3. Set Up Application Directory

```bash
# Create application directory
mkdir -p ~/app

# Clone the repository
git clone https://github.com/bemathxw/customify.git ~/app

# Navigate to app directory
cd ~/app

# Create virtual environment
python3 -m venv venv

# Activate virtual environment
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Install Gunicorn
pip install gunicorn
```

### 4. Configure Environment Variables

Create a `.env` file in the application directory:

```bash
# Create and edit .env file
nano ~/app/.env
```

Add the following content:

```
FLASK_SECRET_KEY=your_secure_random_key
SPOTIFY_CLIENT_ID=your_spotify_client_id
SPOTIFY_CLIENT_SECRET=your_spotify_client_secret
FLASK_ENV=production
```

Make sure to replace placeholder values with actual secure values.

### 5. Configure Gunicorn

Create a Gunicorn service file:

```bash
# Exit to root user
exit

# Create service file
sudo nano /etc/systemd/system/customify.service
```

Add the following content:

```
[Unit]
Description=Gunicorn instance to serve Customify
After=network.target

[Service]
User=customify
Group=www-data
WorkingDirectory=/home/customify/app
Environment="PATH=/home/customify/app/venv/bin"
EnvironmentFile=/home/customify/app/.env
ExecStart=/home/customify/app/venv/bin/gunicorn --workers 3 --bind 127.0.0.1:8000 app:app

[Install]
WantedBy=multi-user.target
```

Enable and start the service:

```bash
sudo systemctl enable customify
sudo systemctl start customify
```

### 6. Configure Nginx

Create an Nginx configuration file:

```bash
sudo nano /etc/nginx/sites-available/customify
```

Add the following content:

```
server {
    listen 80;
    server_name customify.example.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Enable the site and restart Nginx:

```bash
sudo ln -s /etc/nginx/sites-available/customify /etc/nginx/sites-enabled
sudo nginx -t
sudo systemctl restart nginx
```

### 7. Set Up SSL with Let's Encrypt

```bash
sudo certbot --nginx -d customify.example.com
```

Follow the prompts to complete SSL setup.

## Database Configuration

This application does not require a database as it uses Spotify API and session storage. If you need persistent storage in the future, consider adding a database like PostgreSQL.

## Code Deployment

### Initial Deployment

The initial deployment is covered in the server configuration steps above.

### Updating the Application

To update the application:  

```bash
# Switch to application user
sudo su - customify

# Navigate to app directory
cd ~/app

# Pull latest changes
git pull

# Activate virtual environment
source venv/bin/activate

# Install any new dependencies
pip install -r requirements.txt

# Exit to root user
exit

# Restart the service
sudo systemctl restart customify
```

## Health Check

### Verify Service Status

```bash
# Check if Gunicorn service is running
sudo systemctl status customify

# Check Nginx status
sudo systemctl status nginx
```

### Application Health Check

1. **Basic HTTP Check**:
   - Open your browser and navigate to your domain (https://customify.example.com)
   - Verify that the home page loads correctly

2. **Functionality Check**:
   - Try to log in with Spotify
   - Verify that recommendations are generated
   - Check that playlists can be created

3. **Log Monitoring**:
   ```bash
   # Check application logs
   sudo journalctl -u customify

   # Check Nginx access logs
   sudo tail -f /var/log/nginx/access.log

   # Check Nginx error logs
   sudo tail -f /var/log/nginx/error.log
   ```

4. **Set Up Monitoring** (Optional):
   - Consider setting up monitoring with tools like Prometheus and Grafana
   - Monitor CPU, memory usage, and response times


## Backup Strategy

1. **Configuration Backup**:
   - Regularly back up `.env` file
   - Back up Nginx and Gunicorn configuration files

2. **Application Backup**:
   - The application code is stored in Git, so a full backup is not necessary
   - Consider setting up a CI/CD pipeline for automated deployments