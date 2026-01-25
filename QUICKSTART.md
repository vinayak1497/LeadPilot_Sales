# SalesShortcut - Local Setup Guide

## ✅ Setup Complete!

The LeadPilot project has been cloned and the UI Client is now running locally.

## 🌐 Access the Application

The UI Client is accessible at: **http://localhost:8000**

## 📝 What's Been Set Up

1. ✅ Repository cloned to: C:\Users\avani\LeadPilot_DDoxers_2026
2. ✅ Virtual environment already configured at .venv
3. ✅ Dependencies installed (with jinja2 added)
4. ✅ .env file created from template
5. ✅ UI Client service running on port 8000

## 🚀 Starting the Services

### Quick Start (UI Client Only)
Double-click the file: **start_ui.bat**

Or run in PowerShell:
```powershell
cd C:\Users\avani\LeadPilot_DDoxers_2026
.\start_ui.bat
```

### Start All Services (when needed)
To start all services (Lead Finder, Lead Manager, SDR, etc.), you'll need to configure API keys first (see below), then run each service separately.

## ⚙️ Configuration Required

The project needs API keys to function fully. Edit the .env file and add:

### Required API Keys:
- **GOOGLE_API_KEY** - For Gemini LLM (AI features)
- **GOOGLE_MAPS_API_KEY** - For finding businesses via Google Maps
- **GOOGLE_CLOUD_PROJECT** - Your Google Cloud Project ID

### Optional API Keys (for full features):
- **ELEVENLABS_API_KEY** - For AI phone calls
- **EMAIL_USERNAME** & **EMAIL_PASSWORD** - For email features
- **OPENAI_API_KEY** - Alternative AI provider
- **ANTHROPIC_API_KEY** - Alternative AI provider

### How to Edit Configuration:
```powershell
notepad .env
```

## 📦 Services Architecture

The project consists of 5 microservices:

1. **UI Client** (Port 8000) - Web dashboard ✅ RUNNING
2. **Lead Finder** (Port 8081) - Discovers potential leads
3. **Lead Manager** (Port 8082) - Manages lead data
4. **SDR Agent** (Port 8084) - AI-powered outreach
5. **Gmail PubSub** (Port 8083) - Email monitoring

## 🔍 Key Features

- **Lead Generation**: Find businesses without websites in any city
- **AI Research**: Automated business analysis
- **Personalized Outreach**: Phone calls and emails
- **Lead Management**: Track conversions and schedule meetings

## 📖 Documentation

- Main README: [README.md](README.md)
- Installation Guide: [INSTALLATION.md](INSTALLATION.md)
- Deployment Guide: [DEPLOYMENT.md](DEPLOYMENT.md)
- Environment Setup: [ENVIRONMENT.md](ENVIRONMENT.md)

## 🛠️ Troubleshooting

### UI Client Won't Start
1. Make sure port 8000 is not in use: `netstat -ano | findstr :8000`
2. Check the virtual environment: `.venv\Scripts\python.exe --version`
3. Verify dependencies: `.venv\Scripts\pip.exe list`

### Missing Dependencies
If you encounter "No module named..." errors:
```powershell
.venv\Scripts\pip.exe install -r requirements.txt
```

### Email Tracking Warning
The warning "Email credentials not configured" is normal if you haven't set up email yet. The UI will still work for other features.

## 📚 Next Steps

1. **Configure API Keys**: Edit .env with your API credentials
2. **Explore the UI**: Visit http://localhost:8000
3. **Start Other Services**: Follow INSTALLATION.md to start additional services
4. **Read Documentation**: Check out the README files for each service

## 🆘 Getting Help

- Check individual service READMEs in their respective folders
- Review [INSTALLATION.md](INSTALLATION.md) for detailed setup
- See [ENVIRONMENT.md](ENVIRONMENT.md) for API setup guides

---

**Project successfully running locally! 🎉**
