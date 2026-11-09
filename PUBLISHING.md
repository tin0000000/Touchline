# Publish Touchline on the internet

This project has a Render Blueprint at the repository root. It deploys the Python web app and attaches a persistent disk for the SQLite account and club database.

## Steps

1. Put the whole `Touchline Prototype` folder in a GitHub repository. Keep `render.yaml` at the repository root and keep the `Installable App` folder beside it.
2. Create/sign into Render, connect your GitHub account, and choose **New → Blueprint**.
3. Select the repository. Render reads `render.yaml`; review the web service and persistent disk, then approve creation. The blueprint uses a paid Starter web service because Render Free web services do not support persistent disks. Current prices are listed on Render's pricing page.
4. Wait for the deploy to become live, then open its `onrender.com` URL. Create your manager account. In Settings, refresh team access to get the team invite code. Players can sign up and join with that code.
5. To use a custom domain, add it in the service's **Settings → Custom Domains**, then follow the DNS records Render shows.
6. On a phone, open the deployed HTTPS URL in the browser and choose **Add to Home Screen** / **Install app**.

Do not remove the persistent disk or change `TOUCHLINE_DB_PATH` after users have registered; that would make the service point at a different database. Back up the SQLite file before major changes. Render disks are attached to one service instance, so this single-process SQLite deployment is for an early community launch. A larger public service should migrate to managed PostgreSQL and add account recovery, email verification, and production monitoring.

A Render Free web service can be used to preview the interface only, but its filesystem is ephemeral and its free services can spin down. Do not use that setup for real accounts or club data.
