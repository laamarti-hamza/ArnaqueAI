# Arnaqueur VS Jean Dubois

## Auteurs
- Paul Sode
- Mohammed Hamza Laamarti

## Présentation
Ce projet est une simulation interactive d'arnaque téléphonique.  
Un arnaqueur échange avec Jean Dubois (victime simulée), pendant qu'un système multi-agents pilote la scène en temps réel.

L'objectif est pédagogique: illustrer les techniques de manipulation, la résistance d'un profil vulnérable et l'impact d'interruptions contextuelles (audience, événements sonores, distractions).

## Objectifs du projet
- Simuler un scénario d'arnaque de type "faux support technique".
- Orchestrer plusieurs agents IA spécialisés.
- Permettre une intervention audience avec propositions et vote.
- Afficher une conversation vivante avec streaming, synthèse vocale et effets sonores intégrés au texte.
- Rester robuste même en cas d'indisponibilité d'un fournisseur LLM.

## Fonctionnalités principales

### 1) Orchestration multi-agents
- **Directeur**: choisit la progression du scénario et définit l'objectif tactique.
- **Victime (Jean Dubois)**: répond selon un persona précis, lent, méfiant, parfois distrait.
- **Modérateur audience**: nettoie, corrige et sélectionne les propositions du public.

### 2) Discussion en temps réel
- Envoi d'un message arnaqueur via l'interface.
- Réponse de Jean en streaming SSE.
- Affichage progressif type "machine à écrire".

### 3) Système audience par pop-ups
- Tous les **3 messages arnaqueur**, un pop-up de propositions apparaît.
- L'utilisateur peut:
  - saisir une proposition,
  - ajouter plusieurs propositions,
  - lancer la sélection de 3 choix.
- Une fois la sélection terminée, un second pop-up de vote apparaît:
  - vote manuel sur un choix,
  - ou vote simulé.

### 4) Effets sonores dans le texte
- Les tags sonores sont insérés dans le message victime:
  - `[SOUND_EFFECT: DOG_BARKING]`
  - `[SOUND_EFFECT: DOORBELL]`
  - `[SOUND_EFFECT: COUGHING_FIT]`
  - `[SOUND_EFFECT: TV_BACKGROUND_BFMTV]`
- Dans le frontend, ces tags sont rendus en étiquettes inline (`Son : ...`) au sein du texte.
- Les effets sonores sont déclenchés en synchronisation avec la narration vocale.

### 5) Synthèse vocale de la victime
- Endpoint dédié pour générer l'audio de la réponse victime.
- Mode dégradé prévu si la synthèse vocale est indisponible.

### 6) Robustesse et fallback
- Si un appel LLM distant échoue (OAuth/SSL/réseau), la simulation bascule sur des heuristiques locales.
- La conversation continue sans blocage de l'interface.

## Architecture technique

### Backend (FastAPI)
- `app/main.py`: API REST, streaming SSE, exposition des fichiers statiques frontend et sons.
- `app/state.py`: moteur de simulation et état global (thread-safe).
- `app/agents.py`: logique Directeur / Victime / Modérateur.
- `app/voice.py`: synthèse vocale de Jean.
- `app/tools.py`: outils audio et extraction des effets.
- `app/scenario.py`: étapes du scénario et détection de progression.
- `app/config.py`: chargement et auto-détection de configuration.
- `app/schemas.py`: validation des payloads.

### Frontend (Vanilla JS)
- `frontend/index.html`: structure de l'interface.
- `frontend/styles.css`: style moderne, responsive.
- `frontend/app.js`: rendu des messages, pop-ups audience, appels API, audio voix + effets.

### Ressources audio
- `app/sounds/dog-barking.mp3`
- `app/sounds/doorbell.mp3`
- `app/sounds/coughing.mp3`
- `app/sounds/tvbackground.mp3`

## Arborescence utile
```text
ArnaqueAI/
├── app/
│   ├── main.py
│   ├── state.py
│   ├── agents.py
│   ├── voice.py
│   ├── tools.py
│   ├── config.py
│   ├── scenario.py
│   ├── schemas.py
│   └── sounds/
├── frontend/
│   ├── index.html
│   ├── styles.css
│   └── app.js
├── docs/
│   ├── examples.md
│   └── screenshots/
├── scripts/
│   └── preflight_security_check.ps1
├── .env.example
├── requirements.txt
└── README.md
```

## Installation

### Prérequis
- Python 3.10+ recommandé
- `pip`

### 1. Créer un environnement virtuel
```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

### 2. Installer les dépendances
```powershell
pip install -r requirements.txt
```

### 3. Configurer l'environnement
```powershell
Copy-Item .env.example .env
```

Renseigner ensuite `.env` selon le fournisseur choisi.

## Configuration `.env`

### Fournisseurs LLM supportés
- `openai`
- `anthropic`
- `gemini`
- `vertex`
- `auto`
- `none`

### Exemple Vertex (LLM + voix)
```env
LLM_PROVIDER=vertex
GOOGLE_APPLICATION_CREDENTIALS=./ipssi-487113-729cf7c9a4af.json
VERTEX_PROJECT_ID=ipssi-487113
VERTEX_LOCATION=us-central1
VERTEX_MODEL=gemini-2.0-flash-001

VICTIM_VOICE_ENABLED=true
VERTEX_TTS_MODEL=gemini-2.5-flash-preview-tts
VERTEX_TTS_VOICE=Sadaltager
VERTEX_TTS_LANGUAGE=fr-FR
VERTEX_TTS_STYLE_PROMPT=Voix d'homme âgé, fatigué et tremblante, débit lent, ton naturel. Lire exactement le texte fourni.
```

### Exemple Gemini Developer API
```env
LLM_PROVIDER=gemini
GOOGLE_API_KEY=votre_cle_api
GOOGLE_MODEL=gemini-1.5-flash
```

### Exemple OpenAI
```env
LLM_PROVIDER=openai
OPENAI_API_KEY=votre_cle_api
OPENAI_MODEL=gpt-4o-mini
```

### Exemple Anthropic
```env
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=votre_cle_api
ANTHROPIC_MODEL=claude-sonnet-4-20250514
```

## Lancement
```powershell
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

Puis ouvrir:
`http://127.0.0.1:8000`

## Endpoints API

### Santé et état
- `GET /api/health`
- `GET /api/simulation/state`
- `POST /api/simulation/reset`

### Conversation
- `POST /api/simulation/step`
- `POST /api/simulation/step/stream`

### Audience
- `POST /api/audience/submit`
- `POST /api/audience/select`
- `POST /api/audience/vote`
- `POST /api/audience/vote/simulate`

### Voix
- `POST /api/voice/victim`

## Exemple rapide (curl)
```bash
curl -X POST http://127.0.0.1:8000/api/simulation/step \
  -H "Content-Type: application/json" \
  -d "{\"scammer_input\":\"Bonjour, ici le support Microsoft.\"}"
```

## Captures d'écran

### Interface utilisateur
![Interface utilisateur](docs/screenshots/Screenshot%202026-02-15%20234233.png)

### Demande de propositions
![Demande de propositions](docs/screenshots/Screenshot%202026-02-15%20234608.png)

### Vote des propositions sélectionnées
![Vote des propositions sélectionnées](docs/screenshots/Screenshot%202026-02-15%20234648.png)

## Sécurité et bonnes pratiques
- Le fichier `.env` ne doit jamais être versionné.
- Les clés JSON locales doivent rester hors dépôt public.
- Utiliser le contrôle avant commit:
```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\preflight_security_check.ps1
```

## Dépannage

### Erreur OAuth / SSL (`oauth2.googleapis.com`)
Si vous voyez une erreur de type SSL/OAuth:
- vérifiez votre accès réseau et les certificats locaux,
- vérifiez votre fichier de credentials Google,
- testez un mode sans LLM distant (`LLM_PROVIDER=none`) pour valider le fonctionnement local.

Le projet inclut un fallback heuristique pour continuer la simulation même en cas de panne distante.

### Pas de son
- Vérifier que `VICTIM_VOICE_ENABLED=true`.
- Vérifier l'accès aux fichiers `/sounds/...`.
- Vérifier les permissions autoplay du navigateur.

## Pistes d'évolution
- Ajouter une persistance des sessions (base de données).
- Ajouter un tableau de bord d'analyse des tentatives d'arnaque.
- Ajouter un export de conversations (JSON/PDF).
- Étendre les profils de victime et les scénarios.

## Décharge de responsabilité
Ce projet est fourni à des fins pédagogiques et de sensibilisation.  
Il ne doit pas être utilisé pour concevoir, automatiser ou faciliter des activités frauduleuses.
