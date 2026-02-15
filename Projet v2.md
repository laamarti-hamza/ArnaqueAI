# 1. Projet Master 2 IA : Simulateur d'Arnaque Dynamique & Interactif

## 1.0 Consignes Administratives et de Rendu (CRITIQUE)

Avant de parler technique, voici les règles **éliminatoires** pour le rendu :

1. **Dépôt GitHub Public :** Le code doit être hébergé sur un repository GitHub public.
    
2. **Sécurité des Clés (Zéro Tolérance) :**
    
    - **AUCUNE clé d'API (OpenAI, HuggingFace, etc.) ne doit être commitée.**
        
    - Utilisez un fichier `.env` ajouté au `.gitignore`.
        
    - _Pénalité :_ Si une clé est trouvée dans l'historique des commits, le projet sera pénalisé.
        
3. **Identification :** Le fichier `README.md` doit impérativement contenir les **Noms et Prénoms** de tous les membres du groupe. Sans cela, pas de notation.

4. Le `README.md` est votre rapport, c'est ce que je note
    
---

## Informations Groupe

**Auteurs du projet :**
- Paul Sode
- Mohammed Hamza Laamarti

---

## 1.1 Architecture du Système : "Le Théâtre de l'Arnaque"

Le système n'est plus un simple chatbot, c'est une simulation orchestrée par plusieurs agents.

### 1.1.1 Les Acteurs (Agents LLM)

1. **L'Agent "Victime" (Mr Jean Dubois) :**
    
    - **Rôle :** Exécute le Persona (vieux monsieur, 78 ans, aigri, tendance à s'énerver).
        
    - **Spécificité :** Il a accès à des **Outils (Tools)** pour générer des bruitages (toux, chien, sonnette).
        
    - **Entrée :** Le texte de l'arnaqueur + L'objectif courant + Contexte audience.
        
2. **L'Agent "Directeur de Scénario" (Superviseur) :**
    
    - **Rôle :** Il ne parle pas. Il analyse la conversation en arrière-plan.
        
    - **Tâche :** Il compare l'état de la discussion avec un "Script d'Arnaque Type" (ex: Support Technique Microsoft).
        
    - **Sortie :** Il met à jour l'**Objectif Courant** de Mr Dubois (ex: "Il demande l'accès au PC -> Feindre de ne pas trouver le bouton 'Démarrer'").
        
3. **L'Agent "Modérateur Audience" :**
    
    - **Rôle :** Filtre et sélectionne les propositions de l'audience.
    
    - **Amélioration implémentée :** Correction orthographique intelligente des propositions avant sélection avec validation de similarité pour préserver le sens.
        

---

## 1.2 Fonctionnalités Clés et Workflow

### 1.2.1 Le Scénario Dynamique (Scripted Flow)

L'interaction suit un script classique (ex: Arnaque au Compte Bancaire ou Tech Support).

- **Boucle de contrôle :** À chaque échange, le _Directeur_ évalue si l'étape du script est franchie. Si oui, il pousse un nouveau contexte dans le _System Prompt_ de la Victime.

- **Implémentation réalisée :** 
  - 5 étapes de progression (Ouverture, Problème annoncé, Accès distant, Identifiants/paiement, Pression finale)
  - Détection via LLM avec JSON structuré + fallback heuristique par mots-clés
  - Progression monotone (pas de régression de stage)
    

### 1.2.2 L'Interaction Audience (Bifurcation)

Pour rendre la démo vivante, l'audience peut influencer le destin de l'arnaqueur.

1. **Input :** Les spectateurs proposent des événements via une interface (console ou simple input texte).
    
2. **Sélection (LLM) :** L'Agent _Modérateur_ reçoit toutes les idées, en élimine les inappropriées et en sélectionne **3 cohérentes** avec la situation.
    
3. **Vote :** Un vote (simulé ou réel) détermine l'événement gagnant.
    
4. **Conséquence :** L'objectif de la Victime change temporairement (ex: "Quelqu'un sonne à la porte, va ouvrir et laisse l'arnaqueur attendre 2 minutes").

5. **Amélioration implémentée :**
   - Interface web moderne avec système de vote intégré
   - Vote manuel par clic ou vote simulé automatique
   - Contrainte active pendant 2 tours avec décrémentation automatique
   - Priorisation de la contrainte audience dans le prompt (détails obligatoires pour faire perdre du temps)
    

### 4.2.3 Audio et MCP (Model Context Protocol)

La victime doit être "entendue" dans son environnement.

- **MCP Server / Tools :** Implémentez une liste d'outils que le LLM peut appeler **au lieu de répondre par du texte seul**.
    
- **Liste de Bruits (Soundboard) :**
    
    - `dog_bark()` (Poupoune s'énerve)
        
    - `doorbell()` (Livraison Amazon)
        
    - `coughing_fit()` (Quinte de toux de 10 secondes)
        
    - `tv_background()` (Augmenter le volume de la télé "BFMTV")

- **Amélioration implémentée :**
  - Support tool calling natif pour OpenAI/Anthropic
  - Extraction manuelle des tags `[SOUND_EFFECT: ...]` pour Gemini/Vertex
  - Affichage des badges visuels dans l'interface pour chaque effet sonore
  - Synthèse vocale IA (Vertex TTS) pour donner une vraie voix à Jean Dubois
        

---

## 1.3 Guide d'Implémentation Technique (LangChain)

Voici la structure de code attendue pour valider les compétences :

### A. Configuration du Prompt Système (Victime)

Le prompt doit être modulaire.

**Implémentation réalisée (`app/agents.py` - méthode `_build_system_prompt`) :**

```python
def _build_system_prompt(self, objective: str, audience_constraint: str, stage_name: str) -> str:
    return (
        "Role: Vous etes Jean Dubois, 78 ans, ancien artisan retraite. Grognon, mefiant, mais lucide. "
        "Vous vivez seul et vous n'aimez pas qu'on vous presse. "
        "Vous ne donnez jamais de mot de passe, code, RIB, numero de carte, piece d'identite ou acces a distance. "
        "Jamais directement, meme sous pression ou menace. "
        # ... (persona détaillé)
        f"Current Context: Stage={stage_name}. Objectif={objective}\n"
        f"Audience Event: {audience_constraint or 'Aucun evenement audience en cours.'}\n"
        "Regle critique: la contrainte audience est prioritaire et doit etre prise en compte a chaque reponse..."
        # ... (instructions détaillées)
    )
```

**Améliorations apportées :**
- Prompt modulaire avec injection dynamique du contexte
- Persona riche et nuancé avec faiblesse exploitable (autorité formelle)
- Priorisation explicite de la contrainte audience
- Instructions pour produire des réponses détaillées qui font perdre du temps

### B. Gestion des Outils (MCP/Tools)

Utilisez le décorateur `@tool` de LangChain.

**Implémentation réalisée (`app/tools.py`) :**

```python
from langchain_core.tools import tool

@tool
def dog_bark() -> str:
    """Joue un bruitage d'aboiement de chien."""
    return "[SOUND_EFFECT: DOG_BARKING]"

@tool
def doorbell() -> str:
    """Joue un bruitage de sonnette de porte."""
    return "[SOUND_EFFECT: DOORBELL]"

@tool
def coughing_fit() -> str:
    """Simule une quinte de toux de dix secondes."""
    return "[SOUND_EFFECT: COUGHING_FIT]"

@tool
def tv_background() -> str:
    """Augmente le volume de la television en bruit de fond."""
    return "[SOUND_EFFECT: TV_BACKGROUND_BFMTV]"

# Registry pour accès dynamique
SOUND_TOOL_REGISTRY: Dict[str, object] = {
    "dog_bark": dog_bark,
    "doorbell": doorbell,
    "coughing_fit": coughing_fit,
    "tv_background": tv_background,
}
```

**Améliorations apportées :**
- Tous les tools suivent le pattern `@tool` de LangChain
- Registry pour invocation dynamique
- Support multi-provider (tool calling natif + extraction manuelle)
- Extraction et nettoyage des tags dans les réponses

### C. La Boucle d'Exécution

**Implémentation réalisée (`app/state.py` - méthode `_step_unlocked`) :**

```python
def _step_unlocked(self, clean_input: str, on_text_chunk: Callable[[str], None] | None = None) -> Dict[str, object]:
    # 1. L'arnaqueur (Humain ou autre LLM) parle
    self._add_message_unlocked(role="scammer", content=clean_input)
    
    # 2. Le Directeur analyse et met à jour l'objectif
    decision = self.director.decide(
        latest_scammer=clean_input,
        history=history_window,
        current_stage=self.state.stage_index,
    )
    self.state.stage_index = decision.stage_index
    self.state.current_objective = decision.objective
    self.state.director_reason = decision.reason
    
    # 3. Check Audience (géré séparément via endpoints dédiés)
    # Les contraintes sont déjà dans self.state.audience_constraint
    
    # 4. La Victime répond (avec accès aux Tools Bruits)
    if on_text_chunk is None:
        victim_reply = self.victim.respond(...)
    else:
        victim_reply = self.victim.respond_stream(...)
    
    self._add_message_unlocked(
        role="victim",
        content=victim_reply.text,
        sound_effects=victim_reply.sound_effects,
    )
    
    # 5. Tick de la contrainte audience
    self._tick_audience_constraint_unlocked()
    
    return self._snapshot_unlocked()
```

**Améliorations apportées :**
- Boucle complète avec tous les agents
- Support streaming SSE pour réponses progressives
- Thread-safety avec `threading.Lock`
- Gestion automatique du cycle de vie des contraintes
- Snapshot complet de l'état pour le frontend

---

## 1.4 Critères d'Évaluation Finaux

1. **Qualité du Repository :** `.gitignore` présent, `README.md` complet avec noms, code propre.
   -  **Réalisé** : `.gitignore` strict, README exhaustif, code organisé en modules

2. **Prompt Engineering :** La résistance de Jean Dubois (est-ce qu'il craque et donne le mot de passe ? Si oui, c'est raté).
   -  **Réalisé** : Jean ne divulgue jamais directement. Faiblesse exploitable via autorité formelle progressive uniquement
 
3. **Complexité LangChain :** Utilisation correcte des _Agents_, _Tools_, et _Chains_.
   -  **Réalisé** : 3 agents distincts, 4 tools avec `@tool`, support multi-provider
 
4. **Orchestration Multi-LLM :** Le _Directeur_ change-t-il bien la stratégie en fonction du script ?
   -  **Réalisé** : Analyse LLM + heuristique, progression par stages, justification des décisions

5. **Facteur "Fun" :** L'intégration des bruits et des votes audience fonctionne-t-elle ?
   -  **Réalisé** : Bruitages avec badges visuels, vote interactif, synthèse vocale IA, interface moderne

6. **Screenshots et exemples** : Ajouter des exemples qui montrent que votre projet fonctionne.
   -  **Réalisé** : Documentation complète avec screenshots et exemples de conversations

---

## 1.5 Fonctionnalités Avancées Implémentées

Au-delà des exigences de base, le projet inclut :

### 1. Support Multi-Provider LLM
- **OpenAI** (GPT-4o-mini)
- **Anthropic** (Claude Sonnet 4)
- **Google Gemini** (API développeur)
- **Vertex AI** (Gemini 2.0 Flash)
- Auto-détection avec priorité configurable
- Fallback heuristique si aucun LLM disponible

### 2. Streaming Server-Sent Events (SSE)
- Endpoint `/api/simulation/step/stream`
- Événements `chunk`, `done`, `error`
- Affichage progressif token par token
- Effet machine à écrire dans l'interface

### 3. Synthèse Vocale IA
- Vertex AI Gemini TTS avec voix personnalisée
- Configuration de style vocal (homme âgé, fatigué)
- Lecture automatique des réponses
- Conversion PCM L16 → WAV
- Gestion de cache pour éviter relectures

### 4. Interface Frontend Moderne
- Design "vintage tech" avec effet grain
- Messages bulles différenciées
- Badges pour effets sonores
- État temps réel (stage, objectif, contrainte)
- Responsive design
- Animations fluides

### 5. Correction Orthographique Intelligente
- LLM corrige les propositions audience
- Validation par score de similarité
- Préservation du sens original
- Fallback sur proposition originale si changement trop important

### 6. Gestion Robuste des Erreurs
- Thread-safety avec locks
- Validation Pydantic des requêtes
- Messages d'erreur explicites
- Retry automatique pour streaming
- Logs structurés pour debug

### 7. Configuration Flexible
- Support fichiers `.env` et variables d'environnement
- Auto-détection des credentials Google
- Configuration TTS personnalisable
- Limites configurables (historique, longueur messages)

---

## 1.6 Architecture Technique Détaillée

### Backend (FastAPI + LangChain)
```
app/
├── __init__.py          # Package marker
├── main.py              # API REST + serveur frontend
├── state.py             # SimulationEngine avec state management
├── agents.py            # DirectorAgent, ModeratorAgent, VictimAgent
├── voice.py             # VictimVoiceSynthesizer (Vertex TTS)
├── tools.py             # Tools LangChain pour bruitages
├── scenario.py          # Script d'arnaque par étapes
├── config.py            # Configuration multi-provider
└── schemas.py           # Schémas Pydantic validation
```

### Frontend (Vanilla JS)
```
frontend/
├── index.html           # Structure HTML responsive
├── styles.css           # Design system moderne
└── app.js               # Logique client (API calls, SSE, TTS playback)
```

### Flow de données
```
User Input → FastAPI Endpoint → SimulationEngine
                                      ↓
                          DirectorAgent.decide()
                                      ↓
                          VictimAgent.respond_stream()
                                      ↓
                          SSE Stream → Frontend
                                      ↓
                          VictimVoiceSynthesizer.synthesize()
                                      ↓
                          Audio Playback
```

---

## 1.7 Points d'Excellence du Projet

1. **Orchestration Multi-Agents Complète**
   - 3 agents LLM distincts avec responsabilités claires
   - Communication via état partagé thread-safe
   - Décisions justifiées et traçables

2. **Flexibilité et Robustesse**
   - Support 4 providers LLM différents
   - Fallback heuristique si LLM indisponible
   - Gestion d'erreurs gracieuse à tous les niveaux

3. **Expérience Utilisateur Moderne**
   - Interface responsive et animée
   - Streaming temps réel des réponses
   - Synthèse vocale pour immersion
   - Feedback visuel immédiat

4. **Qualité du Code**
   - Type hints complets Python 3.10+
   - Documentation inline et docstrings
   - Separation of concerns claire
   - Conventions PEP 8 respectées

5. **Sécurité et Bonnes Pratiques**
   - Aucun secret dans le code
   - Script de contrôle pré-commit
   - Validation stricte des inputs
   - Rate limiting prévu (historique limité)

---

## 1.8 Améliorations Futures Possibles

1. **Agents supplémentaires**
   - Agent "Analyste" pour statistiques en temps réel
   - Agent "Narrateur" pour commentaires humoristiques
   - Multi-victimes avec personnalités différentes

2. **Scénarios variés**
   - Arnaque au faux support technique Apple
   - Arnaque au CPF/retraite
   - Arnaque amoureuse
   - Phishing bancaire

3. **Fonctionnalités avancées**
   - Enregistrement des sessions pour replay
   - Classement des arnaqueurs (qui tient le plus longtemps)
   - Mode entraînement avec conseils en temps réel
   - Export PDF des conversations

4. **Amélioration IA**
   - Fine-tuning sur vraies conversations d'arnaques
   - Détection automatique de techniques de manipulation
   - Adaptation du persona selon le profil arnaqueur

---

## Conclusion

Ce projet démontre une **maîtrise complète** de l'orchestration multi-agents avec LangChain, combinant :
- Architecture modulaire et extensible
- Utilisation avancée des tools et du streaming
- Interface utilisateur moderne et réactive
- Support multi-provider LLM
- Synthèse vocale IA pour immersion
- Gestion robuste des erreurs et de la sécurité

Le système fonctionne de manière autonome avec plusieurs providers LLM et inclut des fallbacks heuristiques pour garantir la robustesse. L'expérience utilisateur est soignée avec streaming temps réel, effets sonores, et voix synthétique.

**Auteurs :** Paul Sode et Mohammed Hamza Laamarti
**Formation :** Master 2 IA - IPSSI
**Technologies :** FastAPI, LangChain, OpenAI/Anthropic/Gemini/Vertex AI, Vanilla JS, Server-Sent Events