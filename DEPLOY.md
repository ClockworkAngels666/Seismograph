# Deploying Seismograph (no coding needed)

Total time: about 20 minutes. You need a free GitHub account and a free Streamlit Community Cloud account.

## 1. Put your name on it (2 minutes)

Open `prm/config.py` in any text editor (or edit it on GitHub after uploading — click the file, then the pencil
icon). Near the top, change:

```python
AUTHOR = "Your Name"
```

Also replace "Your Name", the LinkedIn link and the e-mail address at the bottom of `README.md`.

## 2. Put the code on GitHub (5 minutes)

1. Sign in at [github.com](https://github.com), click **+** (top right) → **New repository**.
2. Name it `seismograph`, choose **Public**, leave everything else unticked, click **Create repository**.
3. On the next page click **uploading an existing file**.
4. Unzip the project on your computer, open the project folder, select **everything inside it**
   and drag it onto the GitHub page. Keep the folder structure — drag the folders, not just the files.
5. Scroll down and click **Commit changes**.

**Hidden folders.** Two folders start with a dot: `.streamlit` (colours) and `.github` (monthly data backup).
Mac's Finder hides them — press **Cmd + Shift + .** in the folder window to show them before selecting everything.
On Windows, tick **View → Hidden items** in File Explorer. If they don't upload, the app still works; you can add
them later with **Add file → Create new file** and type the path, e.g. `.streamlit/config.toml`, then paste the contents.

## 3. Deploy on Streamlit Community Cloud (5 minutes)

1. Go to [share.streamlit.io](https://share.streamlit.io) and sign in with GitHub. Allow Streamlit to access your
   repositories when asked.
2. Click **Create app** → deploy from a GitHub repository.
3. Choose your repository, branch `main`, main file path `streamlit_app.py`.
4. Optional but recommended: set a custom **App URL** such as `seismograph-yourname`.
5. Click **Deploy**. The first build takes a few minutes. Pages then open instantly from the saved snapshot and
   switch to live data by themselves about a minute later.

Copy the app's address and paste it into the top of `README.md` on GitHub.

## 4. Turn on the monthly data backup (2 minutes)

1. In your repository, open the **Actions** tab. If asked, click **I understand my workflows, go ahead and enable them**.
2. Click **Refresh data snapshot** → **Run workflow**. After a minute or two a `data/snapshot` folder appears in
   your repository. From now on it refreshes on the 3rd of every month.
3. If the run fails at "Commit the snapshot", go to **Settings → Actions → General → Workflow permissions**, pick
   **Read and write permissions**, save, and run it again.

## 5. Make it yours

* **Write assessments**: use the app's *Assessment builder* page, download the file and upload it to the
  `assessments` folder. See `assessments/README.md` for a writing guide.
* **Fill the watchlist**: use the helper on the *Events watchlist* page, then edit `data/events.csv` on GitHub
  (pencil icon → paste the line at the bottom → *Commit changes*).
* **Change the model**: weights, thresholds and indicators are all in `prm/config.py`.

Every change you commit on GitHub appears in the live app within a few minutes.

## Troubleshooting

| Problem | Fix |
|---|---|
| "This app has gone to sleep" | Free apps sleep after a period without visitors. Click the button to wake it; open it yourself before sending the link to anyone. |
| A yellow banner says a source is unavailable | One of the APIs is down; scores use the other indicators. Click **↻ Refresh data** in the sidebar later. |
| News says it is unavailable | Every news source (Bing, Google, GDELT) refused at once — rare. It retries by itself within 10 minutes. |
| The app shows an error on start-up | In Streamlit Cloud, open **Manage app** (bottom right) to see the logs, and check that `requirements.txt` was uploaded. |
| An assessment doesn't appear | Check the file name is the three-letter code (`NGA.md`), it is inside `assessments/`, and the top block starts and ends with `---`. |

## Putting it on your CV

> **Seismograph** — Designed and launched an open-source political-risk dashboard scoring around 200 economies
> on 17 indicators across four pillars, using live World Bank, IMF, UNHCR and UCDP data; authored quarterly
> risk assessments with probabilistic forecasts. *(link)*

Pin the repository on your GitHub profile and add the app link to the *Projects* or *Featured* section on LinkedIn.
