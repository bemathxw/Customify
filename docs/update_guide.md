# Update Guide for Customify

This document provides step-by-step instructions for updating the Customify application in a production environment.

## Preparation

### 1. Review Release Notes

- Review the release notes for the new version
- Check for breaking changes or new dependencies
- Verify compatibility with your current environment

### 2. Create Backups

```bash
# Log in to the server
ssh user@your-server

# Create backup of environment variables
sudo cp /home/customify/app/.env /home/customify/app/.env.backup.$(date +%Y%m%d)

# Create backup of Nginx configuration
sudo cp /etc/nginx/sites-available/customify /etc/nginx/sites-available/customify.backup.$(date +%Y%m%d)

# Create backup of systemd service file
sudo cp /etc/systemd/system/customify.service /etc/systemd/system/customify.service.backup.$(date +%Y%m%d)
```

### 3. Plan Downtime

- Schedule the update during low-traffic periods
- Estimate downtime (typically 5-15 minutes)
- Notify users if necessary (for major updates)

### 4. Create Update Branch

```bash
# Switch to application user
sudo su - customify

# Navigate to app directory
cd ~/app

# Create a temporary branch for testing the update
git checkout -b update-test

# Pull the latest changes
git fetch origin

# Check out the new version (replace X.Y.Z with the version number)
git checkout vX.Y.Z
```

### 5. Test Update Locally (Optional)

If possible, test the update in a staging environment before applying to production.

## Update Process

### 1. Stop Services

```bash
# Exit to root user if you're still the application user
exit

# Stop the Gunicorn service
sudo systemctl stop customify

# Optionally, put Nginx in maintenance mode
# (Create a maintenance page first if needed)
```

### 2. Deploy New Code

```bash
# Switch to application user
sudo su - customify

# Navigate to app directory
cd ~/app

# Backup current code state
git describe --tags > ~/previous_version.txt

# Switch to main branch
git checkout main

# Pull the latest changes
git pull origin main

# If deploying a specific version:
# git checkout vX.Y.Z
```

### 3. Update Dependencies

```bash
# Activate virtual environment
source venv/bin/activate

# Update pip
pip install --upgrade pip

# Install/update dependencies
pip install -r requirements.txt
```

### 4. Update Configuration

```bash
# Check if new environment variables are needed
# If yes, update the .env file
nano .env

# Compare with example configuration if available
# diff -u .env.example .env
```

### 5. Restart Services

```bash
# Exit to root user
exit

# Restart the Gunicorn service
sudo systemctl restart customify

# Check service status
sudo systemctl status customify

# If you modified Nginx configuration, test and reload
sudo nginx -t
sudo systemctl reload nginx
```

## Post-Update Verification

### 1. Verify Application Status

```bash
# Check application logs for errors
sudo journalctl -u customify -n 50 --no-pager

# Check Nginx logs
sudo tail -n 50 /var/log/nginx/error.log
```

### 2. Perform Health Checks

1. **Basic Connectivity Test**:
   ```bash
   curl -I https://customify.example.com
   ```
   Expected result: HTTP 200 OK

2. **Functional Testing**:
   - Open the application in a browser
   - Test Spotify login functionality
   - Verify recommendations are generated
   - Test playlist creation
