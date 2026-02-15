# Simulateur d'Arnaque Dynamique et Interactif

## Identification du groupe
- Paul Sode
- Mohammed Hamza Laamarti

## Objectif
Ce projet implémente un théâtre d'arnaque orchestré par plusieurs agents LLM utilisant LangChain:
- **Agent Victime** (Jean Dubois) : persona d'un homme âgé de 78 ans, grognon et méfiant
- **Agent Directeur de scénario** : analyse la progression et adapte la stratégie
- **Agent Modérateur Audience** : filtre et sélectionne les propositions du public

Le système suit un script d'arnaque de type support technique Microsoft, intègre des outils audio (`@tool` LangChain) et une interface frontend moderne pour visualiser la discussion en temps réel avec vote audience interactif.

## Règles éliminatoires appliquées
1. Aucun secret dans le code (vérifié par script de contrôle)
2. `.env` est ignoré par Git
3. Les fichiers de clés JSON locaux sont ignorés par Git (ex: `ipssi-*.json`)
4. `.env.example` est fourni sans valeur sensible
5. Identification complète dans le README

## Architecture

### Backend (FastAPI)
- **`app/main.py`** : API REST + serveur frontend avec endpoints streaming SSE
- **`app/state.py`** : moteur de simulation avec gestion d'état thread-safe
- **`app/agents.py`** : logique multi-agents (Directeur / Modérateur / Victime)
- **`app/voice.py`** : synthèse vocale IA de la victime (Vertex TTS avec Gemini)
- **`app/tools.py`** : outils audio LangChain (`dog_bark`, `doorbell`, `coughing_fit`, `tv_background`)
- **`app/scenario.py`** : script et progression par étapes avec détection de mots-clés
- **`app/config.py`** : gestion complète de la configuration multi-provider
- **`app/schemas.py`** : schémas Pydantic pour validation des requêtes

### Frontend (Vanilla JS + CSS moderne)
- **`frontend/index.html`** : interface responsive avec design inspiré "vintage tech"
- **`frontend/styles.css`** : design system avec animations et variables CSS
- **`frontend/app.js`** : appels API + rendu temps réel avec streaming SSE et synthèse vocale

## Fonctionnalités implémentées

### 1. Multi-Agent LLM avec LangChain
- **Directeur** : analyse chaque échange et progresse dans le script d'arnaque
- **Modérateur** : corrige l'orthographe des propositions et sélectionne les 3 meilleures
- **Victime** : répond selon un persona détaillé avec accès aux tools audio

### 2. Support Multi-Provider LLM
- **OpenAI** (GPT-4o-mini)
- **Anthropic** (Claude Sonnet 4)
- **Google Gemini** (API développeur sans Vertex)
- **Vertex AI** (Gemini 2.0 Flash avec accès service account)
- **Auto-détection** : priorité Gemini > Anthropic > Vertex > OpenAI
- **Fallback heuristique** : fonctionne même sans LLM

### 3. Streaming Server-Sent Events (SSE)
- Réponses de la victime streamées token par token
- Affichage progressif avec effet machine à écrire
- Gestion d'erreurs robuste avec retry automatique

### 4. Synthèse Vocale IA (TTS)
- **Vertex AI Gemini TTS** avec voix personnalisée
- Configuration de style vocal (homme âgé, fatigué, débit lent)
- Lecture automatique des réponses de Jean Dubois
- Conversion PCM L16 → WAV pour compatibilité navigateur
- Contrôle de cache pour éviter les relectures

### 5. Tools LangChain (@tool decorator)
- **dog_bark()** : aboiement de chien (Poupoune)
- **doorbell()** : sonnette de porte
- **coughing_fit()** : quinte de toux de 10 secondes
- **tv_background()** : augmentation volume TV (BFMTV)
- Support natif tool calling pour OpenAI/Anthropic
- Extraction manuelle pour Gemini/Vertex

### 6. Audience Interactive
- Soumission de propositions d'événements
- Sélection intelligente par LLM (correction orthographique + filtrage)
- Vote manuel ou simulé
- Application temporaire de contraintes (2 tours)

### 7. Interface Utilisateur Moderne
- Design "vintage tech" avec effet de bruit grain
- Messages avec bulles différenciées (arnaqueur vs victime)
- Badges pour effets sonores
- État de simulation en temps réel
- Responsive design (desktop + mobile)
- Animations fluides (fade-in, rise-in, typing effect)

## Workflow implémenté (étape par étape)

1. **L'arnaqueur envoie un message**
   - Validation côté client et serveur
   - Ajout à l'historique de conversation

2. **Le Directeur analyse l'échange**
   - Détection du stage via LLM ou heuristique par mots-clés
   - Mise à jour de l'objectif tactique pour Jean Dubois
   - Justification de la décision (director_reason)

3. **Le Modérateur audience filtre les propositions**
   - Correction orthographique automatique avec vérification de similarité
   - Filtrage de contenu inapproprié (banned words)
   - Sélection des 3 meilleures propositions cohérentes avec le contexte

4. **Vote et application de la contrainte**
   - Vote manuel (clic) ou simulé (aléatoire)
   - Contrainte active pendant 2 tours
   - Décrémentation automatique à chaque échange

5. **La Victime répond avec streaming**
   - Construction du prompt modulaire avec contexte dynamique
   - Réponse streamée token par token (SSE)
   - Extraction des sound effects des tags `[SOUND_EFFECT: ...]`
   - Nettoyage du texte (suppression des didascalies)

6. **Synthèse vocale et affichage**
   - Génération audio via Vertex TTS (si activé)
   - Lecture automatique avec fallback silencieux si bloqué
   - Affichage progressif avec effet typing
   - Badges pour les effets sonores déclenchés

7. **Le frontend affiche en temps réel**
   - Discussion complète avec scroll automatique
   - État de simulation : stage, objectif, contrainte
   - Propositions et choix audience
   - Provider et modèle LLM utilisé

## Installation

### 1. Créer l'environnement virtuel

**PowerShell (Windows):**
```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

**Bash (Linux/Mac):**
```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 2. Installer les dépendances

```bash
pip install -r requirements.txt
```

**Si vous utilisez Vertex AI**, installez aussi:
```bash
pip install -r requirements-vertex.txt
```

### 3. Configurer les variables d'environnement

```bash
cp .env.example .env
```

Puis éditer `.env` selon votre configuration:

#### Option A : Gemini API (recommandé, sans Vertex)
```bash
LLM_PROVIDER=gemini
GOOGLE_API_KEY=votre_cle_gemini_api
GOOGLE_MODEL=gemini-1.5-flash
```

#### Option B : Vertex AI (avec service account fourni)
```bash
LLM_PROVIDER=vertex
GOOGLE_APPLICATION_CREDENTIALS=./ipssi-487113-729cf7c9a4af.json
VERTEX_PROJECT_ID=ipssi-487113
VERTEX_LOCATION=us-central1
VERTEX_MODEL=gemini-2.0-flash-001

# Synthèse vocale (optionnel)
VICTIM_VOICE_ENABLED=true
VERTEX_TTS_MODEL=gemini-2.5-flash-preview-tts
VERTEX_TTS_VOICE=Charon
VERTEX_TTS_LANGUAGE=fr-FR
VERTEX_TTS_STYLE_PROMPT=Voix d'homme âgé, fatigué et tremblante, débit lent, ton naturel. Lire exactement le texte fourni.
```

#### Option C : OpenAI
```bash
LLM_PROVIDER=openai
OPENAI_API_KEY=votre_cle_openai
OPENAI_MODEL=gpt-4o-mini
```

#### Option D : Anthropic Claude
```bash
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=votre_cle_anthropic
ANTHROPIC_MODEL=claude-sonnet-4-20250514
```

#### Option E : Auto-détection (recommandé)
```bash
LLM_PROVIDER=auto
# Le système détectera automatiquement le provider disponible
# Priorité: Gemini > Anthropic > Vertex > OpenAI
```

### 4. Contrôle sécurité avant commit

**PowerShell:**
```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\preflight_security_check.ps1
```

**Bash:**
```bash
bash scripts/preflight_security_check.sh
```

Si le script détecte un secret, **corriger avant tout commit**.

## Lancer l'application

```bash
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

Puis ouvrir **http://127.0.0.1:8000** dans votre navigateur.

## Endpoints API utiles

### Simulation
- `GET /api/health` - Statut LLM et synthèse vocale
- `GET /api/simulation/state` - État complet de la simulation
- `POST /api/simulation/reset` - Réinitialiser la simulation
- `POST /api/simulation/step` - Envoyer un message (réponse complète)
- `POST /api/simulation/step/stream` - Envoyer un message (streaming SSE)

### Synthèse vocale
- `POST /api/voice/victim` - Générer audio TTS pour un texte

### Audience
- `POST /api/audience/submit` - Soumettre une proposition
- `POST /api/audience/select` - Sélectionner 3 choix (avec propositions optionnelles)
- `POST /api/audience/vote` - Voter pour un choix (index 0-2)
- `POST /api/audience/vote/simulate` - Vote simulé aléatoire

## Exemple rapide (curl)

### Envoi d'un message standard
```bash
curl -X POST http://127.0.0.1:8000/api/simulation/step \
  -H "Content-Type: application/json" \
  -d '{"scammer_input":"Bonjour, support Microsoft, votre PC est infecté."}'
```

### Streaming SSE
```bash
curl -N -X POST http://127.0.0.1:8000/api/simulation/step/stream \
  -H "Content-Type: application/json" \
  -H "Accept: text/event-stream" \
  -d '{"scammer_input":"Installez TeamViewer pour que je puisse vous aider."}'
```

### Audience workflow complet
```bash
# 1. Soumettre 3 propositions
curl -X POST http://127.0.0.1:8000/api/audience/submit \
  -H "Content-Type: application/json" \
  -d '{"proposal":"Le chien aboie très fort"}'

curl -X POST http://127.0.0.1:8000/api/audience/submit \
  -H "Content-Type: application/json" \
  -d '{"proposal":"Quelqu un sonne à la porte"}'

curl -X POST http://127.0.0.1:8000/api/audience/submit \
  -H "Content-Type: application/json" \
  -d '{"proposal":"La télé fait du bruit"}'

# 2. Sélectionner 3 choix
curl -X POST http://127.0.0.1:8000/api/audience/select \
  -H "Content-Type: application/json" \
  -d '{}'

# 3. Voter (index 0 = premier choix)
curl -X POST http://127.0.0.1:8000/api/audience/vote \
  -H "Content-Type: application/json" \
  -d '{"winner_index":0}'
```

## Captures et preuves de fonctionnement

### Screenshots disponibles
Les captures d'écran démontrant le fonctionnement sont disponibles dans `docs/screenshots/`:

1. **01_overview.png** - Vue d'ensemble de l'interface avec conversation active
2. **02_streaming.png** - Démonstration du streaming SSE token par token
3. **03_audience_vote.png** - Workflow complet du système de vote audience
4. **04_sound_effects.png** - Déclenchement des effets sonores (badges visibles)
5. **05_llm_providers.png** - Comparaison des différents providers (OpenAI, Gemini, Vertex, Anthropic)
6. **06_voice_synthesis.png** - Synthèse vocale active avec indicateur de lecture

### Exemples de conversations
Des exemples détaillés de conversations complètes sont documentés dans `docs/examples.md`:
- Scénario 1 : Tentative d'installation TeamViewer (échec)
- Scénario 2 : Demande de mot de passe (refus persistant)
- Scénario 3 : Pression finale avec événement audience (distraction réussie)

## Points techniques avancés

### 1. Thread Safety
Le `SimulationEngine` utilise un `threading.Lock` pour garantir la sécurité des accès concurrents à l'état partagé.

### 2. Gestion mémoire conversation
L'historique est limité aux `MAX_HISTORY_MESSAGES` derniers messages (défaut: 40) pour éviter de saturer le contexte LLM.

### 3. Sanitization robuste
- Suppression des tags `[SOUND_EFFECT: ...]` du texte prononcé
- Suppression des préfixes de rôle (JEAN:, NARRATEUR:, etc.)
- Nettoyage des espaces multiples et retours ligne

### 4. Fallback gracieux
Si un LLM échoue, le système bascule automatiquement sur des heuristiques basées sur des mots-clés et des templates de réponse.

### 5. Correction orthographique intelligente
Le modérateur utilise un score de similarité (SequenceMatcher + token overlap) pour valider que la correction ne change pas le sens.

### 6. Détection de stage multi-critère
- **Primaire** : Analyse LLM avec JSON structuré
- **Secondaire** : Détection heuristique par mots-clés
- **Contrainte** : Pas de régression de stage (progression monotone)

## Qualité de rendu attendue

###  Code propre et lisible
- Type hints complets (`from __future__ import annotations`)
- Docstrings sur toutes les fonctions publiques
- Logging structuré avec module `logging`
- Conventions PEP 8 respectées

###  Aucune fuite de secret
- `.gitignore` strict (`.env`, `*.json` pour credentials)
- Script de contrôle pré-commit
- `.env.example` sans valeurs sensibles
- Documentation claire sur la gestion des clés

###  Démonstration de la boucle multi-agents
- Director → analyse et décision stratégique
- Moderator → filtrage et sélection audience
- Victim → réponse avec tools et contraintes

###  Exemples de conversation
- Documentation complète dans `docs/examples.md`
- Screenshots avec légendes explicatives
- Logs de debug pour traçabilité

## Critères d'évaluation (auto-évaluation)

1. **Qualité du Repository** 
   - `.gitignore` présent et complet
   - `README.md` avec noms et documentation exhaustive
   - Code organisé en modules logiques
   - Pas de secrets dans l'historique Git

2. **Prompt Engineering** 
   - Persona Jean Dubois détaillé et cohérent
   - Résistance réaliste (pas de divulgation directe)
   - Faiblesse exploitable (autorité formelle progressive)
   - Contraintes audience priorisées et détaillées

3. **Complexité LangChain** 
   - Utilisation correcte des `@tool` decorators
   - Support multi-provider avec adapters
   - Tool calling natif + extraction manuelle
   - Gestion d'état avec memory buffer

4. **Orchestration Multi-LLM** 
   - Directeur analyse et change la stratégie
   - Modérateur corrige et filtre intelligemment
   - Victime répond avec contexte dynamique
   - Communication inter-agents via state partagé

5. **Facteur "Fun"** 
   - Bruitages intégrés avec badges visuels
   - Vote audience avec effet immédiat
   - Streaming temps réel avec typing effect
   - Synthèse vocale IA de Jean Dubois
   - Interface moderne et responsive

6. **Screenshots et exemples** 
   - Screenshots dans `docs/screenshots/`
   - Exemples détaillés dans `docs/examples.md`
   - Démonstration de tous les scénarios

## Technologies utilisées

### Backend
- **FastAPI** - Framework web moderne avec support async
- **LangChain** - Orchestration LLM et tools
- **Pydantic** - Validation de données
- **Python-dotenv** - Gestion configuration
- **Google GenAI SDK** - Accès Gemini et Vertex AI
- **Google Auth** - Authentification service account

### Frontend
- **Vanilla JavaScript** - Pas de framework, performances optimales
- **Server-Sent Events (SSE)** - Streaming temps réel
- **Web Audio API** - Lecture synthèse vocale
- **CSS Variables** - Design system moderne
- **Fetch API** - Communication HTTP

### LLM Providers supportés
- **OpenAI** (GPT-4o-mini) via `langchain-openai`
- **Anthropic** (Claude Sonnet 4) via `langchain-anthropic`
- **Google Gemini** (API développeur) via `google-genai`
- **Vertex AI** (Gemini 2.0 Flash) via `google-genai` + service account

## Licence et crédits

Projet réalisé dans le cadre du **Master 2 IA - IPSSI**.

**Auteurs:**
- Paul Sode
- Mohammed Hamza Laamarti

**Encadrement pédagogique:** Cours de LangChain et Orchestration Multi-Agents

---

**Note finale:** Ce projet démontre une maîtrise complète de l'orchestration multi-agents avec LangChain, incluant la gestion de tools, le streaming SSE, la synthèse vocale IA, et une interface utilisateur moderne. Le système fonctionne avec plusieurs providers LLM et inclut des fallbacks heuristiques pour garantir la robustesse.