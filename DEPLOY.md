# Deploy publicly (Streamlit Community Cloud, free)

Visitors will not need a Groq key: the key is stored in Streamlit's private **Secrets** settings, never in the code.

## 1. Put the code on GitHub (one time)
1. Sign in at https://github.com and create a new repository named `marsh-pitch-generator`. Leave it empty (no README).
2. In Terminal:
   ```bash
   cd ~/Marsh_Case_Study/1_Working_Application
   git remote add origin https://github.com/<your-username>/marsh-pitch-generator.git
   git push -u origin main
   ```
   Git will ask you to sign in to GitHub in the browser the first time.

## 2. Deploy the app
1. Go to https://share.streamlit.io and sign in with GitHub.
2. **Create app** → *Deploy a public app from GitHub* → repository `marsh-pitch-generator`, branch `main`, main file `app.py`.
3. Choose an app URL (e.g. `marsh-pitch-generator`).
4. **Advanced settings** → Python version **3.12** → **Secrets**: paste
   ```toml
   GROQ_API_KEY = "gsk_...your key..."
   ```
5. Click **Deploy**. The first build takes 2–4 minutes. Your link will be `https://<chosen-name>.streamlit.app`.

## Notes
- Each visitor gets up to 15 AI-generated pitches per session (`MAX_RUNS_PER_SESSION` secret), which protects your free Groq quota. After that the app switches to template mode and keeps working.
- To change the key later: app → **Settings → Secrets**. Never commit `.env`; it is excluded by `.gitignore`.
- Free apps go to sleep after a few days without visits. The first visitor then clicks "Yes, get this app back up" and waits about 30 seconds.
