# Momentoooo Deployment Guide

This guide covers deploying Momentoooo to various cloud platforms.

## 📋 Pre-Deployment Checklist

Before deploying, ensure you have:

- [ ] Git repository with your code
- [ ] All dependencies in `requirements.txt`
- [ ] Environment variables documented
- [ ] PostgreSQL database (provided by platform or external)

---

## 🚀 Quick Start Files

### Procfile (Required for Heroku/Railway)
Create a `Procfile` in your project root:
```
web: gunicorn app:app
```

### runtime.txt (Optional - specifies Python version)
```
python-3.12.0
```

---

## 🌐 Deployment Options

### Option 1: Railway (Recommended - Easiest)

**Free tier:** $5 credit/month (enough for hobby projects)

1. **Push to GitHub**
   ```bash
   git init
   git add .
   git commit -m "Initial commit"
   git remote add origin https://github.com/yourusername/momentoooo.git
   git push -u origin main
   ```

2. **Deploy on Railway**
   - Go to [railway.app](https://railway.app)
   - Click "Start a New Project"
   - Select "Deploy from GitHub repo"
   - Choose your repository

3. **Add PostgreSQL**
   - Click "New" → "Database" → "PostgreSQL"
   - Railway automatically sets `DATABASE_URL`

4. **Set Environment Variables**
   - Click on your app → "Variables"
   - Add each variable:
   ```
   FLASK_SECRET_KEY=your-secure-random-key
   ADMIN_USERNAME=admin
   ADMIN_PASSWORD=your-secure-password
   BREVO_API_KEY=your-brevo-api-key
   BREVO_SENDER_EMAIL=your-email@domain.com
   BREVO_SENDER_NAME=Momentoooo
   STRIPE_PUBLIC_KEY=pk_live_xxx
   STRIPE_SECRET_KEY=sk_live_xxx
   ```

5. **Deploy**
   - Railway auto-deploys on push
   - Visit your app at `https://yourapp.railway.app`

---

### Option 2: Render
after
**Free tier:** 750 hours/month, spins down  15 min inactivity

1. **Create render.yaml** in project root:
   ```yaml
   services:
     - type: web
       name: momentoooo
       env: python
       buildCommand: pip install -r requirements.txt
       startCommand: gunicorn app:app
       envVars:
         - key: DATABASE_URL
           fromDatabase:
             name: momentoooo-db
             property: connectionString

   databases:
     - name: momentoooo-db
       plan: free
   ```

2. **Deploy on Render**
   - Go to [render.com](https://render.com)
   - Click "New" → "Blueprint"
   - Connect your GitHub repo
   - Render reads `render.yaml` and sets up everything

3. **Add Environment Variables**
   - Go to your service → "Environment"
   - Add all required variables

---

### Option 3: Heroku

**Eco tier:** $5/month for dynos + $5/month for PostgreSQL

1. **Install Heroku CLI**
   ```bash
   curl https://cli-assets.heroku.com/install.sh | sh
   ```

2. **Create Heroku App**
   ```bash
   heroku login
   heroku create momentoooo-app
   ```

3. **Add PostgreSQL**
   ```bash
   heroku addons:create heroku-postgresql:essential-0
   ```

4. **Set Environment Variables**
   ```bash
   heroku config:set FLASK_SECRET_KEY=your-secret-key
   heroku config:set ADMIN_USERNAME=admin
   heroku config:set ADMIN_PASSWORD=your-password
   heroku config:set BREVO_API_KEY=your-api-key
   heroku config:set BREVO_SENDER_EMAIL=your@email.com
   heroku config:set BREVO_SENDER_NAME=Momentoooo
   ```

5. **Deploy**
   ```bash
   git push heroku main
   ```

6. **Open App**
   ```bash
   heroku open
   ```

---

### Option 4: Fly.io

**Free tier:** 3 shared-cpu-1x VMs, 3GB storage

1. **Install Fly CLI**
   ```bash
   curl -L https://fly.io/install.sh | sh
   ```

2. **Create fly.toml**
   ```toml
   app = "momentoooo"
   primary_region = "ord"

   [build]
     builder = "paketobuildpacks/builder:base"

   [env]
     PORT = "8080"

   [http_service]
     internal_port = 8080
     force_https = true

   [[services]]
     internal_port = 8080
     protocol = "tcp"

     [[services.ports]]
       handlers = ["http"]
       port = 80

     [[services.ports]]
       handlers = ["tls", "http"]
       port = 443
   ```

3. **Deploy**
   ```bash
   fly auth login
   fly launch
   fly postgres create
   fly postgres attach --app momentoooo
   fly secrets set FLASK_SECRET_KEY=your-secret
   fly deploy
   ```

---

### Option 5: DigitalOcean App Platform

**Cost:** ~$5/month for basic app + $15/month for managed PostgreSQL

1. Go to [cloud.digitalocean.com](https://cloud.digitalocean.com)
2. Click "Apps" → "Create App"
3. Connect GitHub repository
4. Configure:
   - **Type:** Web Service
   - **Run Command:** `gunicorn app:app`
5. Add managed PostgreSQL database
6. Set environment variables
7. Deploy

---

## 🔐 Environment Variables Reference

| Variable | Required | Description |
|----------|----------|-------------|
| `DATABASE_URL` | Yes | PostgreSQL connection string |
| `FLASK_SECRET_KEY` | Yes | Random string for session security |
| `ADMIN_USERNAME` | Yes | Initial admin username |
| `ADMIN_PASSWORD` | Yes | Initial admin password |
| `BREVO_API_KEY` | Yes | Brevo email API key |
| `BREVO_SENDER_EMAIL` | Yes | Verified sender email |
| `BREVO_SENDER_NAME` | No | Sender name (default: Momento) |
| `STRIPE_PUBLIC_KEY` | No | Stripe publishable key |
| `STRIPE_SECRET_KEY` | No | Stripe secret key |
| `STRIPE_WEBHOOK_SECRET` | No | Stripe webhook signing secret |

---

## 🔧 Generating a Secure Secret Key

```python
python -c "import secrets; print(secrets.token_hex(32))"
```

---

## 🗄️ Database Migration

When deploying to a new PostgreSQL database:

1. The app automatically creates tables on first run
2. If you need to reset:
   ```sql
   DROP SCHEMA public CASCADE;
   CREATE SCHEMA public;
   ```

---

## 🐛 Troubleshooting

### "Application Error" on Heroku/Railway
- Check logs: `heroku logs --tail` or Railway dashboard
- Ensure `Procfile` exists and is correct
- Verify all environment variables are set

### Database Connection Issues
- Verify `DATABASE_URL` is set correctly
- Check if database is provisioned and running
- Ensure `psycopg2-binary` is in requirements.txt

### Static Files Not Loading
- Ensure `static/` folder is committed
- Check for case-sensitivity in file paths

### WebAuthn/Biometric Not Working
- WebAuthn requires HTTPS (works on deployed apps)
- Set correct `RP_ID` in `routes/biometric.py` to your domain

---

## 🌍 Custom Domain

### Railway
1. Go to Settings → Domains
2. Click "Generate Domain" or "Add Custom Domain"
3. Add CNAME record to your DNS

### Render
1. Go to Settings → Custom Domains
2. Add your domain
3. Configure DNS as instructed

### Heroku
```bash
heroku domains:add www.yourdomain.com
# Add CNAME record pointing to your-app.herokuapp.com
```

---

## 📊 Monitoring

### View Logs
- **Railway:** Dashboard → Deployments → View Logs
- **Render:** Dashboard → Logs
- **Heroku:** `heroku logs --tail`
- **Fly.io:** `fly logs`

### Health Check
Add to your app:
```python
@app.route('/health')
def health():
    return {'status': 'healthy'}, 200
```

---

## 🔄 Continuous Deployment

All platforms support auto-deploy on git push:

1. Push to GitHub
2. Platform detects changes
3. Builds and deploys automatically

---

## 📝 Production Checklist

- [ ] Set `FLASK_ENV=production`
- [ ] Use strong, unique `FLASK_SECRET_KEY`
- [ ] Enable HTTPS (automatic on most platforms)
- [ ] Set up error monitoring (Sentry, etc.)
- [ ] Configure backup for PostgreSQL
- [ ] Set up custom domain with SSL
- [ ] Update `RP_ID` in biometric.py to production domain
