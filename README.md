# Simulateur d'Arnaque Dynamique et Interactif

## Identification du groupe (obligatoire)
- Nom Prenom 1: A REMPLIR
- Nom Prenom 2: A REMPLIR
- Nom Prenom 3: A REMPLIR

## Objectif
Ce projet implemente un theatre d'arnaque orchestre par plusieurs agents:
- Agent Victime (Jean Dubois)
- Agent Directeur de scenario
- Agent Moderateur Audience

Le systeme suit un script d'arnaque de type support technique, integre des outils audio (`@tool` LangChain) et une interface frontend pour visualiser la discussion et le vote audience.

## Regles eliminatoires appliquees
1. Aucun secret dans le code.
2. `.env` est ignore par Git.
3. Les fichiers de cles JSON locaux sont ignores par Git (ex: `ipssi-*.json`).
4. `.env.example` est fourni sans valeur sensible.

## Architecture
### Backend (FastAPI)
- `app/main.py`: API REST + serveur frontend.
- `app/state.py`: moteur de simulation et etat global.
- `app/agents.py`: logique Directeur / Moderateur / Victime.
- `app/tools.py`: outils audio LangChain (`dog_bark`, `doorbell`, `coughing_fit`, `tv_background`).
- `app/scenario.py`: script et progression par etapes.

### Frontend (vanilla JS)
- `frontend/index.html`: interface discussion + audience.
- `frontend/styles.css`: style responsive.
- `frontend/app.js`: appels API + rendu temps reel.

## Workflow implemente (etape par etape)
1. L'arnaqueur envoie un message.
2. Le Directeur analyse l'echange et met a jour l'objectif de Jean.
3. Le Moderateur audience peut filtrer les propositions et en garder 3.
4. Le vote (manuel ou simule) applique une contrainte temporaire.
5. La Victime repond avec prompt modulaire + outils audio possibles.
6. Le frontend affiche:
- discussion complete,
- objectif/stage courant,
- contrainte audience,
- effets sonores declenches.

## Installation
1. Creer l'environnement virtuel:
```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```
2. Installer les dependances:
```powershell
pip install -r requirements.txt
```
Si vous avez besoin du provider Vertex, installez en plus:
```powershell
pip install -r requirements-vertex.txt
```
3. Configurer les variables:
```powershell
Copy-Item .env.example .env
```
4. Renseigner dans `.env`:
- Mode automatique (recommande):
  - `LLM_PROVIDER=auto` (priorite a Gemini si `GOOGLE_API_KEY` est defini, sinon Vertex si un fichier service account Google est detecte)
- Si vous utilisez Gemini sans Vertex (recommande si Vertex AI API est indisponible):
  - `LLM_PROVIDER=gemini`
  - `GOOGLE_API_KEY=...` (ou `GOOGLE_API_KEY_FILE=./votre_fichier.json` avec une cle `api_key`)
  - `GOOGLE_MODEL=gemini-1.5-flash`
- Si vous utilisez la cle Google fournie (`ipssi-487113-729cf7c9a4af.json`):
  - `LLM_PROVIDER=vertex`
  - `GOOGLE_APPLICATION_CREDENTIALS=./ipssi-487113-729cf7c9a4af.json`
  - `VERTEX_PROJECT_ID=ipssi-487113` (ou laisser vide, auto-detection)
  - `VERTEX_LOCATION=us-central1`
  - `VERTEX_MODEL=gemini-2.0-flash-001`
- Si vous utilisez OpenAI:
  - `OPENAI_API_KEY=...`
  - `OPENAI_MODEL=gpt-4o-mini`

## Controle securite avant commit
```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\preflight_security_check.ps1
```
Si le script detecte un secret, corriger avant tout commit.

## Lancer l'application
```powershell
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

Puis ouvrir `http://127.0.0.1:8000`.

## Endpoints API utiles
- `GET /api/health`
- `GET /api/simulation/state`
- `POST /api/simulation/reset`
- `POST /api/simulation/step`
- `POST /api/simulation/step/stream` (SSE)
- `POST /api/audience/submit`
- `POST /api/audience/select`
- `POST /api/audience/vote`
- `POST /api/audience/vote/simulate`

## Exemple rapide (curl)
```bash
curl -X POST http://127.0.0.1:8000/api/simulation/step \
  -H "Content-Type: application/json" \
  -d "{\"scammer_input\":\"Bonjour, support Microsoft, votre PC est infecte.\"}"
```

## Captures et preuves de fonctionnement
Ajouter vos captures ici:
- `docs/screenshots/01_overview.png`
- `docs/screenshots/02_audience_vote.png`
- `docs/screenshots/03_sound_effects.png`

## Qualite de rendu attendue
- Code propre et lisible.
- Aucune fuite de secret.
- Demonstration de la boucle multi-agents.
- Exemples de conversation dans `docs/examples.md`.
