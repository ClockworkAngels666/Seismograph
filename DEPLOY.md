# Publishing Seismographic (no coding needed)

Seismographic is published on **Hugging Face Spaces**: free, no "hosted by" badge on the app, and it updates by
itself every time the GitHub repository changes. Total time: about 10 minutes, once.

## 1. Create a Hugging Face account and a token (3 minutes)

1. Sign up at [huggingface.co/join](https://huggingface.co/join) and confirm your e-mail.
2. Open [huggingface.co/settings/tokens](https://huggingface.co/settings/tokens) → **Create new token**.
3. Choose the token type **Write**, name it `seismographic-publish`, click **Create token** and copy it.
   Keep it private: anyone with it can change your Spaces.

## 2. Connect GitHub to Hugging Face (2 minutes)

GitHub publishes the app for you, so it needs the token (stored encrypted, never shown again) and the Space's name.

In a terminal (it asks you to paste the token):

```bash
gh secret set HF_TOKEN -R ClockworkAngels666/Seismographic
```

```bash
gh variable set HF_SPACE -R ClockworkAngels666/Seismographic --body "YOUR-HF-USERNAME/Seismographic"
```

Or on github.com: the repository's **Settings → Secrets and variables → Actions**. Add a *secret* `HF_TOKEN`
(the token), then on the *Variables* tab a variable `HF_SPACE` (`YOUR-HF-USERNAME/Seismographic`).

## 3. Publish (5 minutes, mostly waiting)

1. On GitHub open the **Actions** tab → **Publish to Hugging Face** → **Run workflow**.
   It creates the Space the first time and uploads the app. After this, every push to `main` publishes by itself.
2. Open `huggingface.co/spaces/YOUR-HF-USERNAME/Seismographic`. It shows **Building** for 3–5 minutes, then
   **Running**.
3. Share the direct address, which shows the app full screen with nothing around it:
   `https://YOUR-HF-USERNAME-seismographic.hf.space` (your username in lower case).

The `Dockerfile` in the repository also runs the app on Render, Fly.io or any other Docker host.

## 4. Monthly data backup

The **Refresh data snapshot** action saves a copy of all data on the 3rd of every month, so pages open instantly
and keep working if a source is down. The Space republishes after each refresh. If a run fails at "Commit the
snapshot", go to **Settings → Actions → General → Workflow permissions**, pick **Read and write permissions**,
save, and run it again.

## 5. Make it yours

* **Write assessments**: use the app's *Assessment builder* page, download the file and upload it to the
  `assessments` folder. See `assessments/README.md` for a writing guide.
* **Fill the watchlist**: use the helper on the *Events watchlist* page, then edit `data/events.csv` on GitHub
  (pencil icon → paste the line at the bottom → *Commit changes*).
* **Change the model**: weights, thresholds and indicators are all in `prm/config.py`.

Every change you commit on GitHub appears in the live app a few minutes later.

## Troubleshooting

| Problem | Fix |
|---|---|
| The Space says it is sleeping | Free Spaces sleep after about two days without visitors. Opening it wakes it in under a minute; open it yourself before sending the link to anyone. |
| The Action fails with "401" or "403" | The token is missing or is not a **Write** token. Create a new one and set `HF_TOKEN` again. |
| The Action is skipped | The `HF_SPACE` variable is not set (step 2). |
| The Space shows "Build error" or "Runtime error" | Open the Space's **Logs** tab to see why. |
| A yellow banner says a source is unavailable | One of the APIs is down; scores use the other indicators. Click **↻ Refresh data** in the sidebar later. |
| News says it is unavailable | Every news source (Bing, Google, GDELT) refused at once — rare. It retries by itself within 10 minutes. |
| An assessment doesn't appear | Check the file name is the three-letter code (`NGA.md`), it is inside `assessments/`, and the top block starts and ends with `---`. |

## Putting it on your CV

> **Seismographic** — Designed and launched an open-source political-risk dashboard scoring around 200 economies
> on 17 indicators across four pillars, using live World Bank, IMF, UNHCR and UCDP data; authored quarterly
> risk assessments with probabilistic forecasts. *(link)*

Pin the repository on your GitHub profile and add the app link to the *Projects* or *Featured* section on LinkedIn.
