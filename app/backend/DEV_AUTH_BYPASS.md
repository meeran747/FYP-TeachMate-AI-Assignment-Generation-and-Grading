# Development Auth Bypass

## Quick Setup for Development

To bypass authentication during development and focus on assignment creation:

### Step 1: Add to `.env` file

```bash
# Development only - bypasses authentication
BYPASS_AUTH=true
```

### Step 2: Restart Backend

```bash
cd app/backend
source venv/bin/activate
python main_rbac.py
```

## What This Does

- ✅ All endpoints work without authentication
- ✅ Returns a mock "teacher" user for all requests
- ✅ No token verification needed
- ✅ Fast development workflow

## ⚠️ Important

- **ONLY use this in development!**
- **NEVER set `BYPASS_AUTH=true` in production!**
- This completely disables authentication

## To Re-enable Auth

Simply remove or set:
```bash
BYPASS_AUTH=false
```

Then restart the backend.

## Default User

When bypassed, all requests use:
- **User ID**: `dev-user-id`
- **Email**: `dev@example.com`
- **Role**: `teacher`
- **Name**: `Dev User`

This allows you to test assignment creation without dealing with authentication complexity.

